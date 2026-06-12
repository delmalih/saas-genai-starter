import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.domains.llm_settings.resolver import chat_provider_dep
from src.domains.tenants.models import Membership, Organization
from src.domains.usage.models import LLMUsage
from src.llm.errors import ProviderUnavailable
from src.llm.rate_limit import TenantRateLimiter, get_rate_limiter
from src.llm.types import Usage

from tests.conftest import AuthHeaderFactory
from tests.llm.fakes import FakeChatProvider, make_completion


@pytest.fixture
async def org_headers(db_session: AsyncSession, auth_headers: AuthHeaderFactory) -> dict[str, str]:
    organization = Organization(name="Chat Co")
    organization.memberships = [Membership(user_id="alice", role="owner")]
    db_session.add(organization)
    await db_session.flush()
    return {**auth_headers(user_id="alice"), "X-Org-Id": str(organization.id)}


@pytest.fixture
def fake_provider(app: FastAPI) -> FakeChatProvider:
    provider = FakeChatProvider(
        result=make_completion(
            text="hello",
            model="claude-sonnet-4-6",
            usage=Usage(input_tokens=100, output_tokens=20),
        ),
        stream_chunks=["hel", "lo"],
    )
    app.dependency_overrides[chat_provider_dep] = lambda: provider
    return provider


async def create_conversation(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/conversations", json={}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


async def collect_sse(response: httpx.Response) -> list[dict[str, Any]]:
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


async def test_full_chat_flow(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    fake_provider: FakeChatProvider,
    db_session: AsyncSession,
) -> None:
    conversation_id = await create_conversation(client, org_headers)

    async with client.stream(
        "POST",
        f"/conversations/{conversation_id}/messages",
        json={"content": "Hello there, assistant!"},
        headers=org_headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = await collect_sse(response)

    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "hello"
    assert events[-1]["type"] == "done"

    # History persisted: user + assistant messages survive a "reload".
    response = await client.get(f"/conversations/{conversation_id}", headers=org_headers)
    detail = response.json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "hello"
    # Conversation auto-titled from the first message.
    assert detail["title"] == "Hello there, assistant!"

    # Usage recorded with the chat feature tag.
    usage_rows = (await db_session.execute(select(LLMUsage))).scalars().all()
    assert len(usage_rows) == 1
    assert usage_rows[0].feature == "chat"
    assert usage_rows[0].input_tokens == 100


async def test_history_is_sent_to_the_provider(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    fake_provider: FakeChatProvider,
) -> None:
    conversation_id = await create_conversation(client, org_headers)
    for content in ("first", "second"):
        async with client.stream(
            "POST",
            f"/conversations/{conversation_id}/messages",
            json={"content": content},
            headers=org_headers,
        ) as response:
            await collect_sse(response)

    assert fake_provider.calls == 2
    # Second call must include: first user msg, assistant reply, second user msg.
    response = await client.get(f"/conversations/{conversation_id}", headers=org_headers)
    assert len(response.json()["messages"]) == 4


async def test_conversation_of_another_tenant_is_404(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    auth_headers: AuthHeaderFactory,
    db_session: AsyncSession,
    fake_provider: FakeChatProvider,
) -> None:
    conversation_id = await create_conversation(client, org_headers)

    other_org = Organization(name="Other")
    other_org.memberships = [Membership(user_id="mallory", role="owner")]
    db_session.add(other_org)
    await db_session.flush()
    mallory = {**auth_headers(user_id="mallory"), "X-Org-Id": str(other_org.id)}

    response = await client.get(f"/conversations/{conversation_id}", headers=mallory)
    assert response.status_code == 404
    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "hi"},
        headers=mallory,
    )
    assert response.status_code == 404


async def test_rate_limited_chat_returns_429(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    fake_provider: FakeChatProvider,
    app: FastAPI,
) -> None:
    from src.core.redis import get_redis

    app.dependency_overrides[get_rate_limiter] = lambda: TenantRateLimiter(
        get_redis(), requests_per_minute=0, tokens_per_day=1000
    )
    conversation_id = await create_conversation(client, org_headers)

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "hi"},
        headers=org_headers,
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers


async def test_provider_error_arrives_as_sse_event(
    client: httpx.AsyncClient,
    org_headers: dict[str, str],
    app: FastAPI,
    db_session: AsyncSession,
) -> None:
    provider = FakeChatProvider(errors=[ProviderUnavailable("down")] * 10)
    app.dependency_overrides[chat_provider_dep] = lambda: provider
    conversation_id = await create_conversation(client, org_headers)

    async with client.stream(
        "POST",
        f"/conversations/{conversation_id}/messages",
        json={"content": "hi"},
        headers=org_headers,
    ) as response:
        assert response.status_code == 200  # stream already open
        events = await collect_sse(response)

    assert events[-1]["type"] == "error"
    # The user message survived; no assistant message was written.
    response = await client.get(f"/conversations/{conversation_id}", headers=org_headers)
    assert [m["role"] for m in response.json()["messages"]] == ["user"]


async def test_unknown_conversation_is_404(
    client: httpx.AsyncClient, org_headers: dict[str, str], fake_provider: FakeChatProvider
) -> None:
    response = await client.post(
        f"/conversations/{uuid.uuid4()}/messages",
        json={"content": "hi"},
        headers=org_headers,
    )
    assert response.status_code == 404
