"""Ingestion job logic — shared by the ARQ worker (local/default) and the
Cloud Tasks push endpoint (production). Callers own the retry policy;
permanent configuration errors mark the document failed and return cleanly,
transient errors raise."""

import uuid

import structlog

from src.core.db import get_sessionmaker
from src.core.storage import get_storage
from src.core.tenancy import TenantContext
from src.domains.documents.ingestion import ingest_document
from src.domains.documents.models import STATUS_FAILED
from src.domains.documents.repository import DocumentRepository
from src.domains.llm_settings.resolver import (
    resolve_chat_provider,
    resolve_embedding_provider,
)
from src.llm.errors import ProviderNotConfigured
from src.llm.provider import ChatProvider

logger = structlog.get_logger(__name__)


async def run_ingest_job(document_id: str, tenant_id: str, user_id: str) -> None:
    tenant = TenantContext(organization_id=uuid.UUID(tenant_id), user_id=user_id, role="member")
    async with get_sessionmaker()() as db:
        try:
            embedder = await resolve_embedding_provider(db, tenant)
        except ProviderNotConfigured as exc:
            # Config error, not transient — mark failed, no retry.
            await _mark_failed(db, tenant, document_id, str(exc))
            return
        chat_provider: ChatProvider | None
        try:
            chat_provider = await resolve_chat_provider(db, tenant)
        except ProviderNotConfigured:
            chat_provider = None  # metadata extraction is skipped, ingestion proceeds
        await ingest_document(
            db,
            get_storage(),
            embedder,
            tenant,
            uuid.UUID(document_id),
            chat_provider=chat_provider,
        )


async def _mark_failed(db: object, tenant: TenantContext, document_id: str, message: str) -> None:
    document = await DocumentRepository(db, tenant).get(uuid.UUID(document_id))  # type: ignore[arg-type]
    if document is not None:
        document.status = STATUS_FAILED
        document.error = message[:2000]
        await db.commit()  # type: ignore[attr-defined]
    logger.error("ingestion.not_configured", document_id=document_id, error=message)
