from typing import Any, Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from src.core.config import get_settings


class TaskQueue(Protocol):
    """Background job dispatch — ARQ (Redis) locally and by default;
    a Cloud Tasks adapter lands with the infra epic (SGS-041)."""

    async def enqueue(self, job_name: str, **kwargs: Any) -> None: ...


class ArqTaskQueue:
    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        return self._pool

    async def enqueue(self, job_name: str, **kwargs: Any) -> None:
        pool = await self._get_pool()
        await pool.enqueue_job(job_name, **kwargs)


_queue = ArqTaskQueue()


def get_task_queue() -> TaskQueue:
    """FastAPI dependency — overridable in tests."""
    return _queue
