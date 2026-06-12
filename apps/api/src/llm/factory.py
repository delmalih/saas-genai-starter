from functools import lru_cache

from src.core.config import get_settings
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.errors import ProviderNotConfigured
from src.llm.provider import ChatProvider, EmbeddingProvider
from src.llm.resilience import ResilientChatProvider
from src.llm.voyage_provider import VoyageEmbeddingProvider


@lru_cache
def get_chat_provider() -> ChatProvider:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ProviderNotConfigured("ANTHROPIC_API_KEY is not set")
    return ResilientChatProvider(
        AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_chat_model,
            default_max_tokens=settings.llm_max_output_tokens,
        )
    )


def chat_provider_dep() -> ChatProvider:
    """FastAPI dependency wrapper — overridable in tests."""
    return get_chat_provider()


def embedding_provider_dep() -> EmbeddingProvider | None:
    """FastAPI dependency wrapper — None when Voyage is not configured,
    so features depending on embeddings degrade instead of erroring."""
    try:
        return get_embedding_provider()
    except ProviderNotConfigured:
        return None


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if not settings.voyage_api_key:
        raise ProviderNotConfigured("VOYAGE_API_KEY is not set")
    return VoyageEmbeddingProvider(
        api_key=settings.voyage_api_key,
        model=settings.llm_embedding_model,
    )
