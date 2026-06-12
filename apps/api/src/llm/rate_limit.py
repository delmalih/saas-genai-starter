import time
import uuid
from datetime import UTC, datetime

import redis.asyncio as redis
import structlog

from src.core.errors import QuotaExceeded

logger = structlog.get_logger(__name__)

WINDOW_SECONDS = 60


class TenantRateLimiter:
    """Redis-backed per-tenant limits for LLM endpoints.

    Two independent budgets:
    - requests/minute — sliding window over a sorted set
    - tokens/day — daily counter fed by recorded usage

    Fails open: if Redis is unreachable, requests are allowed and the error
    is logged — availability over strictness, the cost guard is best-effort.
    """

    def __init__(
        self,
        client: redis.Redis,
        requests_per_minute: int,
        tokens_per_day: int,
    ):
        self._redis = client
        self._requests_per_minute = requests_per_minute
        self._tokens_per_day = tokens_per_day

    async def check(self, tenant_id: uuid.UUID) -> None:
        """Raises QuotaExceeded if either budget is exhausted."""
        try:
            await self._check_requests(tenant_id)
            await self._check_tokens(tenant_id)
        except QuotaExceeded:
            raise
        except redis.RedisError as exc:
            logger.error("rate_limit.redis_unavailable", error=str(exc))

    async def record_tokens(self, tenant_id: uuid.UUID, tokens: int) -> None:
        if tokens <= 0:
            return
        key = self._tokens_key(tenant_id)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incrby(key, tokens)
                pipe.expire(key, 60 * 60 * 48)
                await pipe.execute()
        except redis.RedisError as exc:
            logger.error("rate_limit.redis_unavailable", error=str(exc))

    async def _check_requests(self, tenant_id: uuid.UUID) -> None:
        key = f"rl:req:{tenant_id}"
        now = time.time()
        window_start = now - WINDOW_SECONDS

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            _, current = await pipe.execute()

        if current >= self._requests_per_minute:
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            oldest_score = float(oldest[0][1]) if oldest else now
            retry_after = max(1, int(oldest_score + WINDOW_SECONDS - now) + 1)
            raise QuotaExceeded(
                f"Request limit reached ({self._requests_per_minute}/minute)",
                retry_after_seconds=retry_after,
            )

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
            pipe.expire(key, WINDOW_SECONDS * 2)
            await pipe.execute()

    async def _check_tokens(self, tenant_id: uuid.UUID) -> None:
        used = await self._redis.get(self._tokens_key(tenant_id))
        if used is not None and int(used) >= self._tokens_per_day:
            raise QuotaExceeded(
                f"Daily token budget reached ({self._tokens_per_day} tokens/day)",
                retry_after_seconds=self._seconds_until_midnight(),
            )

    @staticmethod
    def _tokens_key(tenant_id: uuid.UUID) -> str:
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        return f"rl:tok:{tenant_id}:{day}"

    @staticmethod
    def _seconds_until_midnight() -> int:
        now = datetime.now(UTC)
        midnight = now.replace(hour=23, minute=59, second=59)
        return max(1, int((midnight - now).total_seconds()) + 1)


def get_rate_limiter() -> TenantRateLimiter:
    from src.core.config import get_settings
    from src.core.redis import get_redis

    settings = get_settings()
    return TenantRateLimiter(
        get_redis(),
        requests_per_minute=settings.rate_limit_requests_per_minute,
        tokens_per_day=settings.rate_limit_tokens_per_day,
    )
