import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from src.core.db import DbSession
from src.core.tenancy import CurrentTenant
from src.domains.chat.agent import AgentToolbox, run_agent
from src.domains.chat.models import ROLE_ASSISTANT, ROLE_USER
from src.domains.chat.schemas import (
    ChatMessageOut,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    SendMessageIn,
)
from src.domains.chat.service import ChatService
from src.domains.documents.retrieval import RetrievalService
from src.domains.usage.service import UsageService
from src.llm.errors import LLMError, ProviderNotConfigured
from src.llm.factory import chat_provider_dep, get_embedding_provider
from src.llm.provider import ChatProvider, EmbeddingProvider
from src.llm.rate_limit import TenantRateLimiter, get_rate_limiter
from src.llm.types import Message

router = APIRouter(prefix="/conversations", tags=["chat"])

Provider = Annotated[ChatProvider, Depends(chat_provider_dep)]
RateLimiter = Annotated[TenantRateLimiter, Depends(get_rate_limiter)]


def _conversation_out(conversation: Any) -> ConversationOut:
    return ConversationOut.model_validate(conversation, from_attributes=True)


@router.get("")
async def list_conversations(tenant: CurrentTenant, db: DbSession) -> list[ConversationOut]:
    conversations = await ChatService(db, tenant).list_conversations()
    return [_conversation_out(c) for c in conversations]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate, tenant: CurrentTenant, db: DbSession
) -> ConversationOut:
    conversation = await ChatService(db, tenant).create_conversation(
        created_by=tenant.user_id, title=payload.title
    )
    response = _conversation_out(conversation)
    await db.commit()
    return response


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, tenant: CurrentTenant, db: DbSession
) -> ConversationDetailOut:
    service = ChatService(db, tenant)
    conversation = await service.get_conversation(conversation_id)
    messages = await service.get_messages(conversation_id)
    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        messages=[ChatMessageOut.model_validate(m, from_attributes=True) for m in messages],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, tenant: CurrentTenant, db: DbSession
) -> None:
    await ChatService(db, tenant).delete_conversation(conversation_id)
    await db.commit()


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _embedder_or_none() -> EmbeddingProvider | None:
    try:
        return get_embedding_provider()
    except ProviderNotConfigured:
        return None


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageIn,
    tenant: CurrentTenant,
    db: DbSession,
    provider: Provider,
    limiter: RateLimiter,
) -> StreamingResponse:
    """Stream the assistant reply over SSE.

    Events: {type: delta, text} ... {type: done, message_id} | {type: error}.
    The user message is committed before streaming starts so it survives a
    client disconnect; usage is recorded even on interrupted streams.
    """
    service = ChatService(db, tenant)
    conversation = await service.get_conversation(conversation_id)
    # Quota check happens before the stream opens — it can still return 429.
    await limiter.check(tenant.organization_id)

    history = await service.get_messages(conversation_id)
    await service.add_message(conversation_id, ROLE_USER, payload.content)
    service.maybe_autotitle(conversation, payload.content)
    await db.commit()

    llm_messages = [
        *ChatService.to_llm_messages(history),
        Message(role="user", content=payload.content),
    ]
    usage = UsageService(db, tenant)

    # RAG kicks in as soon as the workspace has at least one ready document.
    embedder = _embedder_or_none()
    retrieval = RetrievalService(db, tenant, embedder) if embedder else None
    use_rag = retrieval is not None and await retrieval.has_ready_documents()
    toolbox = AgentToolbox(db, tenant, retrieval)

    async def event_stream() -> AsyncIterator[str]:
        try:
            agent = run_agent(provider, usage, toolbox, tenant, llm_messages, use_rag)
            async for event in agent:
                if event["type"] != "final":
                    yield _sse(event)
                    continue
                message = await service.add_message(
                    conversation_id,
                    ROLE_ASSISTANT,
                    event["text"],
                    citations=event["citations"],
                )
                await limiter.record_tokens(tenant.organization_id, event["tokens"])
                await db.commit()
                yield _sse(
                    {
                        "type": "done",
                        "message_id": str(message.id),
                        "citations": event["citations"],
                    }
                )
        except LLMError as exc:
            # The response is already streaming — errors travel as events.
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
