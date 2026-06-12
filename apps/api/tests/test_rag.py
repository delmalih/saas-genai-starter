import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.storage import LocalDiskStorage
from src.core.tenancy import TenantContext
from src.domains.chat.models import ChatMessage
from src.domains.documents.ingestion import ingest_document
from src.domains.documents.retrieval import RetrievalService
from src.domains.tenants.models import Membership, Organization
from src.domains.usage.models import LLMUsage
from src.llm.factory import chat_provider_dep, get_embedding_provider
from src.llm.types import ToolCall, Usage

from tests.conftest import AuthHeaderFactory
from tests.llm.fakes import FakeChatProvider, FakeEmbeddingProvider, make_completion


@pytest.fixture
async def tenant(db_session: AsyncSession) -> TenantContext:
    organization = Organization(name="RAG Co")
    organization.memberships = [Membership(user_id="alice", role="owner")]
    db_session.add(organization)
    await db_session.flush()
    return TenantContext(organization_id=organization.id, user_id="alice", role="owner")


@pytest.fixture
def org_headers(tenant: TenantContext, auth_headers: AuthHeaderFactory) -> dict[str, str]:
    return {**auth_headers(user_id="alice"), "X-Org-Id": str(tenant.organization_id)}


@pytest.fixture
def embedder(app: FastAPI) -> FakeEmbeddingProvider:
    fake = FakeEmbeddingProvider(dimension=1024)
    app.dependency_overrides[get_embedding_provider] = lambda: fake
    return fake


@pytest.fixture
async def ready_document(
    db_session: AsyncSession,
    tenant: TenantContext,
    tmp_path: Any,
    embedder: FakeEmbeddingProvider,
) -> None:
    from src.domains.documents.models import Document

    storage = LocalDiskStorage(tmp_path)
    document = Document(
        tenant_id=tenant.organization_id,
        name="handbook.txt",
        mime_type="text/plain",
        size_bytes=100,
        created_by="alice",
        storage_path="x/handbook.txt",
    )
    db_session.add(document)
    await db_session.flush()
    await storage.save(
        "x/handbook.txt", b"The vacation policy grants 25 days per year to all employees."
    )
    await ingest_document(db_session, storage, embedder, tenant, document.id)


# --- retrieval (SGS-033) -------------------------------------------------------


async def test_retrieval_returns_citations(
    db_session: AsyncSession,
    tenant: TenantContext,
    ready_document: None,
    embedder: FakeEmbeddingProvider,
) -> None:
    retrieval = RetrievalService(db_session, tenant, embedder)
    citations = await retrieval.search("vacation policy", created_by="alice")

    assert citations
    top = citations[0]
    assert top.document_name == "handbook.txt"
    assert "vacation policy" in top.snippet
    assert 0 <= top.score <= 1


async def test_retrieval_is_tenant_scoped(
    db_session: AsyncSession,
    tenant: TenantContext,
    ready_document: None,
    embedder: FakeEmbeddingProvider,
) -> None:
    other = Organization(name="Other")
    other.memberships = [Membership(user_id="bob", role="owner")]
    db_session.add(other)
    await db_session.flush()
    other_tenant = TenantContext(organization_id=other.id, user_id="bob", role="owner")

    citations = await RetrievalService(db_session, other_tenant, embedder).search(
        "vacation policy", created_by="bob"
    )
    assert citations == []


# --- RAG chat (SGS-034) ---------------------------------------------------------


def tool_use_completion(query: str) -> Any:
    return make_completion(
        text="",
        model="claude-sonnet-4-6",
        stop_reason="tool_use",
        usage=Usage(input_tokens=50, output_tokens=10),
        tool_calls=[ToolCall(id="toolu_1", name="search_documents", arguments={"query": query})],
    )


async def collect_sse(response: httpx.Response) -> list[dict[str, Any]]:
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


