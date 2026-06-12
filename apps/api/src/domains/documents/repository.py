import uuid

from sqlalchemy import delete

from src.core.repository import TenantScopedRepository
from src.domains.documents.models import Document, DocumentChunk


class DocumentRepository(TenantScopedRepository[Document]):
    model = Document

    async def list_recent(self, limit: int = 100) -> list[Document]:
        result = await self._db.execute(
            self._query().order_by(Document.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


class DocumentChunkRepository(TenantScopedRepository[DocumentChunk]):
    model = DocumentChunk

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.tenant_id == self._tenant.organization_id,
                DocumentChunk.document_id == document_id,
            )
        )
