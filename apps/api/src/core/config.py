from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "test", "production"]


class Settings(BaseSettings):
    """Application settings, loaded from environment variables (and .env locally).

    Required variables without a default make the app fail fast at startup.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: AppEnv = "local"
    database_url: str
    redis_url: str
    auth_jwks_url: str = "http://localhost:3000/api/auth/jwks"
    # When set, iss/aud claims are verified against these values.
    auth_jwt_issuer: str | None = None
    auth_jwt_audience: str | None = None
    # Base URL of the web app — used to build links in emails.
    web_base_url: str = "http://localhost:3000"
    # Email delivery: Resend when the key is set, console logging otherwise.
    resend_api_key: str | None = None
    email_from: str = "onboarding@resend.dev"
    # LLM providers. Keys are optional at boot so the rest of the app runs
    # without them — LLM calls fail with a clear error instead.
    anthropic_api_key: str | None = None
    voyage_api_key: str | None = None
    llm_chat_model: str = "claude-sonnet-4-6"
    llm_embedding_model: str = "voyage-3.5"
    llm_max_output_tokens: int = 4096
    # Per-tenant limits on LLM-consuming endpoints.
    rate_limit_requests_per_minute: int = 30
    rate_limit_tokens_per_day: int = 500_000

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from the environment
