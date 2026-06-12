import io
import uuid
from pathlib import Path
from typing import Any

import httpx
import pymupdf
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.queue import get_task_queue
from src.core.storage import LocalDiskStorage, get_storage
from src.core.tenancy import TenantContext
from src.domains.documents.ingestion import ingest_document
from src.domains.documents.models import Document, DocumentChunk
from src.domains.documents.parsing import chunk_pages, extract_pages
from src.domains.tenants.models import Membership, Organization
from src.llm.errors import ProviderUnavailable

from tests.conftest import AuthHeaderFactory
from tests.llm.fakes import FakeEmbeddingProvider


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, dict[str, Any]]] = []

    async def enqueue(self, job_name: str, **kwargs: Any) -> None:
        self.jobs.append((job_name, kwargs))


@pytest.fixture
def storage(tmp_path: Path) -> LocalDiskStorage:
    return LocalDiskStorage(tmp_path)


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


@pytest.fixture
def overrides(app: FastAPI, storage: LocalDiskStorage, queue: RecordingQueue) -> None:
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_task_queue] = lambda: queue


@pytest.fixture
async def tenant(db_session: AsyncSession) -> TenantContext:
    organization = Organization(name="Docs Co")
    organization.memberships = [Membership(user_id="alice", role="owner")]
    db_session.add(organization)
    await db_session.flush()
    return TenantContext(organization_id=organization.id, user_id="alice", role="owner")


@pytest.fixture
def org_headers(tenant: TenantContext, auth_headers: AuthHeaderFactory) -> dict[str, str]:
    return {**auth_headers(user_id="alice"), "X-Org-Id": str(tenant.organization_id)}


def make_pdf(texts: list[str]) -> bytes:
    document = pymupdf.open()
    for text in texts:
        page = document.new_page()
        page.insert_text((72, 72), text)
    return document.tobytes()


# --- storage ------------------------------------------------------------------


async def test_local_storage_roundtrip(storage: LocalDiskStorage) -> None:
    await storage.save("tenant-a/doc/file.txt", b"hello")
    assert await storage.load("tenant-a/doc/file.txt") == b"hello"
    await storage.delete("tenant-a/doc/file.txt")
    with pytest.raises(FileNotFoundError):
        await storage.load("tenant-a/doc/file.txt")


async def test_local_storage_rejects_path_escape(storage: LocalDiskStorage) -> None:
    with pytest.raises(ValueError, match="escapes"):
        await storage.save("../outside.txt", b"nope")


# --- parsing & chunking -------------------------------------------------------


def test_pdf_pages_extracted() -> None:
    pages = extract_pages(make_pdf(["first page text", "second page text"]), "application/pdf")
    assert len(pages) == 2
    assert pages[0].number == 1
    assert "first page" in pages[0].text


def test_chunking_overlaps_and_keeps_pages() -> None:
    words = " ".join(f"word{i}" for i in range(1000))
    pages = extract_pages(words.encode(), "text/plain")
    chunks = chunk_pages(pages)

    assert len(chunks) >= 2
    assert all(c.page is None for c in chunks)
    assert [c.position for c in chunks] == list(range(len(chunks)))
    # Overlap: the start of chunk 2 repeats the tail of chunk 1.
    tail = chunks[0].content.split()[-10:]
    assert all(word in chunks[1].content for word in tail)


# --- upload endpoint ------------------------------------------------------------


