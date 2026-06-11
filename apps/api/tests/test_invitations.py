import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.email import get_email_sender
from src.domains.tenants.models import Membership, Organization

from tests.conftest import AuthHeaderFactory


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text})


@pytest.fixture
def email_outbox(app: FastAPI) -> RecordingEmailSender:
    outbox = RecordingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: outbox
    return outbox


@pytest.fixture
async def acme_org(db_session: AsyncSession) -> Organization:
    organization = Organization(name="Acme")
    organization.memberships = [
        Membership(user_id="alice", role="owner"),
        Membership(user_id="carol", role="member"),
    ]
    db_session.add(organization)
    await db_session.flush()
    return organization


def extract_token(email_text: str) -> str:
    match = re.search(r"/invite/([A-Za-z0-9_-]+)", email_text)
    assert match, f"no invite link in: {email_text}"
    return match.group(1)


async def invite(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    org_id: str,
    email: str = "bob@acme.dev",
    role: str = "member",
) -> httpx.Response:
    return await client.post(
        f"/organizations/{org_id}/invitations",
        json={"email": email, "role": role},
        headers=headers,
    )


async def test_full_invite_accept_flow(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    email_outbox: RecordingEmailSender,
) -> None:
    response = await invite(client, auth_headers(user_id="alice"), str(acme_org.id))
    assert response.status_code == 201
    assert response.json()["email"] == "bob@acme.dev"

    assert len(email_outbox.sent) == 1
    assert email_outbox.sent[0]["to"] == "bob@acme.dev"
    token = extract_token(email_outbox.sent[0]["text"])

    response = await client.post(
        "/invitations/accept",
        json={"token": token},
        headers=auth_headers(user_id="bob", email="bob@acme.dev"),
    )
    assert response.status_code == 200
    assert response.json()["organization_name"] == "Acme"
    assert response.json()["role"] == "member"

    # Bob is now a member.
    response = await client.get(
        f"/organizations/{acme_org.id}/members", headers=auth_headers(user_id="bob")
    )
    assert response.status_code == 200

    # Single use: a second accept fails.
    response = await client.post(
        "/invitations/accept",
        json={"token": token},
        headers=auth_headers(user_id="bob2", email="bob@acme.dev"),
    )
    assert response.status_code == 400
    assert "already been used" in response.json()["error"]["message"]


async def test_member_cannot_invite(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    email_outbox: RecordingEmailSender,
) -> None:
    response = await invite(client, auth_headers(user_id="carol"), str(acme_org.id))
    assert response.status_code == 403
    assert email_outbox.sent == []


async def test_cannot_invite_existing_member(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    email_outbox: RecordingEmailSender,
    db_session: AsyncSession,
) -> None:
    await db_session.execute(
        text(
            'INSERT INTO auth."user" (id, email, name) '
            "VALUES ('carol', 'carol@acme.dev', 'Carol')"
        )
    )
    response = await invite(
        client, auth_headers(user_id="alice"), str(acme_org.id), email="Carol@acme.dev"
    )
    assert response.status_code == 409


async def test_email_mismatch_rejected(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    email_outbox: RecordingEmailSender,
) -> None:
    await invite(client, auth_headers(user_id="alice"), str(acme_org.id))
    token = extract_token(email_outbox.sent[0]["text"])

    response = await client.post(
        "/invitations/accept",
        json={"token": token},
        headers=auth_headers(user_id="mallory", email="mallory@evil.dev"),
    )
    assert response.status_code == 403


async def test_expired_invitation_rejected(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    email_outbox: RecordingEmailSender,
    db_session: AsyncSession,
) -> None:
    await invite(client, auth_headers(user_id="alice"), str(acme_org.id))
    token = extract_token(email_outbox.sent[0]["text"])

    await db_session.execute(
        text("UPDATE invitations SET expires_at = :past"),
        {"past": datetime.now(UTC) - timedelta(days=1)},
    )
    response = await client.post(
        "/invitations/accept",
        json={"token": token},
        headers=auth_headers(user_id="bob", email="bob@acme.dev"),
    )
    assert response.status_code == 400
    assert "expired" in response.json()["error"]["message"]


async def test_revoked_invitation_rejected(
    client: httpx.AsyncClient,
    auth_headers: AuthHeaderFactory,
    acme_org: Organization,
    email_outbox: RecordingEmailSender,
) -> None:
    response = await invite(client, auth_headers(user_id="alice"), str(acme_org.id))
    invitation_id = response.json()["id"]
    token = extract_token(email_outbox.sent[0]["text"])

    headers = auth_headers(user_id="alice")
    response = await client.delete(
        f"/organizations/{acme_org.id}/invitations/{invitation_id}", headers=headers
    )
    assert response.status_code == 204

    # Gone from the pending list, and the token is dead.
    response = await client.get(f"/organizations/{acme_org.id}/invitations", headers=headers)
    assert response.json() == []

    response = await client.post(
        "/invitations/accept",
        json={"token": token},
        headers=auth_headers(user_id="bob", email="bob@acme.dev"),
    )
    assert response.status_code == 400
    assert "revoked" in response.json()["error"]["message"]


async def test_garbage_token_rejected(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory
) -> None:
    response = await client.post(
        "/invitations/accept",
        json={"token": "x" * 43},
        headers=auth_headers(),
    )
    assert response.status_code == 400


async def test_pending_list_requires_admin(
    client: httpx.AsyncClient, auth_headers: AuthHeaderFactory, acme_org: Organization
) -> None:
    response = await client.get(
        f"/organizations/{acme_org.id}/invitations",
        headers=auth_headers(user_id="carol"),
    )
    assert response.status_code == 403