async def start_conversation(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/conversations", json={}, headers=headers)
    return response.json()["id"]


async def test_rag_chat_with_citations(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    ready_document: None,
    app: FastAPI,
    db_session: AsyncSession,
) -> None:
    provider = FakeChatProvider(
        script=[
            tool_use_completion("vacation policy"),
            make_completion(
                text="You get 25 days.",
                model="claude-sonnet-4-6",
                usage=Usage(input_tokens=200, output_tokens=30),
            ),
        ],
        stream_chunks=["You get ", "25 days."],
    )
    app.dependency_overrides[chat_provider_dep] = lambda: provider
    conversation_id = await start_conversation(client, org_headers)

    async with client.stream(
        "POST",
        f"/conversations/{conversation_id}/messages",
        json={"content": "How many vacation days do I get?"},
        headers=org_headers,
    ) as response:
        events = await collect_sse(response)

    types = [e["type"] for e in events]
    assert "tool_use" in types
    done = events[-1]
    assert done["type"] == "done"
    assert done["citations"]
    assert done["citations"][0]["document_name"] == "handbook.txt"

    # Tools were offered to the model; tool results were sent back.
    assert provider.received[0]["tools"] is not None
    second_call_messages = provider.received[1]["messages"]
    assert any(
        isinstance(m.content, list) and any(b.get("type") == "tool_result" for b in m.content)
        for m in second_call_messages
    )

    # Assistant message persisted with citations; usage tagged rag.
    messages = (await db_session.execute(select(ChatMessage))).scalars().all()
    assistant = next(m for m in messages if m.role == "assistant")
    assert assistant.citations and assistant.citations[0]["document_name"] == "handbook.txt"

    usage_rows = (await db_session.execute(select(LLMUsage))).scalars().all()
    rag_rows = [r for r in usage_rows if r.feature == "rag"]
    assert len(rag_rows) == 2  # one per agent round


async def test_chat_without_documents_has_no_tools(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    embedder: FakeEmbeddingProvider,
    app: FastAPI,
    db_session: AsyncSession,
) -> None:
    provider = FakeChatProvider(result=make_completion(text="hello", model="claude-sonnet-4-6"))
    app.dependency_overrides[chat_provider_dep] = lambda: provider
    conversation_id = await start_conversation(client, org_headers)

    async with client.stream(
        "POST",
        f"/conversations/{conversation_id}/messages",
        json={"content": "hi"},
        headers=org_headers,
    ) as response:
        events = await collect_sse(response)

    assert events[-1]["type"] == "done"
    assert events[-1]["citations"] == []
    assert provider.received[0]["tools"] is None

    usage_rows = (await db_session.execute(select(LLMUsage))).scalars().all()
    assert all(r.feature == "chat" for r in usage_rows)


# --- metadata extraction (SGS-035) ----------------------------------------------


async def test_metadata_extracted_on_ingestion(
    db_session: AsyncSession,
    tenant: TenantContext,
    tmp_path: Any,
) -> None:
    from src.domains.documents.models import Document

    storage = LocalDiskStorage(tmp_path)
    document = Document(
        tenant_id=tenant.organization_id,
        name="paper.txt",
        mime_type="text/plain",
        size_bytes=50,
        created_by="alice",
        storage_path="x/paper.txt",
    )
    db_session.add(document)
    await db_session.flush()
    await storage.save("x/paper.txt", b"A research paper about retrieval augmented generation.")

    chat = FakeChatProvider(
        result=make_completion(
            text=json.dumps(
                {
                    "title": "RAG Research Paper",
                    "language": "en",
                    "summary": "A paper about RAG.",
                    "topics": ["rag", "retrieval"],
                }
            ),
            model="claude-sonnet-4-6",
        )
    )
    await ingest_document(
        db_session,
        storage,
        FakeEmbeddingProvider(dimension=1024),
        tenant,
        document.id,
        chat_provider=chat,
    )

    assert document.status == "ready"
    assert document.title == "RAG Research Paper"
    assert document.topics == ["rag", "retrieval"]
    assert chat.received[0]["json_schema"] is not None

    usage_rows = (await db_session.execute(select(LLMUsage))).scalars().all()
    assert {r.feature for r in usage_rows} == {"ingestion", "extraction"}


async def test_metadata_failure_does_not_fail_ingestion(
    db_session: AsyncSession,
    tenant: TenantContext,
    tmp_path: Any,
) -> None:
    from src.domains.documents.models import Document

    storage = LocalDiskStorage(tmp_path)
    document = Document(
        tenant_id=tenant.organization_id,
        name="doc.txt",
        mime_type="text/plain",
        size_bytes=20,
        created_by="alice",
        storage_path="x/doc.txt",
    )
    db_session.add(document)
    await db_session.flush()
    await storage.save("x/doc.txt", b"plain content here")

    chat = FakeChatProvider(result=make_completion(text="NOT JSON", model="claude-sonnet-4-6"))
    await ingest_document(
        db_session,
        storage,
        FakeEmbeddingProvider(dimension=1024),
        tenant,
        document.id,
        chat_provider=chat,
    )

    assert document.status == "ready"
    assert document.title is None
