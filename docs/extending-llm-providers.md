# Extending the LLM layer

Adding a chat or embeddings provider is a contained change — domain code
(chat, RAG, ingestion) never imports vendor SDKs and won't need touching.

## The contract

Providers implement the protocols in `apps/api/src/llm/provider.py`:

```python
class ChatProvider(Protocol):
    async def complete(self, messages, system=None, tools=None,
                       json_schema=None, max_tokens=None) -> Completion: ...
    def stream(self, messages, system=None, tools=None,
               max_tokens=None) -> AsyncIterator[StreamEvent]: ...

class EmbeddingProvider(Protocol):
    async def embed(self, texts, input_type="document") -> EmbeddingResult: ...
```

Normalized messages (`src/llm/types.py`) use Anthropic-shaped content blocks
as the lingua franca: `{"type": "tool_use", ...}` / `{"type": "tool_result",
...}`. Your provider translates them to its own wire format — see
`openai_provider.py::_translate_messages` for a worked example.

## Checklist for a new provider

1. **Implementation** — `src/llm/<name>_provider.py`. Use plain httpx (see
   `voyage_provider.py` for a minimal example, `openai_provider.py` for a
   full one with streaming + tool-call delta assembly). Accept an optional
   `transport: httpx.AsyncBaseTransport` so tests can use
   `httpx.MockTransport` — no network in unit tests.
2. **Error mapping** — convert provider errors to the typed exceptions in
   `src/llm/errors.py` (`RateLimited` with `retry_after`,
   `ProviderUnavailable`, `ContextTooLong`, `ProviderBadRequest`). The
   resilience layer keys off these.
3. **Catalog** — add the provider and its model allowlist to
   `src/llm/catalog.py`. The settings UI reads this through the API; no
   frontend change needed.
4. **Pricing** — add per-model entries to `src/llm/pricing.py` (USD per
   million tokens, `Decimal`). Unknown models cost 0 and log a warning.
5. **Resolution** — wire the provider into
   `src/domains/llm_settings/resolver.py` (construction + which key field it
   uses). It gets wrapped in the resilience decorators automatically.
6. **Tests** — mapping matrix with `httpx.MockTransport` (text, tool calls,
   usage incl. cached tokens, 429 with `retry-after`), plus a resolver case.
   See `tests/llm/test_openai_provider.py`.

## Embedding providers: one extra rule

`document_chunks.embedding` is `Vector(1024)` — every embedding provider
must produce 1024-dimension vectors (OpenAI's `text-embedding-3-*` support a
`dimensions` parameter; Voyage's `voyage-3.5` is natively 1024). A provider
with a different dimension requires a migration **and re-ingesting every
document** — vectors from different models are not comparable, which is also
why the settings UI warns when switching embedding providers.
