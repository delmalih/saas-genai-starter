from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crypto import decrypt_secret, encrypt_secret
from src.core.errors import BadRequest, Forbidden
from src.core.tenancy import TenantContext
from src.domains.llm_settings.models import OrgLLMSettings
from src.domains.llm_settings.schemas import LLMSettingsUpdate
from src.llm.catalog import (
    CHAT_PROVIDERS,
    KEY_FIELDS,
    PROVIDER_ANTHROPIC,
    PROVIDER_VOYAGE,
    validate_chat_choice,
    validate_embedding_choice,
)


class LLMSettingsService:
    def __init__(self, db: AsyncSession, tenant: TenantContext):
        self._db = db
        self._tenant = tenant

    async def get_or_default(self) -> OrgLLMSettings:
        result = await self._db.execute(
            select(OrgLLMSettings).where(OrgLLMSettings.tenant_id == self._tenant.organization_id)
        )
        settings = result.scalar_one_or_none()
        if settings is None:
            # Column defaults only apply at flush — set them explicitly so a
            # transient (never-saved) instance is fully usable.
            settings = OrgLLMSettings(
                tenant_id=self._tenant.organization_id,
                chat_provider=PROVIDER_ANTHROPIC,
                chat_model=CHAT_PROVIDERS[PROVIDER_ANTHROPIC].default_model,
                embedding_provider=PROVIDER_VOYAGE,
            )
        return settings

    async def update(self, payload: LLMSettingsUpdate) -> OrgLLMSettings:
        if self._tenant.role not in ("owner", "admin"):
            raise Forbidden("Requires the admin role")

        settings = await self.get_or_default()

        chat_provider = payload.chat_provider or settings.chat_provider
        chat_model = payload.chat_model or settings.chat_model
        if payload.chat_provider and not payload.chat_model:
            # Switching provider without naming a model: take its default.
            chat_model = CHAT_PROVIDERS[payload.chat_provider].default_model
        if not validate_chat_choice(chat_provider, chat_model):
            raise BadRequest(f"Unknown model {chat_model!r} for provider {chat_provider!r}")
        if payload.embedding_provider and not validate_embedding_choice(payload.embedding_provider):
            raise BadRequest(f"Unknown embedding provider {payload.embedding_provider!r}")

        settings.chat_provider = chat_provider
        settings.chat_model = chat_model
        if payload.embedding_provider:
            settings.embedding_provider = payload.embedding_provider

        for key_field in KEY_FIELDS:
            value = getattr(payload, key_field)
            if value is None:
                continue  # omitted — unchanged
            encrypted_field = f"{key_field}_encrypted"
            if value == "":
                setattr(settings, encrypted_field, None)
            else:
                setattr(settings, encrypted_field, encrypt_secret(value.strip()))

        self._db.add(settings)
        await self._db.flush()
        return settings

    @staticmethod
    def decrypted_key(settings: OrgLLMSettings, key_field: str) -> str | None:
        encrypted = getattr(settings, f"{key_field}_encrypted")
        return decrypt_secret(encrypted) if encrypted else None

    @staticmethod
    def key_last4(settings: OrgLLMSettings, key_field: str) -> str | None:
        plain = LLMSettingsService.decrypted_key(settings, key_field)
        return plain[-4:] if plain else None
