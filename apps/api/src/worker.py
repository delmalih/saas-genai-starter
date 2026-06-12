"""ARQ background worker.

Run with: uv run arq src.worker.WorkerSettings (or `make worker`).
Jobs are idempotent — a job killed mid-run is retried from scratch and
re-ingestion replaces existing chunks.
"""

import uuid
from typing import Any

import structlog
from arq.connections import RedisSettings
from arq.worker import Retry

from src.core.config import get_settings
from src.core.db import get_sessionmaker
from src.core.logging import setup_logging
from src.core.storage import get_storage
from src.core.tenancy import TenantContext
from src.domains.documents.ingestion import ingest_document
from src.llm.errors import ProviderNotConfigured
from src.llm.factory import get_chat_provider, get_embedding_provider
from src.llm.provider import ChatProvider

logger = structlog.get_logger(__name__)

MAX_TRIES = 3
RETRY_DELAY_SECONDS = 5


async def ingest_document_job(
    ctx: dict[str, Any], document_id: str, tenant_id: str, user_id: str
) -> None:
    tenant = TenantContext(organization_id=uuid.UUID(tenant_id), user_id=user_id, role="member")
    chat_provider: ChatProvider | None
    try:
        chat_provider = get_chat_provider()
    except ProviderNotConfigured:
        chat_provider = None  # metadata extraction is skipped, ingestion proceeds
    async with get_sessionmaker()() as db:
        try:
            await ingest_document(
                db,
                get_storage(),
                get_embedding_provider(),
                tenant,
                uuid.UUID(document_id),
                chat_provider=chat_provider,
            )
        except Exception as exc:
            # ingest_document already marked the document failed; retry a
            # couple of times for transient failures (provider hiccups).
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
