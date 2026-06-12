import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status

from src.core.config import get_settings
from src.core.db import DbSession
from src.core.errors import ApiError, NotFound
from src.core.queue import TaskQueue, get_task_queue
from src.core.storage import BlobStorage, get_storage
from src.core.tenancy import CurrentTenant
from src.domains.documents.models import ALLOWED_MIME_TYPES, Document
from src.domains.documents.repository import DocumentChunkRepository, DocumentRepository
from src.domains.documents.schemas import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])

Storage = Annotated[BlobStorage, Depends(get_storage)]
Queue = Annotated[TaskQueue, Depends(get_task_queue)]

INGEST_JOB = "ingest_document_job"


def _out(document: Document) -> DocumentOut:
    return DocumentOut.model_validate(document, from_attributes=True)


@router.get("")
async def list_documents(tenant: CurrentTenant, db: DbSession) -> list[DocumentOut]:
    documents = await DocumentRepository(db, tenant).list_recent()
    return [_out(d) for d in documents]


@router.get("/{document_id}")
async def get_document(document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession) -> DocumentOut:
    document = await DocumentRepository(db, tenant).get(document_id)
    if document is None:
        raise NotFound("Document not found")
    return _out(document)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    tenant: CurrentTenant,
    db: DbSession,
    storage: Storage,
    queue: Queue,
) -> DocumentOut:
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ApiError(
            415,
            "unsupported_type",
            f"Unsupported file type {mime_type} — allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )
    data = await file.read()
    max_bytes = get_settings().max_upload_bytes
    if len(data) > max_bytes:
        raise ApiError(
            413, "file_too_large", f"File exceeds the {max_bytes // (1024 * 1024)}MB limit"
        )
    if not data:
        raise ApiError(400, "bad_request", "Empty file")

    name = (file.filename or "document")[:255]
    document = DocumentRepository(db, tenant).add(
        Document(
            name=name,
            mime_type=mime_type,
            size_bytes=len(data),
            created_by=tenant.user_id,
            storage_path="",
        )
    )
    await db.flush()
    document.storage_path = f"{tenant.organization_id}/{document.id}/{name}"
    await storage.save(document.storage_path, data)
    await db.refresh(document)
    response = _out(document)
    await db.commit()

    await queue.enqueue(
        INGEST_JOB,
        document_id=str(document.id),
        tenant_id=str(tenant.organization_id),
        user_id=tenant.user_id,
    )
    return response


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    tenant: CurrentTenant,
    db: DbSession,
    storage: Storage,
) -> None:
    documents = DocumentRepository(db, tenant)
    document = await documents.get(document_id)
    if document is None:
        raise NotFound("Document not found")
    await DocumentChunkRepository(db, tenant).delete_for_document(document.id)
    await storage.delete(document.storage_path)
    await documents.delete(document)
    await db.commit()
