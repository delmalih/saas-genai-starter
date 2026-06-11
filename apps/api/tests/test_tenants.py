import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.domains.tenants.models import Membership, Organization

from tests.conftest import AuthHeaderFactory


@pytest.fixture
async def acme_org(db_session: AsyncSession) -> Organization:
    """An org with the full role matrix: alice=owner, bob=admin, carol/dave=member."""
    organization = Organization(name="Acme")
    organization.memberships = [
        Membership(user_id="alice", role="owner"),
        Membership(user_id="bob", role="admin"),
        Membership(user_id="carol", role="member"),
        Membership(user_id="dave", role="member"),
    ]
    db_session.add(organization)
    await db_session.flush()
    return organization


async def test_personal_org_autocreated_on_first_call(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory
) -> None:
    headers = auth_headers(user_id="newcomer", name="New Comer")
    response = await client.get("/organizations", headers=headers)
    assert response.status_code == 200
    organizations = response.json()
    assert len(organizations) == 1
    assert organizations[0]["name"] == "New Comer's workspace"
    assert organizations[0]["role"] == "owner"

    # Idempotent: a second call does not create another one.
    response = await client.get("/organizations", headers=headers)
    assert len(response.json()) == 1


async def test_create_organization(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory
) -> None:
    response = await client.post(
        "/organizations", json={"name": "Side Project"}, headers=auth_headers()
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Side Project"
    assert response.json()["role"] == "owner"


async def test_member_cannot_rename_org(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.patch(
        f"/organizations/{acme_org.id}",
        json={"name": "Hijacked"},
        headers=auth_headers(user_id="carol"),
    )
    assert response.status_code == 403


async def test_admin_can_rename_org(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.patch(
        f"/organizations/{acme_org.id}",
        json={"name": "Acme Corp"},
        headers=auth_headers(user_id="bob"),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Acme Corp"


async def test_non_member_gets_404(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.get(
        f"/organizations/{acme_org.id}/members",
        headers=auth_headers(user_id="stranger"),
    )
    assert response.status_code == 404

    response = await client.get(
        f"/organizations/{uuid.uuid4()}/members", headers=auth_headers(user_id="alice")
    )
    assert response.status_code == 404


async def test_member_emails_resolved_from_auth_schema(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    db_session: AsyncSession,
) -> None:
    await db_session.execute(
        text(
            'INSERT INTO auth."user" (id, email, name) VALUES '
            "('alice', 'alice@acme.dev', 'Alice'), ('bob', 'bob@acme.dev', 'Bob')"
        )
    )
    response = await client.get(
        f"/organizations/{acme_org.id}/members", headers=auth_headers(user_id="alice")
    )
    assert response.status_code == 200
    by_user = {m["user_id"]: m for m in response.json()}
    assert len(by_user) == 4
    assert by_user["alice"]["email"] == "alice@acme.dev"
    assert by_user["bob"]["role"] == "admin"
    assert by_user["carol"]["email"] is None  # not seeded in the auth schema


async def test_member_cannot_change_roles(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.patch(
        f"/organizations/{acme_org.id}/members/dave",
        json={"role": "admin"},
        headers=auth_headers(user_id="carol"),
    )
    assert response.status_code == 403


async def test_admin_cannot_grant_owner(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.patch(
        f"/organizations/{acme_org.id}/members/carol",
        json={"role": "owner"},
        headers=auth_headers(user_id="bob"),
    )
    assert response.status_code == 403


async def test_admin_cannot_change_owner_role(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.patch(
        f"/organizations/{acme_org.id}/members/alice",
        json={"role": "member"},
        headers=auth_headers(user_id="bob"),
    )
    assert response.status_code == 403


async def test_owner_can_promote_to_admin(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.patch(
        f"/organizations/{acme_org.id}/members/carol",
        json={"role": "admin"},
        headers=auth_headers(user_id="alice"),
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_admin_can_remove_member(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.delete(
        f"/organizations/{acme_org.id}/members/carol",
        headers=auth_headers(user_id="bob"),
    )
    assert response.status_code == 204


async def test_admin_cannot_remove_admin_or_owner(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    db_session: AsyncSession,
) -> None:
    db_session.add(Membership(organization_id=acme_org.id, user_id="erin", role="admin"))
    await db_session.flush()

    for target in ("alice", "erin"):
        response = await client.delete(
            f"/organizations/{acme_org.id}/members/{target}",
            headers=auth_headers(user_id="bob"),
        )
        assert response.status_code == 403, target


async def test_member_can_leave(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.delete(
        f"/organizations/{acme_org.id}/members/carol",
        headers=auth_headers(user_id="carol"),
    )
    assert response.status_code == 204


async def test_last_owner_cannot_leave_or_be_demoted(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    headers = auth_headers(user_id="alice")
    response = await client.delete(f"/organizations/{acme_org.id}/members/alice", headers=headers)
    assert response.status_code == 409

    response = await client.patch(
        f"/organizations/{acme_org.id}/members/alice",
        json={"role": "member"},
        headers=headers,
    )
    assert response.status_code == 409


async def test_owner_transfer_then_leave(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    headers = auth_headers(user_id="alice")
    response = await client.patch(
        f"/organizations/{acme_org.id}/members/bob",
        json={"role": "owner"},
        headers=headers,
    )
    assert response.status_code == 200

    response = await client.delete(f"/organizations/{acme_org.id}/members/alice", headers=headers)
    assert response.status_code == 204
