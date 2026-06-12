import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFound
from src.core.tenancy import TenantContext
from src.domains.chat.models import DEFAULT_TITLE, ChatMessage, Conversation
from src.domains.chat.repository import ChatMessageRepository, ConversationRepository
from src.llm.types import Message

# Stable on purpose: this is the cacheable prefix of every chat request.
# Do not interpolate anything dynamic here — see docs on prompt caching.
SYSTEM_PROMPT = (
    "You are a helpful, concise assistant. Answer in the language the user "
    "writes in. Use Markdown when it improves readability. If you do not "
    "know something, say so instead of guessing."
)

TITLE_MAX_LENGTH = 60


class ChatService:
    def __init__(self, db: AsyncSession, tenant: TenantContext):
        self._conversations = ConversationRepository(db, tenant)
        self._messages = ChatMessageRepository(db, tenant)
        self._db = db

    async def list_conversations(self) -> list[Conversation]:
        return await self._conversations.list_recent()

    async def create_conversation(self, created_by: str, title: str | None) -> Conversation:
        conversation = self._conversations.add(
            Conversation(title=title or DEFAULT_TITLE, created_by=created_by)
        )
        await self._db.flush()
        await self._db.refresh(conversation)
        return conversation

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            raise NotFound("Conversation not found")
        return conversation

    async def delete_conversation(self, conversation_id: uuid.UUID) -> None:
        conversation = await self.get_conversation(conversation_id)
        await self._conversations.delete(conversation)

    async def get_messages(self, conversation_id: uuid.UUID) -> list[ChatMessage]:
        return await self._messages.list_for_conversation(conversation_id)

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[dict[str, object]] | None = None,
    ) -> ChatMessage:
        message = self._messages.add(
            ChatMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                citations=citations or None,
            )
        )
        await self._db.flush()
        await self._db.refresh(message)
        return message

    def maybe_autotitle(self, conversation: Conversation, first_user_message: str) -> None:
        """Name the conversation after the first message, once."""
        if conversation.title == DEFAULT_TITLE:
            conversation.title = first_user_message[:TITLE_MAX_LENGTH].strip()

    @staticmethod
    def to_llm_messages(history: list[ChatMessage]) -> list[Message]:
        return [
            Message(role="user" if m.role == "user" else "assistant", content=m.content)
            for m in history
        ]
