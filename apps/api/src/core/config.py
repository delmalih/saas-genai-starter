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
    # Encrypts org-provided API keys at rest (Fernet). Generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_encryption_key: str | None = None
    # Server-wide LLM keys — the fallback when an org has not configured its
    # own (self-host mode). Optional at boot: LLM calls fail with a clear
    # error instead.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    voyage_api_key: str | None = None
    llm_chat_model: str = "claude-sonnet-4-6"
    llm_embedding_model: str = "voyage-3.5"
    llm_max_output_tokens: int = 4096
    # Per-tenant limits on LLM-consuming endpoints (admin can override per org).
    rate_limit_requests_per_minute: int = 30
    rate_limit_tokens_per_day: int = 500_000
    # Comma-separated emails with access to the platform admin panel.
    admin_emails: str = ""
    # Background jobs: "arq" polls Redis (local/default); "cloud_tasks"
    # pushes HTTP tasks to /internal/jobs/* (production, scale-to-zero).
    queue_driver: Literal["arq", "cloud_tasks"] = "arq"
    cloud_tasks_queue: str | None = None  # projects/P/locations/L/queues/Q
    internal_jobs_base_url: str | None = None  # this API's public URL
    jobs_service_account_email: str | None = None  # OIDC identity of the queue

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(
            email.strip().lower() for email in self.admin_emails.split(",") if email.strip()
        )

    # Document storage (local disk path in dev; GCS in production).
    storage_dir: str = "./storage"
    max_upload_bytes: int = 20 * 1024 * 1024
    # Tracing — spans export to OTEL_EXPORTER_OTLP_ENDPOINT when set,
    # to the console otherwise.
    otel_enabled: bool = False
    otel_service_name: str = "saas-genai-starter-api"
    otel_exporter_otlp_endpoint: str | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from the environment
