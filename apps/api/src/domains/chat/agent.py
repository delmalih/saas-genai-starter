import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenancy import TenantContext
from src.domains.chat.models import Conversation
from src.domains.chat.service import SYSTEM_PROMPT
from src.domains.documents.models import STATUS_READY, Document
from src.domains.documents.retrieval import Citation, RetrievalService
from src.domains.usage.models import FEATURE_CHAT, FEATURE_RAG
from src.domains.usage.service import UsageService
from src.llm.provider import ChatProvider
from src.llm.types import Completion, Message, StreamEnd, TextDelta, ToolCall, ToolDef

logger = structlog.get_logger(__name__)

MAX_TOOL_ROUNDS = 4

SEARCH_TOOL = ToolDef(
    name="search_documents",
    description=(
        "Search the workspace's uploaded documents. Call this whenever the "
        "user asks about their documents, or about facts that may be stored "
        "in them, before answering from memory."
    ),
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for"}},
        "required": ["query"],
    },
)

STATS_TOOL = ToolDef(
    name="get_workspace_stats",
    description=(
        "Get counts of documents and conversations in this workspace. Call "
        "this when the user asks what is in their workspace."
    ),
    input_schema={"type": "object", "properties": {}},
)

# Stable suffix — part of the cacheable prefix, never interpolate into it.
RAG_SYSTEM_PROMPT = (
    SYSTEM_PROMPT + "\n\nYou can search the user's uploaded documents with the "
    "search_documents tool. Ground document-related answers in the retrieved "
    "snippets and mention which document they come from."
)


class AgentToolbox:
    """Executes tool calls issued by the model during a chat turn."""

    def __init__(self, db: AsyncSession, tenant: TenantContext, retrieval: RetrievalService | None):
        self._db = db
        self._tenant = tenant
        self._retrieval = retrieval
        self.citations: list[Citation] = []

    async def execute(self, call: ToolCall) -> str:
        if call.name == "search_documents":
            return await self._search(str(call.arguments.get("query", "")))
        if call.name == "get_workspace_stats":
            return await self._stats()
        return f"Unknown tool: {call.name}"

    async def _search(self, query: str) -> str:
        if self._retrieval is None:
            return "Document search is not configured."
        if not query:
            return "Empty query."
        results = await self._retrieval.search(query, created_by=self._tenant.user_id)
        for citation in results:
            if not any(
                c.document_id == citation.document_id
                and c.page == citation.page
                and c.snippet == citation.snippet
                for c in self.citations
            ):
                self.citations.append(citation)
        if not results:
            return "No matching content found in the documents."
        return json.dumps(
            [
                {
                    "document": c.document_name,
                    "page": c.page,
                    "snippet": c.snippet,
                    "score": c.score,
                }
                for c in results
            ]
        )

    async def _stats(self) -> str:
        documents = await self._db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == self._tenant.organization_id,
                Document.status == STATUS_READY,
            )
        )
        conversations = await self._db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.tenant_id == self._tenant.organization_id)
        )
        return json.dumps(
            {
                "ready_documents": documents.scalar_one(),
                "conversations": conversations.scalar_one(),
            }
        )


def _assistant_turn(completion: Completion) -> Message:
    blocks: list[dict[str, Any]] = []
    if completion.text:
        blocks.append({"type": "text", "text": completion.text})
    for call in completion.tool_calls:
        blocks.append(
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        )
    return Message(role="assistant", content=blocks)


def citations_payload(citations: list[Citation]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": str(c.document_id),
            "document_name": c.document_name,
            "page": c.page,
            "snippet": c.snippet,
            "score": c.score,
        }
        for c in citations
    ]


async def run_agent(
    provider: ChatProvider,
    usage: UsageService,
    toolbox: AgentToolbox,
    tenant: TenantContext,
    llm_messages: list[Message],
    use_rag: bool,
) -> AsyncIterator[dict[str, Any]]:
    """Streamed agent loop. Yields SSE-ready event dicts; the last one is
    {type: final, text, citations, tokens} for the caller to persist."""
    tools = [SEARCH_TOOL, STATS_TOOL] if use_rag else None
    system = RAG_SYSTEM_PROMPT if use_rag else SYSTEM_PROMPT
    feature = FEATURE_RAG if use_rag else FEATURE_CHAT

    messages = list(llm_messages)
    total_tokens = 0
    completion: Completion | None = None

    for _ in range(MAX_TOOL_ROUNDS):
        completion = None
        async for event in usage.tracked_stream(
            provider, feature, tenant.user_id, messages, system=system, tools=tools
        ):
            if isinstance(event, TextDelta):
                yield {"type": "delta", "text": event.text}
            elif isinstance(event, StreamEnd):
                completion = event.completion
        assert completion is not None  # noqa: S101 — StreamEnd always arrives
        total_tokens += completion.usage.input_tokens + completion.usage.output_tokens

        if completion.stop_reason != "tool_use" or not completion.tool_calls:
            break

        result_blocks: list[dict[str, Any]] = []
        for call in completion.tool_calls:
            yield {"type": "tool_use", "name": call.name, "input": call.arguments}
            output = await toolbox.execute(call)
            result_blocks.append({"type": "tool_result", "tool_use_id": call.id, "content": output})
        messages.append(_assistant_turn(completion))
        messages.append(Message(role="user", content=result_blocks))
    else:
        logger.warning("agent.max_tool_rounds", uuid=str(uuid.uuid4()))

    yield {
        "type": "final",
        "text": completion.text if completion else "",
        "citations": citations_payload(toolbox.citations),
        "tokens": total_tokens,
    }
