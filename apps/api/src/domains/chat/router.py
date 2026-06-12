import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from src.core.db import DbSession
from src.core.tenancy import CurrentTenant
from src.domains.chat.models import ROLE_ASSISTANT, ROLE_USER
from src.domains.chat.schemas import (
    ChatMessageOut,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    SendMessageIn,
)
from src.domains.chat.service import SYSTEM_PROMPT, ChatService
from src.domains.usage.models import FEATURE_CHAT
from src.domains.usage.service import UsageService
from src.llm.errors import LLMError
from src.llm.factory import chat_provider_dep
from src.llm.provider import ChatProvider
from src.llm.rate_limit import TenantRateLimiter, get_rate_limiter
from src.llm.types import Message, StreamEnd, TextDelta

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

    async def event_stream() -> AsyncIterator[str]:
        try:
            stream = usage.tracked_stream(
                provider, FEATURE_CHAT, tenant.user_id, llm_messages, system=SYSTEM_PROMPT
            )
            async for event in stream:
                if isinstance(event, TextDelta):
                    yield _sse({"type": "delta", "text": event.text})
                elif isinstance(event, StreamEnd):
                    completion = event.completion
                    message = await service.add_message(
                        conversation_id, ROLE_ASSISTANT, completion.text
                    )
                    await limiter.record_tokens(
                        tenant.organization_id,
                        completion.usage.input_tokens + completion.usage.output_tokens,
                    )
                    await db.commit()
                    yield _sse({"type": "done", "message_id": str(message.id)})
        except LLMError as exc:
            # The response is already streaming — errors travel as events.
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
