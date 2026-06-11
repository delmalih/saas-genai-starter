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


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if not settings.voyage_api_key:
        raise ProviderNotConfigured("VOYAGE_API_KEY is not set")
    return VoyageEmbeddingProvider(
        api_key=settings.voyage_api_key,
        model=settings.llm_embedding_model,
    )
