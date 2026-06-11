import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.tenancy import TenantContext
from src.domains.chat.models import Conversation
from src.domains.chat.repository import ConversationRepository
from src.domains.tenants.models import Membership, Organization

from tests.conftest import AuthHeaderFactory


@pytest.fixture
async def two_tenants(db_session: AsyncSession) -> tuple[TenantContext, TenantContext]:
    org_a = Organization(name="Tenant A")
    org_a.memberships = [Membership(user_id="alice", role="owner")]
    org_b = Organization(name="Tenant B")
    org_b.memberships = [Membership(user_id="bob", role="owner")]
    db_session.add_all([org_a, org_b])
    await db_session.flush()
    return (
        TenantContext(organization_id=org_a.id, user_id="alice", role="owner"),
        TenantContext(organization_id=org_b.id, user_id="bob", role="owner"),
    )


async def test_cross_tenant_isolation(
    db_session: AsyncSession, two_tenants: tuple[TenantContext, TenantContext]
) -> None:
    """The core invariant: no repository method can ever cross tenants."""
    tenant_a, tenant_b = two_tenants
    repo_a = ConversationRepository(db_session, tenant_a)
    repo_b = ConversationRepository(db_session, tenant_b)

    conversation = repo_a.add(Conversation(title="secret plans", created_by="alice"))
    await db_session.flush()

    assert await repo_a.get(conversation.id) is not None
    assert await repo_b.get(conversation.id) is None
    assert [c.id for c in await repo_a.list_all()] == [conversation.id]
    assert await repo_b.list_all() == []


async def test_add_overwrites_forged_tenant_id(
    db_session: AsyncSession, two_tenants: tuple[TenantContext, TenantContext]
) -> None:
    tenant_a, tenant_b = two_tenants
    repo_a = ConversationRepository(db_session, tenant_a)

    forged = Conversation(title="forged", created_by="alice")
    forged.tenant_id = tenant_b.organization_id
    repo_a.add(forged)
    await db_session.flush()

    assert forged.tenant_id == tenant_a.organization_id


async def test_delete_refuses_foreign_entity(
    db_session: AsyncSession, two_tenants: tuple[TenantContext, TenantContext]
) -> None:
    tenant_a, tenant_b = two_tenants
    repo_b = ConversationRepository(db_session, tenant_b)

    conversation = ConversationRepository(db_session, tenant_a).add(
        Conversation(title="mine", created_by="alice")
    )
    await db_session.flush()

    with pytest.raises(ValueError, match="another tenant"):
        await repo_b.delete(conversation)


async def test_current_org_requires_header(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory
) -> None:
    response = await client.get("/organizations/current", headers=auth_headers())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


async def test_current_org_rejects_malformed_header(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory
) -> None:
    response = await client.get(
        "/organizations/current",
        headers={**auth_headers(), "X-Org-Id": "not-a-uuid"},
    )
    assert response.status_code == 400


async def test_current_org_404_for_non_member(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    two_tenants: tuple[TenantContext, TenantContext],
) -> None:
    _, tenant_b = two_tenants
    response = await client.get(
        "/organizations/current",
        headers={
            **auth_headers(user_id="alice"),
            "X-Org-Id": str(tenant_b.organization_id),
        },
    )
    assert response.status_code == 404

    response = await client.get(
        "/organizations/current",
        headers={**auth_headers(user_id="alice"), "X-Org-Id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


async def test_current_org_resolves_for_member(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    two_tenants: tuple[TenantContext, TenantContext],
) -> None:
    tenant_a, _ = two_tenants
    response = await client.get(
        "/organizations/current",
        headers={
            **auth_headers(user_id="alice"),
            "X-Org-Id": str(tenant_a.organization_id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(tenant_a.organization_id)
    assert body["role"] == "owner"
    assert body["name"] == "Tenant A"
