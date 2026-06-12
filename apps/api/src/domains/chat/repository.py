import uuid

from src.core.repository import TenantScopedRepository
from src.domains.chat.models import ChatMessage, Conversation


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation

    async def list_recent(self, limit: int = 50) -> list[Conversation]:
        result = await self._db.execute(
            self._query().order_by(Conversation.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


class ChatMessageRepository(TenantScopedRepository[ChatMessage]):
    model = ChatMessage

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        result = await self._db.execute(
            self._query()
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
        )
        return list(result.scalars().all())
