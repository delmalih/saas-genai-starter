import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import get_settings
from src.core.errors import QuotaExceeded
from src.core.redis import get_redis
from src.domains.tenants.models import Membership, Organization
from src.domains.usage.models import LLMUsage
from src.llm.rate_limit import TenantRateLimiter

from tests.conftest import AuthHeaderFactory

ADMIN_EMAIL = "root@example.com"


@pytest.fixture(autouse=True)
def admin_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "admin_emails", f" {ADMIN_EMAIL.upper()}, other@x.dev ")


@pytest.fixture
async def seeded_org(db_session: AsyncSession) -> Organization:
    organization = Organization(name="Seeded Co")
    organization.memberships = [
        Membership(user_id="alice", role="owner"),
        Membership(user_id="bob", role="member"),
    ]
    db_session.add(organization)
    await db_session.flush()
    db_session.add(
        LLMUsage(
            tenant_id=organization.id,
            feature="chat",
            model="claude-sonnet-4-6",
            cost_usd=Decimal("1.25"),
            created_by="alice",
            created_at=datetime.now(UTC),
        )
    )
    await db_session.flush()
    return organization


async def test_non_admin_gets_404_not_403(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory
) -> None:
    response = await client.get(
        "/admin/organizations", headers=auth_headers(email="mortal@example.com")
    )
    assert response.status_code == 404


async def test_admin_sees_cross_tenant_stats(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, seeded_org: Organization
) -> None:
    # Allowlist matching is case-insensitive and whitespace-tolerant.
    response = await client.get("/admin/organizations", headers=auth_headers(email=ADMIN_EMAIL))
    assert response.status_code == 200
    org = next(o for o in response.json() if o["id"] == str(seeded_org.id))
    assert org["members"] == 2
    assert org["cost_30d_usd"] == pytest.approx(1.25)
    assert org["rate_limit_rpm_override"] is None


async def test_admin_sets_and_clears_limit_overrides(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, seeded_org: Organization
) -> None:
    headers = auth_headers(email=ADMIN_EMAIL)
    response = await client.patch(
        f"/admin/organizations/{seeded_org.id}/limits",
        json={"requests_per_minute": 5, "tokens_per_day": 1000},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["rate_limit_rpm_override"] == 5

    response = await client.patch(
        f"/admin/organizations/{seeded_org.id}/limits", json={}, headers=headers
    )
    assert response.json()["rate_limit_rpm_override"] is None


async def test_limiter_honors_overrides() -> None:
    limiter = TenantRateLimiter(get_redis(), requests_per_minute=100, tokens_per_day=10_000)
    tenant_id = uuid.uuid4()

    # Default limit (100/min) would allow this; the override (0) blocks it.
    with pytest.raises(QuotaExceeded):
        await limiter.check(tenant_id, rpm_override=0)
    # And clearing the override falls back to the server default.
    await limiter.check(tenant_id)
