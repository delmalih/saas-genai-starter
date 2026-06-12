import time
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.storage import BlobStorage
from src.core.tenancy import TenantContext
from src.domains.documents.models import (
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_READY,
    Document,
    DocumentChunk,
)
from src.domains.documents.parsing import chunk_pages, extract_pages
from src.domains.documents.repository import DocumentChunkRepository, DocumentRepository
from src.domains.usage.service import UsageService
from src.llm.provider import EmbeddingProvider

logger = structlog.get_logger(__name__)

EMBED_BATCH_SIZE = 100


async def ingest_document(
    db: AsyncSession,
    storage: BlobStorage,
    embedder: EmbeddingProvider,
    tenant: TenantContext,
    document_id: uuid.UUID,
) -> None:
    """Parse → chunk → embed → store. Sets the document status to ready,
    or failed with the error message. Idempotent: re-running replaces chunks."""
    documents = DocumentRepository(db, tenant)
    chunks_repo = DocumentChunkRepository(db, tenant)

    document = await documents.get(document_id)
    if document is None:
        logger.warning("ingestion.document_missing", document_id=str(document_id))
        return

    document.status = STATUS_PROCESSING
    document.error = None
    await db.commit()

    try:
        await _run_pipeline(db, storage, embedder, tenant, document, chunks_repo)
    except Exception as exc:
        await db.rollback()
        document.status = STATUS_FAILED
        document.error = f"{type(exc).__name__}: {exc}"[:2000]
        await db.commit()
        logger.error("ingestion.failed", document_id=str(document.id), error=str(exc))
        raise


async def _run_pipeline(
    db: AsyncSession,
    storage: BlobStorage,
    embedder: EmbeddingProvider,
    tenant: TenantContext,
    document: Document,
    chunks_repo: DocumentChunkRepository,
) -> None:
    data = await storage.load(document.storage_path)
    pages = extract_pages(data, document.mime_type)
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("No text content found in the document")

    await chunks_repo.delete_for_document(document.id)

    usage = UsageService(db, tenant)
    for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
        started = time.monotonic()
        result = await embedder.embed([c.content for c in batch], input_type="document")
        await usage.record_embedding(
            created_by=document.created_by,
            model=result.model,
            input_tokens=result.input_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        for chunk, embedding in zip(batch, result.embeddings, strict=True):
            chunks_repo.add(
                DocumentChunk(
                    document_id=document.id,
                    page=chunk.page,
                    position=chunk.position,
                    content=chunk.content,
                    embedding=embedding,
                )
            )

    document.status = STATUS_READY
    await db.commit()
    logger.info("ingestion.ready", document_id=str(document.id), chunks=len(chunks))
