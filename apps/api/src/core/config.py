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

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from the environment
