import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.tenancy import TenantContext
from src.domains.tenants.models import Membership, Organization
from src.domains.usage.models import LLMUsage
from src.domains.usage.repository import UsageRepository
from src.domains.usage.service import UsageService
from src.llm.errors import ProviderUnavailable
from src.llm.pricing import cost_for
from src.llm.types import Message, StreamEnd, TextDelta, Usage

from tests.llm.fakes import FakeChatProvider, make_completion

USER_MESSAGE = [Message(role="user", content="hi")]


# --- pricing -----------------------------------------------------------------


def test_cost_matches_pricing_table() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    assert cost_for("claude-sonnet-4-6", usage) == Decimal("3.000000")

    usage = Usage(
        input_tokens=10_000,
        output_tokens=2_000,
        cache_read_tokens=80_000,
        cache_write_tokens=4_000,
    )
    # 10kx$3 + 2kx$15 + 80kx$0.30 + 4kx$3.75 per MTok
    expected = Decimal("0.030000") + Decimal("0.030000") + Decimal("0.024000") + Decimal("0.015000")
    assert cost_for("claude-sonnet-4-6", usage) == expected


def test_unknown_model_costs_zero() -> None:
    assert cost_for("some-future-model", Usage(input_tokens=1000)) == Decimal("0")


# --- tracked calls -----------------------------------------------------------


@pytest.fixture
async def tenant(db_session: AsyncSession) -> TenantContext:
    organization = Organization(name="Usage Co")
    organization.memberships = [Membership(user_id="alice", role="owner")]
    db_session.add(organization)
    await db_session.flush()
    return TenantContext(organization_id=organization.id, user_id="alice", role="owner")


async def fetch_rows(db_session: AsyncSession) -> list[LLMUsage]:
    result = await db_session.execute(select(LLMUsage).order_by(LLMUsage.created_at))
    return list(result.scalars().all())


