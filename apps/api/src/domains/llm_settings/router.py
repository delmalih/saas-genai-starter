from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.db import DbSession
from src.core.tenancy import CurrentTenant
from src.domains.llm_settings.models import OrgLLMSettings
from src.domains.llm_settings.schemas import (
    CatalogOut,
    ChatProviderOut,
    EmbeddingProviderOut,
    KeyState,
    LLMSettingsOut,
    LLMSettingsUpdate,
)
from src.domains.llm_settings.service import LLMSettingsService
from src.llm.catalog import CHAT_PROVIDERS, EMBEDDING_PROVIDERS, KEY_FIELDS

router = APIRouter(prefix="/llm-settings", tags=["llm-settings"])


def _to_out(settings: OrgLLMSettings) -> LLMSettingsOut:
    return LLMSettingsOut(
        chat_provider=settings.chat_provider,  # type: ignore[arg-type]  # validated on write
        chat_model=settings.chat_model,
        embedding_provider=settings.embedding_provider,  # type: ignore[arg-type]
        keys={
            key_field: KeyState(
                is_set=getattr(settings, f"{key_field}_encrypted") is not None,
                last4=LLMSettingsService.key_last4(settings, key_field),
            )
            for key_field in KEY_FIELDS
        },
    )


@router.get("/catalog")
async def get_catalog(tenant: CurrentTenant) -> CatalogOut:
    return CatalogOut(
        chat_providers=[
            ChatProviderOut(
                id=p.id,
                label=p.label,
                models=p.models,
                default_model=p.default_model,
                key_field=p.key_field,
            )
            for p in CHAT_PROVIDERS.values()
        ],
        embedding_providers=[
            EmbeddingProviderOut(id=p.id, label=p.label, model=p.model, key_field=p.key_field)
            for p in EMBEDDING_PROVIDERS.values()
        ],
    )


@router.get("")
async def get_llm_settings(tenant: CurrentTenant, db: DbSession) -> LLMSettingsOut:
    settings = await LLMSettingsService(db, tenant).get_or_default()
    return _to_out(settings)


@router.put("")
async def update_llm_settings(
    payload: LLMSettingsUpdate, tenant: CurrentTenant, db: DbSession
) -> LLMSettingsOut:
    settings = await LLMSettingsService(db, tenant).update(payload)
    response = _to_out(settings)
    await db.commit()
    return response


class TestConnectionIn(BaseModel):
    target: Literal["chat", "embedding"] = "chat"


class TestConnectionOut(BaseModel):
    ok: bool
    error: str | None = None


@router.post("/test")
async def test_connection(
    payload: TestConnectionIn, tenant: CurrentTenant, db: DbSession
) -> TestConnectionOut:
    """Validate the configured key with a minimal real call."""
    from src.domains.llm_settings.resolver import (
        resolve_chat_provider,
        resolve_embedding_provider,
    )
    from src.llm.errors import LLMError
    from src.llm.types import Message

    try:
        if payload.target == "chat":
            provider = await resolve_chat_provider(db, tenant)
            await provider.complete([Message(role="user", content="ping")], max_tokens=1)
        else:
            embedder = await resolve_embedding_provider(db, tenant)
            await embedder.embed(["ping"])
    except LLMError as exc:
        return TestConnectionOut(ok=False, error=str(exc))
    return TestConnectionOut(ok=True)
