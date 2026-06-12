import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.crypto import decrypt_secret, encrypt_secret
from src.core.tenancy import TenantContext
from src.domains.llm_settings.models import OrgLLMSettings
from src.domains.tenants.models import Membership, Organization

from tests.conftest import AuthHeaderFactory

SECRET = "sk-ant-test-1234567890abcdEFGH"  # noqa: S105 — fake key for tests


@pytest.fixture
async def tenant(db_session: AsyncSession) -> TenantContext:
    organization = Organization(name="Keys Co")
    organization.memberships = [
        Membership(user_id="alice", role="owner"),
        Membership(user_id="carol", role="member"),
    ]
    db_session.add(organization)
    await db_session.flush()
    return TenantContext(organization_id=organization.id, user_id="alice", role="owner")


@pytest.fixture
def owner_headers(tenant: TenantContext, auth_headers: AuthHeaderFactory) -> dict[str, str]:
    return {**auth_headers(user_id="alice"), "X-Org-Id": str(tenant.organization_id)}


@pytest.fixture
def member_headers(tenant: TenantContext, auth_headers: AuthHeaderFactory) -> dict[str, str]:
    return {**auth_headers(user_id="carol"), "X-Org-Id": str(tenant.organization_id)}


def test_encryption_roundtrip() -> None:
    token = encrypt_secret(SECRET)
    assert token != SECRET
    assert decrypt_secret(token) == SECRET


async def test_defaults_for_fresh_org(
    client: httpx.AsyncClient, owner_headers: dict[str, str]
) -> None:
    response = await client.get("/llm-settings", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["chat_provider"] == "anthropic"
    assert body["chat_model"] == "claude-sonnet-4-6"
    assert body["keys"]["anthropic_api_key"] == {"is_set": False, "last4": None}


async def test_set_key_is_masked_and_encrypted(
    client: httpx.AsyncClient,
    owner_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    response = await client.put(
        "/llm-settings", json={"anthropic_api_key": SECRET}, headers=owner_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["keys"]["anthropic_api_key"]["is_set"] is True
    assert body["keys"]["anthropic_api_key"]["last4"] == SECRET[-4:]
    # The raw key never appears anywhere in the payload.
    assert SECRET not in response.text

    # And it is not stored in plaintext.
    row = (await db_session.execute(select(OrgLLMSettings))).scalar_one()
    assert row.anthropic_api_key_encrypted != SECRET
    assert SECRET not in (row.anthropic_api_key_encrypted or "")
    assert decrypt_secret(row.anthropic_api_key_encrypted or "") == SECRET

    # GET also stays masked.
    response = await client.get("/llm-settings", headers=owner_headers)
    assert SECRET not in response.text


async def test_clear_key_with_empty_string(
    client: httpx.AsyncClient, owner_headers: dict[str, str]
) -> None:
    await client.put("/llm-settings", json={"openai_api_key": SECRET}, headers=owner_headers)
    response = await client.put("/llm-settings", json={"openai_api_key": ""}, headers=owner_headers)
    assert response.json()["keys"]["openai_api_key"]["is_set"] is False


async def test_member_can_read_but_not_write(
    client: httpx.AsyncClient, member_headers: dict[str, str]
) -> None:
    response = await client.get("/llm-settings", headers=member_headers)
    assert response.status_code == 200

    response = await client.put(
        "/llm-settings", json={"chat_provider": "openai"}, headers=member_headers
    )
    assert response.status_code == 403


async def test_provider_switch_takes_default_model(
    client: httpx.AsyncClient, owner_headers: dict[str, str]
) -> None:
    response = await client.put(
        "/llm-settings", json={"chat_provider": "openai"}, headers=owner_headers
    )
    body = response.json()
    assert body["chat_provider"] == "openai"
    assert body["chat_model"] == "gpt-5.1-mini"


async def test_invalid_model_for_provider_is_400(
    client: httpx.AsyncClient, owner_headers: dict[str, str]
) -> None:
    response = await client.put(
        "/llm-settings",
        json={"chat_provider": "openai", "chat_model": "claude-sonnet-4-6"},
        headers=owner_headers,
    )
    assert response.status_code == 400


async def test_settings_are_tenant_scoped(
    client: httpx.AsyncClient,
    owner_headers: dict[str, str],
    db_session: AsyncSession,
    auth_headers: AuthHeaderFactory,
) -> None:
    await client.put("/llm-settings", json={"anthropic_api_key": SECRET}, headers=owner_headers)

    other = Organization(name="Other")
    other.memberships = [Membership(user_id="bob", role="owner")]
    db_session.add(other)
    await db_session.flush()
    bob = {**auth_headers(user_id="bob"), "X-Org-Id": str(other.id)}

    response = await client.get("/llm-settings", headers=bob)
    assert response.json()["keys"]["anthropic_api_key"]["is_set"] is False


async def test_catalog_lists_providers(
    client: httpx.AsyncClient, owner_headers: dict[str, str]
) -> None:
    response = await client.get("/llm-settings/catalog", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert {p["id"] for p in body["chat_providers"]} == {"anthropic", "openai"}
    assert {p["id"] for p in body["embedding_providers"]} == {"voyage", "openai"}