async def test_tracked_complete_records_cost(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    completion = make_completion(
        model="claude-sonnet-4-6",
        usage=Usage(input_tokens=1000, output_tokens=500),
    )
    service = UsageService(db_session, tenant)

    await service.tracked_complete(
        FakeChatProvider(result=completion), "chat", "alice", USER_MESSAGE
    )

    (row,) = await fetch_rows(db_session)
    assert row.feature == "chat"
    assert row.model == "claude-sonnet-4-6"
    assert row.status == "ok"
    assert row.input_tokens == 1000
    assert row.cost_usd == Decimal("0.010500")  # 1kx$3 + 0.5kx$15 per MTok
    assert row.tenant_id == tenant.organization_id


async def test_tracked_complete_records_failures(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    service = UsageService(db_session, tenant)
    provider = FakeChatProvider(errors=[ProviderUnavailable("down")])

    with pytest.raises(ProviderUnavailable):
        await service.tracked_complete(provider, "chat", "alice", USER_MESSAGE)

    (row,) = await fetch_rows(db_session)
    assert row.status == "error"
    assert row.cost_usd == Decimal("0")


async def test_tracked_stream_records_final_usage(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    completion = make_completion(
        model="claude-sonnet-4-6", usage=Usage(input_tokens=200, output_tokens=50)
    )
    service = UsageService(db_session, tenant)

    events = [
        event
        async for event in service.tracked_stream(
            FakeChatProvider(result=completion), "rag", "alice", USER_MESSAGE
        )
    ]

    assert isinstance(events[-1], StreamEnd)
    (row,) = await fetch_rows(db_session)
    assert row.feature == "rag"
    assert row.status == "ok"
    assert row.output_tokens == 50


async def test_client_disconnect_records_partial_usage(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    """Closing the generator mid-stream (client disconnect) still writes a row."""
    provider = FakeChatProvider(stream_chunks=["x" * 40, "y" * 40])
    service = UsageService(db_session, tenant)

    stream = service.tracked_stream(provider, "chat", "alice", USER_MESSAGE)
    first = await anext(aiter(stream))
    assert isinstance(first, TextDelta)
    await stream.aclose()  # simulates the SSE client going away

    (row,) = await fetch_rows(db_session)
    assert row.status == "disconnected"
    assert row.output_tokens == 10  # 40 chars streamed / 4 chars per token


async def test_midstream_error_records_partial_usage(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    class ExplodingProvider(FakeChatProvider):
        async def stream(self, *args: object, **kwargs: object):  # type: ignore[override]
            yield TextDelta(text="z" * 80)
            raise ProviderUnavailable("connection reset")

    service = UsageService(db_session, tenant)

    with pytest.raises(ProviderUnavailable):
        async for _ in service.tracked_stream(ExplodingProvider(), "chat", "alice", USER_MESSAGE):
            pass

    (row,) = await fetch_rows(db_session)
    assert row.status == "error"
    assert row.output_tokens == 20


# --- aggregation -------------------------------------------------------------


async def test_daily_costs_grouped_and_tenant_scoped(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    other_org = Organization(name="Other Co")
    other_org.memberships = [Membership(user_id="bob", role="owner")]
    db_session.add(other_org)
    await db_session.flush()

    today = datetime.now(UTC).replace(hour=12)
    yesterday = today - timedelta(days=1)

    def row(feature: str, created_at: datetime, cost: str, org_id: uuid.UUID) -> LLMUsage:
        return LLMUsage(
            tenant_id=org_id,
            feature=feature,
            model="claude-sonnet-4-6",
            cost_usd=Decimal(cost),
            input_tokens=100,
            output_tokens=10,
            created_by="alice",
            created_at=created_at,
        )

    db_session.add_all(
        [
            row("chat", yesterday, "0.01", tenant.organization_id),
            row("chat", today, "0.02", tenant.organization_id),
            row("rag", today, "0.05", tenant.organization_id),
            row("chat", today, "9.99", other_org.id),  # must not leak
        ]
    )
    await db_session.flush()

    repo = UsageRepository(db_session, tenant)
    start = yesterday - timedelta(hours=13)
    end = today + timedelta(days=1)

    daily = await repo.daily_costs(start, end)
    assert len(daily) == 3
    by_key = {(d.day, d.feature): d for d in daily}
    assert by_key[(today.date(), "rag")].cost_usd == Decimal("0.05")
    assert by_key[(today.date(), "chat")].calls == 1

    total = await repo.total_cost(start, end)
    assert total == Decimal("0.08")


def test_cache_read_is_discounted_10x() -> None:
    uncached = cost_for("claude-sonnet-4-6", Usage(input_tokens=100_000))
    cached = cost_for("claude-sonnet-4-6", Usage(cache_read_tokens=100_000))
    assert cached == uncached / 10


# --- endpoints ---------------------------------------------------------------


@pytest.fixture
async def org_headers(db_session: AsyncSession, auth_headers, tenant: TenantContext):
    return {**auth_headers(user_id="alice"), "X-Org-Id": str(tenant.organization_id)}


async def test_usage_endpoints_match_aggregates(
    client, org_headers, db_session: AsyncSession, tenant: TenantContext
) -> None:
    now = datetime.now(UTC).replace(hour=12)
    db_session.add_all(
        [
            LLMUsage(
                tenant_id=tenant.organization_id,
                feature="chat",
                model="claude-sonnet-4-6",
                cost_usd=Decimal("0.25"),
                input_tokens=1000,
                output_tokens=200,
                created_by="alice",
                created_at=now,
            ),
            LLMUsage(
                tenant_id=tenant.organization_id,
                feature="rag",
                model="claude-sonnet-4-6",
                cost_usd=Decimal("0.10"),
                input_tokens=500,
                output_tokens=100,
                created_by="alice",
                created_at=now,
            ),
        ]
    )
    await db_session.flush()

    response = await client.get("/usage/daily", headers=org_headers)
    assert response.status_code == 200
    daily = response.json()
    assert len(daily) == 2
    assert {d["feature"] for d in daily} == {"chat", "rag"}
    assert sum(d["cost_usd"] for d in daily) == pytest.approx(0.35)

    response = await client.get("/usage/summary", headers=org_headers)
    summary = response.json()
    assert summary["total_cost_usd"] == pytest.approx(0.35)
    assert summary["limits"]["tokens_per_day"] > 0


async def test_usage_empty_tenant(client, org_headers) -> None:
    response = await client.get("/usage/daily", headers=org_headers)
    assert response.status_code == 200
    assert response.json() == []

    response = await client.get("/usage/summary", headers=org_headers)
    assert response.json()["total_cost_usd"] == 0


async def test_usage_invalid_range_is_400(client, org_headers) -> None:
    response = await client.get(
        "/usage/daily",
        params={"start": "2026-06-10", "end": "2026-06-01"},
        headers=org_headers,
    )
    assert response.status_code == 400
