import uuid

import pytest
import redis.asyncio as redis
from src.core.config import get_settings
from src.core.errors import QuotaExceeded
from src.llm.rate_limit import TenantRateLimiter


@pytest.fixture
async def redis_client() -> redis.Redis:
    client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    yield client
    await client.aclose()


def limiter(client: redis.Redis, rpm: int = 3, tpd: int = 1000) -> TenantRateLimiter:
    return TenantRateLimiter(client, requests_per_minute=rpm, tokens_per_day=tpd)


async def test_allows_under_the_limit(redis_client: redis.Redis) -> None:
    tenant = uuid.uuid4()
    rate_limiter = limiter(redis_client)
    for _ in range(3):
        await rate_limiter.check(tenant)


async def test_blocks_above_request_limit_with_retry_after(
    redis_client: redis.Redis,
) -> None:
    tenant = uuid.uuid4()
    rate_limiter = limiter(redis_client, rpm=3)
    for _ in range(3):
        await rate_limiter.check(tenant)

    with pytest.raises(QuotaExceeded) as exc_info:
        await rate_limiter.check(tenant)
    assert exc_info.value.retry_after_seconds >= 1
    assert exc_info.value.headers == {"Retry-After": str(exc_info.value.retry_after_seconds)}


async def test_tenants_are_isolated(redis_client: redis.Redis) -> None:
    exhausted, fresh = uuid.uuid4(), uuid.uuid4()
    rate_limiter = limiter(redis_client, rpm=2)
    for _ in range(2):
        await rate_limiter.check(exhausted)
    with pytest.raises(QuotaExceeded):
        await rate_limiter.check(exhausted)

    # The other tenant is unaffected.
    await rate_limiter.check(fresh)


async def test_daily_token_budget(redis_client: redis.Redis) -> None:
    tenant = uuid.uuid4()
    rate_limiter = limiter(redis_client, rpm=100, tpd=500)

    await rate_limiter.record_tokens(tenant, 499)
    await rate_limiter.check(tenant)

    await rate_limiter.record_tokens(tenant, 1)
    with pytest.raises(QuotaExceeded) as exc_info:
        await rate_limiter.check(tenant)
    assert "token budget" in str(exc_info.value)


async def test_fails_open_when_redis_is_down() -> None:
    broken = redis.Redis.from_url("redis://localhost:1", socket_connect_timeout=0.2)
    rate_limiter = limiter(broken)

    # No exception: availability wins over strictness.
    await rate_limiter.check(uuid.uuid4())
    await rate_limiter.record_tokens(uuid.uuid4(), 100)
    await broken.aclose()
