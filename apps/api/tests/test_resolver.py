import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.tenancy import TenantContext
from src.domains.llm_settings.resolver import (
    _chat_cache,
    resolve_chat_provider,
    resolve_embedding_provider,
)
from src.domains.llm_settings.schemas import LLMSettingsUpdate
from src.domains.llm_settings.service import LLMSettingsService
from src.domains.tenants.models import Membership, Organization
from src.llm.errors import ProviderNotConfigured

KEY = "sk-test-key-ABCD1234"


@pytest.fixture(autouse=True)
def clear_provider_cache() -> None:
    _chat_cache.clear()


@pytest.fixture
async def tenant(db_session: AsyncSession) -> TenantContext:
    organization = Organization(name="Resolve Co")
    organization.memberships = [Membership(user_id="alice", role="owner")]
    db_session.add(organization)
    await db_session.flush()
    return TenantContext(organization_id=organization.id, user_id="alice", role="owner")


async def set_settings(db: AsyncSession, tenant: TenantContext, **kwargs: object) -> None:
    await LLMSettingsService(db, tenant).update(LLMSettingsUpdate(**kwargs))  # type: ignore[arg-type]


async def test_no_key_anywhere_raises_with_guidance(
    db_session: AsyncSession, tenant: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    with pytest.raises(ProviderNotConfigured, match="Settings"):
        await resolve_chat_provider(db_session, tenant)


async def test_org_key_resolves_anthropic(
    db_session: AsyncSession, tenant: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    await set_settings(db_session, tenant, anthropic_api_key=KEY)

    provider = await resolve_chat_provider(db_session, tenant)
    assert provider is not None
    # Cached: same instance (and same circuit breaker) on the next call.
    assert await resolve_chat_provider(db_session, tenant) is provider


async def test_env_fallback_used_when_org_has_no_key(
    db_session: AsyncSession, tenant: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-env-fallback")
    provider = await resolve_chat_provider(db_session, tenant)
    assert provider is not None


async def test_key_rotation_swaps_the_cached_provider(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    await set_settings(db_session, tenant, anthropic_api_key=KEY)
    first = await resolve_chat_provider(db_session, tenant)

    await set_settings(db_session, tenant, anthropic_api_key=KEY + "-rotated")
    second = await resolve_chat_provider(db_session, tenant)
    assert second is not first


async def test_openai_choice_builds_openai_providers(
    db_session: AsyncSession, tenant: TenantContext
) -> None:
    await set_settings(
        db_session,
        tenant,
        chat_provider="openai",
        embedding_provider="openai",
        openai_api_key=KEY,
    )

    from src.llm.openai_provider import OpenAIEmbeddingProvider

    chat = await resolve_chat_provider(db_session, tenant)
    embedder = await resolve_embedding_provider(db_session, tenant)
    assert chat is not None
    assert isinstance(embedder, OpenAIEmbeddingProvider)


async def test_orgs_do_not_share_each_others_keys(
    db_session: AsyncSession, tenant: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    await set_settings(db_session, tenant, anthropic_api_key=KEY)

    other = Organization(name="Other")
    other.memberships = [Membership(user_id="bob", role="owner")]
    db_session.add(other)
    await db_session.flush()
    other_tenant = TenantContext(organization_id=other.id, user_id="bob", role="owner")

    # Org A resolves fine; org B has no key and must NOT inherit A's.
    assert await resolve_chat_provider(db_session, tenant) is not None
    with pytest.raises(ProviderNotConfigured):
        await resolve_chat_provider(db_session, other_tenant)
