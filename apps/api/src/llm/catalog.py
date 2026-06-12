"""Provider and model catalog — the single source of truth for what an
organization can pick in its LLM settings. Kept in code on purpose: adding
a model is a one-line PR, and the UI reads it through the API.

Most chat providers expose an OpenAI-compatible API — for those, an entry
here (id, base_url, key field) plus a pricing row and a key column is the
whole integration. Anthropic and Cohere have native adapters."""

from dataclasses import dataclass, field

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_GEMINI = "gemini"
PROVIDER_MISTRAL = "mistral"
PROVIDER_XAI = "xai"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_GROQ = "groq"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_VOYAGE = "voyage"
PROVIDER_COHERE = "cohere"


@dataclass(frozen=True)
class ChatProviderInfo:
    id: str
    label: str
    models: list[str] = field(default_factory=list)
    default_model: str = ""
    key_field: str = ""
    # OpenAI-compatible endpoint; None = native adapter (Anthropic).
    base_url: str | None = None


@dataclass(frozen=True)
class EmbeddingProviderInfo:
    id: str
    label: str
    model: str
    key_field: str
    # All embedding models are pinned to the schema's vector dimension.
    dimensions: int = 1024
    # OpenAI-compatible endpoint; None = native adapter (Voyage, Cohere).
    base_url: str | None = None
    # Some compatible APIs reject the `dimensions` parameter (fixed-size models).
    send_dimensions: bool = True


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
    PROVIDER_GEMINI: ChatProviderInfo(
        id=PROVIDER_GEMINI,
        label="Google Gemini",
        models=["gemini-3-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash"],
        default_model="gemini-2.5-flash",
        key_field="gemini_api_key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    ),
    PROVIDER_MISTRAL: ChatProviderInfo(
        id=PROVIDER_MISTRAL,
        label="Mistral",
        models=["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
        default_model="mistral-small-latest",
        key_field="mistral_api_key",
        base_url="https://api.mistral.ai/v1",
    ),
    PROVIDER_XAI: ChatProviderInfo(
        id=PROVIDER_XAI,
        label="xAI",
        models=["grok-4", "grok-4-fast"],
        default_model="grok-4-fast",
        key_field="xai_api_key",
        base_url="https://api.x.ai/v1",
    ),
    PROVIDER_DEEPSEEK: ChatProviderInfo(
        id=PROVIDER_DEEPSEEK,
        label="DeepSeek",
        models=["deepseek-chat", "deepseek-reasoner"],
        default_model="deepseek-chat",
        key_field="deepseek_api_key",
        base_url="https://api.deepseek.com/v1",
    ),
    PROVIDER_GROQ: ChatProviderInfo(
        id=PROVIDER_GROQ,
        label="Groq",
        models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        default_model="llama-3.3-70b-versatile",
        key_field="groq_api_key",
        base_url="https://api.groq.com/openai/v1",
    ),
    PROVIDER_OPENROUTER: ChatProviderInfo(
        id=PROVIDER_OPENROUTER,
        label="OpenRouter",
        # A curated slice of the long tail — extend freely; usage for models
        # without a pricing entry is recorded at $0 with a warning log.
        models=[
            "openrouter/auto",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen3-235b-a22b",
        ],
        default_model="openrouter/auto",
        key_field="openrouter_api_key",
        base_url="https://openrouter.ai/api/v1",
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
    PROVIDER_GEMINI: EmbeddingProviderInfo(
        id=PROVIDER_GEMINI,
        label="Google Gemini",
        model="gemini-embedding-001",
        key_field="gemini_api_key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    ),
    PROVIDER_MISTRAL: EmbeddingProviderInfo(
        id=PROVIDER_MISTRAL,
        label="Mistral",
        model="mistral-embed",  # fixed 1024 dimensions
        key_field="mistral_api_key",
        base_url="https://api.mistral.ai/v1",
        send_dimensions=False,
    ),
    PROVIDER_COHERE: EmbeddingProviderInfo(
        id=PROVIDER_COHERE,
        label="Cohere",
        model="embed-v4.0",
        key_field="cohere_api_key",
    ),
}

KEY_FIELDS = (
    "anthropic_api_key",
    "openai_api_key",
    "voyage_api_key",
    "gemini_api_key",
    "mistral_api_key",
    "xai_api_key",
    "deepseek_api_key",
    "groq_api_key",
    "openrouter_api_key",
    "cohere_api_key",
)


def validate_chat_choice(provider: str, model: str) -> bool:
    info = CHAT_PROVIDERS.get(provider)
    return info is not None and model in info.models


def validate_embedding_choice(provider: str) -> bool:
    return provider in EMBEDDING_PROVIDERS
