from typing import Literal

from pydantic import BaseModel, Field

ChatProviderId = Literal[
    "anthropic", "openai", "gemini", "mistral", "xai", "deepseek", "groq", "openrouter", "together"
]
EmbeddingProviderId = Literal["voyage", "openai", "gemini", "mistral", "cohere"]


class KeyState(BaseModel):
    is_set: bool
    last4: str | None = None


class LLMSettingsOut(BaseModel):
    chat_provider: ChatProviderId
    chat_model: str
    embedding_provider: EmbeddingProviderId
    keys: dict[str, KeyState]


class LLMSettingsUpdate(BaseModel):
    """Key semantics: omitted = unchanged, empty string = clear, value = set."""

    chat_provider: ChatProviderId | None = None
    chat_model: str | None = None
    embedding_provider: EmbeddingProviderId | None = None
    anthropic_api_key: str | None = Field(default=None, max_length=512)
    openai_api_key: str | None = Field(default=None, max_length=512)
    voyage_api_key: str | None = Field(default=None, max_length=512)
    gemini_api_key: str | None = Field(default=None, max_length=512)
    mistral_api_key: str | None = Field(default=None, max_length=512)
    xai_api_key: str | None = Field(default=None, max_length=512)
    deepseek_api_key: str | None = Field(default=None, max_length=512)
    groq_api_key: str | None = Field(default=None, max_length=512)
    openrouter_api_key: str | None = Field(default=None, max_length=512)
    cohere_api_key: str | None = Field(default=None, max_length=512)
    together_api_key: str | None = Field(default=None, max_length=512)


class ChatProviderOut(BaseModel):
    id: str
    label: str
    models: list[str]
    default_model: str
    key_field: str


class EmbeddingProviderOut(BaseModel):
    id: str
    label: str
    model: str
    key_field: str


class CatalogOut(BaseModel):
    chat_providers: list[ChatProviderOut]
    embedding_providers: list[EmbeddingProviderOut]