async def test_upload_txt_enqueues_ingestion(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    overrides: None,
    queue: RecordingQueue,
    storage: LocalDiskStorage,
) -> None:
    response = await client.post(
        "/documents",
        files={"file": ("notes.txt", io.BytesIO(b"some interesting notes"), "text/plain")},
        headers=org_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["name"] == "notes.txt"

    assert len(queue.jobs) == 1
    job_name, kwargs = queue.jobs[0]
    assert job_name == "ingest_document_job"
    assert kwargs["document_id"] == body["id"]

    stored = await storage.load(f"{org_headers['X-Org-Id']}/{body['id']}/notes.txt")
    assert stored == b"some interesting notes"


async def test_upload_rejects_unsupported_type(
    client: httpx.AsyncClient, org_headers: dict[str, str], overrides: None
) -> None:
    response = await client.post(
        "/documents",
        files={"file": ("v.mp4", io.BytesIO(b"x"), "video/mp4")},
        headers=org_headers,
    )
    assert response.status_code == 415


async def test_upload_rejects_oversized_file(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    overrides: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 10)
    response = await client.post(
        "/documents",
        files={"file": ("big.txt", io.BytesIO(b"x" * 11), "text/plain")},
        headers=org_headers,
    )
    assert response.status_code == 413


# --- ingestion pipeline ---------------------------------------------------------


async def seed_document(
    db_session: AsyncSession,
    storage: LocalDiskStorage,
    tenant: TenantContext,
    data: bytes,
    mime_type: str,
) -> Document:
    document = Document(
        tenant_id=tenant.organization_id,
        name="test-doc",
        mime_type=mime_type,
        size_bytes=len(data),
        created_by="alice",
        storage_path=f"{tenant.organization_id}/test-doc",
    )
    db_session.add(document)
    await db_session.flush()
    await storage.save(document.storage_path, data)
    return document


async def test_ingest_pdf_end_to_end(
    db_session: AsyncSession, storage: LocalDiskStorage, tenant: TenantContext
) -> None:
    document = await seed_document(
        db_session, storage, tenant, make_pdf(["alpha " * 50, "beta " * 50]), "application/pdf"
    )

    await ingest_document(
        db_session, storage, FakeEmbeddingProvider(dimension=1024), tenant, document.id
    )

    assert document.status == "ready"
    chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
    assert len(chunks) == 2  # one small chunk per page
    assert {c.page for c in chunks} == {1, 2}
    assert all(len(c.embedding) == 1024 for c in chunks)

    # Embedding usage was recorded under the ingestion feature.
    from src.domains.usage.models import LLMUsage

    usage_rows = (await db_session.execute(select(LLMUsage))).scalars().all()
    assert len(usage_rows) == 1
    assert usage_rows[0].feature == "ingestion"


async def test_ingest_failure_marks_document_failed(
    db_session: AsyncSession, storage: LocalDiskStorage, tenant: TenantContext
) -> None:
    class ExplodingEmbedder(FakeEmbeddingProvider):
        async def embed(self, texts: list[str], input_type: str = "document"):  # type: ignore[override]
            raise ProviderUnavailable("voyage down")

    document = await seed_document(db_session, storage, tenant, b"some text content", "text/plain")

    with pytest.raises(ProviderUnavailable):
        await ingest_document(db_session, storage, ExplodingEmbedder(), tenant, document.id)

    await db_session.refresh(document)
    assert document.status == "failed"
    assert "voyage down" in (document.error or "")


async def test_reingest_replaces_chunks(
    db_session: AsyncSession, storage: LocalDiskStorage, tenant: TenantContext
) -> None:
    document = await seed_document(
        db_session, storage, tenant, b"hello world content", "text/plain"
    )
    embedder = FakeEmbeddingProvider(dimension=1024)

    await ingest_document(db_session, storage, embedder, tenant, document.id)
    await ingest_document(db_session, storage, embedder, tenant, document.id)

    chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
    assert len(chunks) == 1  # not duplicated


async def test_delete_document_removes_chunks_and_blob(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    overrides: None,
    db_session: AsyncSession,
    storage: LocalDiskStorage,
    tenant: TenantContext,
) -> None:
    document = await seed_document(db_session, storage, tenant, b"to be deleted", "text/plain")
    await ingest_document(
        db_session, storage, FakeEmbeddingProvider(dimension=1024), tenant, document.id
    )

    response = await client.delete(f"/documents/{document.id}", headers=org_headers)
    assert response.status_code == 204

    chunks = (await db_session.execute(select(DocumentChunk))).scalars().all()
    assert chunks == []
    with pytest.raises(FileNotFoundError):
        await storage.load(f"{tenant.organization_id}/test-doc")


async def test_document_of_other_tenant_is_404(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    overrides: None,
    db_session: AsyncSession,
    auth_headers: AuthHeaderFactory,
) -> None:
    other = Organization(name="Other")
    other.memberships = [Membership(user_id="bob", role="owner")]
    db_session.add(other)
    await db_session.flush()

    response = await client.get(f"/documents/{uuid.uuid4()}", headers=org_headers)
    assert response.status_code == 404


async def test_upload_persists_storage_path_and_delete_works_end_to_end(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    overrides: None,
    db_session: AsyncSession,
    storage: LocalDiskStorage,
) -> None:
    """Regression: db.refresh() after a post-flush mutation silently reverted
    storage_path to '' — files became undeletable (500 on DELETE)."""
    response = await client.post(
        "/documents",
        files={"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=org_headers,
    )
    document_id = response.json()["id"]

    row = (await db_session.execute(select(Document))).scalar_one()
    assert row.storage_path == f"{org_headers['X-Org-Id']}/{document_id}/note.txt"

    response = await client.delete(f"/documents/{document_id}", headers=org_headers)
    assert response.status_code == 204
    with pytest.raises(FileNotFoundError):
        await storage.load(row.storage_path)


async def test_storage_refuses_empty_and_root_paths(storage: LocalDiskStorage) -> None:
    with pytest.raises(ValueError, match="Empty"):
        await storage.delete("")
    with pytest.raises(ValueError, match="storage root"):
        await storage.delete(".")
