import hashlib
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db import DbSession
from src.core.tenancy import CurrentTenant, TenantContext
from src.domains.llm_settings.models import OrgLLMSettings
from src.domains.llm_settings.service import LLMSettingsService
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.catalog import (
    CHAT_PROVIDERS,
    EMBEDDING_PROVIDERS,
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    PROVIDER_VOYAGE,
)
from src.llm.errors import ProviderNotConfigured
from src.llm.openai_provider import OpenAIEmbeddingProvider, OpenAIProvider
from src.llm.provider import ChatProvider, EmbeddingProvider
from src.llm.resilience import ResilientChatProvider
from src.llm.voyage_provider import VoyageEmbeddingProvider

# Provider instances (and their circuit breakers) are reused across requests.
# Keyed by a hash of the key so rotating a key swaps the entry naturally.
_chat_cache: dict[tuple[str, str, str], ChatProvider] = {}
_embedding_cache: dict[tuple[str, str, str], EmbeddingProvider] = {}
_CACHE_MAX = 256

ENV_KEY_FALLBACKS = {
    "anthropic_api_key": lambda: get_settings().anthropic_api_key,
    "openai_api_key": lambda: get_settings().openai_api_key,
    "voyage_api_key": lambda: get_settings().voyage_api_key,
}


def _key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def _resolve_key(org_settings: OrgLLMSettings, key_field: str) -> str | None:
    """Org key first, server env key as the self-host fallback."""
    org_key = LLMSettingsService.decrypted_key(org_settings, key_field)
    return org_key or ENV_KEY_FALLBACKS[key_field]()


async def resolve_chat_provider(db: AsyncSession, tenant: TenantContext) -> ChatProvider:
    org_settings = await LLMSettingsService(db, tenant).get_or_default()
    provider_id = org_settings.chat_provider
    info = CHAT_PROVIDERS[provider_id]
    api_key = _resolve_key(org_settings, info.key_field)
    if not api_key:
        raise ProviderNotConfigured(
            f"No {info.label} API key configured — add one in Settings → AI Provider"
        )

    cache_key = (provider_id, org_settings.chat_model, _key_fingerprint(api_key))
    cached = _chat_cache.get(cache_key)
    if cached is not None:
        return cached

    max_tokens = get_settings().llm_max_output_tokens
    inner: ChatProvider
    if provider_id == PROVIDER_ANTHROPIC:
        inner = AnthropicProvider(api_key, org_settings.chat_model, max_tokens)
    elif provider_id == PROVIDER_OPENAI:
        inner = OpenAIProvider(api_key, org_settings.chat_model, max_tokens)
    else:
        raise ProviderNotConfigured(f"Unknown chat provider {provider_id!r}")

    provider = ResilientChatProvider(inner)
    if len(_chat_cache) >= _CACHE_MAX:
        _chat_cache.clear()
    _chat_cache[cache_key] = provider
    return provider


async def resolve_embedding_provider(db: AsyncSession, tenant: TenantContext) -> EmbeddingProvider:
    org_settings = await LLMSettingsService(db, tenant).get_or_default()
    provider_id = org_settings.embedding_provider
    info = EMBEDDING_PROVIDERS[provider_id]
    api_key = _resolve_key(org_settings, info.key_field)
    if not api_key:
        raise ProviderNotConfigured(
            f"No {info.label} API key configured — add one in Settings → AI Provider"
        )

    cache_key = (provider_id, info.model, _key_fingerprint(api_key))
    cached = _embedding_cache.get(cache_key)
    if cached is not None:
        return cached

    provider: EmbeddingProvider
    if provider_id == PROVIDER_VOYAGE:
        provider = VoyageEmbeddingProvider(api_key, info.model)
    elif provider_id == PROVIDER_OPENAI:
        provider = OpenAIEmbeddingProvider(api_key, info.model, info.dimensions)
    else:
        raise ProviderNotConfigured(f"Unknown embedding provider {provider_id!r}")

    if len(_embedding_cache) >= _CACHE_MAX:
        _embedding_cache.clear()
    _embedding_cache[cache_key] = provider
    return provider


async def chat_provider_dep(tenant: CurrentTenant, db: DbSession) -> ChatProvider:
    return await resolve_chat_provider(db, tenant)


async def embedding_provider_dep(tenant: CurrentTenant, db: DbSession) -> EmbeddingProvider | None:
    try:
        return await resolve_embedding_provider(db, tenant)
    except ProviderNotConfigured:
        return None


TenantChatProvider = Annotated[ChatProvider, Depends(chat_provider_dep)]
TenantEmbedder = Annotated[EmbeddingProvider | None, Depends(embedding_provider_dep)]
