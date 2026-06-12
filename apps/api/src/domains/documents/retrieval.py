import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenancy import TenantContext
from src.domains.documents.models import STATUS_READY, Document, DocumentChunk
from src.domains.usage.service import UsageService
from src.llm.provider import EmbeddingProvider

DEFAULT_TOP_K = 5
SNIPPET_MAX_CHARS = 400


@dataclass(frozen=True)
class Citation:
    document_id: uuid.UUID
    document_name: str
    page: int | None
    snippet: str
    score: float


class RetrievalService:
    """Vector search over the tenant's ready documents."""

    def __init__(self, db: AsyncSession, tenant: TenantContext, embedder: EmbeddingProvider):
        self._db = db
        self._tenant = tenant
        self._embedder = embedder

    async def search(
        self, query: str, created_by: str, top_k: int = DEFAULT_TOP_K
    ) -> list[Citation]:
        started = time.monotonic()
        result = await self._embedder.embed([query], input_type="query")
        await UsageService(self._db, self._tenant).record_embedding(
            created_by=created_by,
            model=result.model,
            input_tokens=result.input_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        query_vector = result.embeddings[0]

        distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        statement = (
            select(DocumentChunk, Document.name, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.tenant_id == self._tenant.organization_id,
                Document.status == STATUS_READY,
            )
            .order_by(distance)
            .limit(top_k)
        )
        rows = (await self._db.execute(statement)).all()
        return [
            Citation(
                document_id=chunk.document_id,
                document_name=name,
                page=chunk.page,
                snippet=chunk.content[:SNIPPET_MAX_CHARS],
                score=round(1.0 - dist, 4),
            )
            for chunk, name, dist in rows
        ]

    async def has_ready_documents(self) -> bool:
        statement = (
            select(Document.id)
            .where(
                Document.tenant_id == self._tenant.organization_id,
                Document.status == STATUS_READY,
            )
            .limit(1)
        )
        return (await self._db.execute(statement)).scalar_one_or_none() is not None
