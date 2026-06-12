"""Provider and model catalog — the single source of truth for what an
organization can pick in its LLM settings. Kept in code on purpose: adding
a model is a one-line PR, and the UI reads it through the API."""

from dataclasses import dataclass, field

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_VOYAGE = "voyage"


@dataclass(frozen=True)
class ChatProviderInfo:
    id: str
    label: str
    models: list[str] = field(default_factory=list)
    default_model: str = ""
    key_field: str = ""


@dataclass(frozen=True)
class EmbeddingProviderInfo:
    id: str
    label: str
    model: str
    key_field: str
    # All embedding models are pinned to the schema's vector dimension.
    dimensions: int = 1024


CHAT_PROVIDERS: dict[str, ChatProviderInfo] = {
    PROVIDER_ANTHROPIC: ChatProviderInfo(
        id=PROVIDER_ANTHROPIC,
        label="Anthropic",
        models=["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-8"],
        default_model="claude-sonnet-4-6",
        key_field="anthropic_api_key",
    ),
    PROVIDER_OPENAI: ChatProviderInfo(
        id=PROVIDER_OPENAI,
        label="OpenAI",
        models=["gpt-5.1", "gpt-5.1-mini"],
        default_model="gpt-5.1-mini",
        key_field="openai_api_key",
    ),
}

EMBEDDING_PROVIDERS: dict[str, EmbeddingProviderInfo] = {
    PROVIDER_VOYAGE: EmbeddingProviderInfo(
        id=PROVIDER_VOYAGE,
        label="Voyage AI",
        model="voyage-3.5",
        key_field="voyage_api_key",
    ),
    PROVIDER_OPENAI: EmbeddingProviderInfo(
        id=PROVIDER_OPENAI,
        label="OpenAI",
        model="text-embedding-3-small",
        key_field="openai_api_key",
    ),
}

KEY_FIELDS = ("anthropic_api_key", "openai_api_key", "voyage_api_key")


def validate_chat_choice(provider: str, model: str) -> bool:
    info = CHAT_PROVIDERS.get(provider)
    return info is not None and model in info.models


def validate_embedding_choice(provider: str) -> bool:
    return provider in EMBEDDING_PROVIDERS
