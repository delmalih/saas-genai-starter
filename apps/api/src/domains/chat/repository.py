from src.core.repository import TenantScopedRepository
from src.domains.chat.models import Conversation


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation
