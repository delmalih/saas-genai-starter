import asyncio
import json
from typing import Any, Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from src.core.config import get_settings


class TaskQueue(Protocol):
    """Background job dispatch — ARQ (Redis) locally and by default;
    Cloud Tasks HTTP push in production (QUEUE_DRIVER=cloud_tasks)."""

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


class CloudTasksQueue:
    """Enqueues HTTP push tasks targeting this API's /internal/jobs/<name>
    endpoint, authenticated with an OIDC token — no always-on worker, the
    job handler scales to zero with the service. Retries are configured on
    the queue itself (Terraform)."""

    def __init__(self, client: Any | None = None):
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import tasks_v2

            self._client = tasks_v2.CloudTasksClient()
        return self._client

    async def enqueue(self, job_name: str, **kwargs: Any) -> None:
        settings = get_settings()
        if not (
            settings.cloud_tasks_queue
            and settings.internal_jobs_base_url
            and settings.jobs_service_account_email
        ):
            raise RuntimeError(
                "QUEUE_DRIVER=cloud_tasks requires CLOUD_TASKS_QUEUE, "
                "INTERNAL_JOBS_BASE_URL and JOBS_SERVICE_ACCOUNT_EMAIL"
            )
        base_url = settings.internal_jobs_base_url.rstrip("/")
        task = {
            "http_request": {
                "http_method": 4,  # tasks_v2.HttpMethod.POST
                "url": f"{base_url}/internal/jobs/{job_name}",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(kwargs).encode(),
                "oidc_token": {
                    "service_account_email": settings.jobs_service_account_email,
                    "audience": base_url,
                },
            }
        }
        client = self._get_client()
        # The google client is sync — keep the event loop free.
        await asyncio.to_thread(client.create_task, parent=settings.cloud_tasks_queue, task=task)


_arq_queue = ArqTaskQueue()
_cloud_tasks_queue = CloudTasksQueue()


def get_task_queue() -> TaskQueue:
    """FastAPI dependency — overridable in tests."""
    if get_settings().queue_driver == "cloud_tasks":
        return _cloud_tasks_queue
    return _arq_queue
