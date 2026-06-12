"""ARQ background worker — the local/default queue driver.

Run with: uv run arq src.worker.WorkerSettings (or `make worker`).
In production with QUEUE_DRIVER=cloud_tasks this process is not deployed;
Cloud Tasks pushes the same jobs to /internal/jobs/* instead.
Jobs are idempotent — a job killed mid-run is retried from scratch and
re-ingestion replaces existing chunks.
"""

from typing import Any

import structlog
from arq.connections import RedisSettings
from arq.worker import Retry

import src.all_models  # noqa: F401 — completes the SQLAlchemy registry
from src.core.config import get_settings
from src.core.logging import setup_logging
from src.domains.documents.jobs import run_ingest_job

logger = structlog.get_logger(__name__)

MAX_TRIES = 3
RETRY_DELAY_SECONDS = 5


async def ingest_document_job(
    ctx: dict[str, Any], document_id: str, tenant_id: str, user_id: str
) -> None:
    try:
        await run_ingest_job(document_id, tenant_id, user_id)
    except Exception as exc:
        # run_ingest_job already marked the document failed; retry a couple
        # of times for transient failures (provider hiccups).
        if ctx["job_try"] < MAX_TRIES:
            logger.warning(
                "ingestion.retry",
                document_id=document_id,
                attempt=ctx["job_try"],
                error=str(exc),
            )
            raise Retry(defer=RETRY_DELAY_SECONDS * ctx["job_try"]) from exc
        logger.error("ingestion.dead_letter", document_id=document_id, error=str(exc))


async def startup(ctx: dict[str, Any]) -> None:
    from src.core.telemetry import setup_telemetry

    setup_logging()
    setup_telemetry()
    logger.info("worker.started")


class WorkerSettings:
    functions = (ingest_document_job,)
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_TRIES
    job_timeout = 600
