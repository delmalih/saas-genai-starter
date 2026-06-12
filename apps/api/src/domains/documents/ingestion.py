import json
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
from src.domains.documents.parsing import Page, chunk_pages, extract_pages
from src.domains.documents.repository import DocumentChunkRepository, DocumentRepository
from src.domains.usage.models import FEATURE_EXTRACTION
from src.domains.usage.service import UsageService
from src.llm.provider import ChatProvider, EmbeddingProvider
from src.llm.types import Message

logger = structlog.get_logger(__name__)

EMBED_BATCH_SIZE = 100
METADATA_SAMPLE_CHARS = 6000

METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "A short descriptive title"},
        "language": {"type": "string", "description": "ISO 639-1 code, e.g. en, fr"},
        "summary": {"type": "string", "description": "Two sentences maximum"},
        "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    },
    "required": ["title", "language", "summary", "topics"],
    "additionalProperties": False,
}


async def ingest_document(
    db: AsyncSession,
    storage: BlobStorage,
    embedder: EmbeddingProvider,
    tenant: TenantContext,
    document_id: uuid.UUID,
    chat_provider: ChatProvider | None = None,
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
        await _run_pipeline(db, storage, embedder, tenant, document, chunks_repo, chat_provider)
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
    chat_provider: ChatProvider | None,
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

    if chat_provider is not None:
        await _extract_metadata(db, tenant, chat_provider, document, pages)

    document.status = STATUS_READY
    await db.commit()
    logger.info("ingestion.ready", document_id=str(document.id), chunks=len(chunks))


async def _extract_metadata(
    db: AsyncSession,
    tenant: TenantContext,
    chat_provider: ChatProvider,
    document: Document,
    pages: list[Page],
) -> None:
    """Best-effort: a failure here must never fail the ingestion."""
    sample = "\n".join(page.text for page in pages)[:METADATA_SAMPLE_CHARS]
    prompt = (
        "Extract metadata from this document excerpt. Be factual and concise.\n\n"
        f"<excerpt>\n{sample}\n</excerpt>"
    )
    try:
        completion = await UsageService(db, tenant).tracked_complete(
            chat_provider,
            FEATURE_EXTRACTION,
            document.created_by,
            [Message(role="user", content=prompt)],
            json_schema=METADATA_SCHEMA,
            max_tokens=500,
        )
        data = json.loads(completion.text)
        document.title = str(data.get("title", ""))[:255] or None
        document.language = str(data.get("language", ""))[:16] or None
        document.summary = str(data.get("summary", "")) or None
        topics = data.get("topics")
        document.topics = [str(t) for t in topics][:5] if isinstance(topics, list) else None
    except Exception as exc:
        logger.warning("ingestion.metadata_failed", document_id=str(document.id), error=str(exc))
