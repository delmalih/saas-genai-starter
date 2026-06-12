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

## The fast path: OpenAI-compatible APIs

Most providers (Gemini's compat endpoint, Mistral, xAI, DeepSeek, Groq,
OpenRouter, Together, Fireworks, a local Ollama…) speak the OpenAI chat API.
For those, **no new provider class is needed** — `OpenAIProvider` takes a
`base_url` and a `provider_name`. Adding one is four small diffs:

1. **Catalog** — a `ChatProviderInfo` entry in `src/llm/catalog.py` with
   `base_url`, the model allowlist and a `key_field`, plus the field in
   `KEY_FIELDS`.
2. **Key storage** — a `<name>_api_key_encrypted` column on
   `OrgLLMSettings` (+ Alembic migration), a `<name>_api_key` setting in
   `core/config.py` (env fallback for self-hosting), and the field on
   `LLMSettingsUpdate` / the `ChatProviderId` literal in
   `domains/llm_settings/schemas.py`.
3. **Pricing** — per-model entries in `src/llm/pricing.py` (USD per million
   tokens, `Decimal`). Unknown models cost 0 and log a warning.
4. **UI label** — the key field's label in
   `apps/web/components/settings/ai-provider-card.tsx` (`KEY_LABELS`), then
   `make generate-client`.

`tests/llm/test_compatible_providers.py` is parameterized over the catalog
and enforces the checklist (pricing entry, key column, settings field) —
a forgotten step fails CI.

## Checklist for a native provider

For APIs with their own wire format (like Anthropic, Voyage, Cohere):

1. **Implementation** — `src/llm/<name>_provider.py`. Use plain httpx (see
   `voyage_provider.py` or `cohere_provider.py` for minimal examples,
   `openai_provider.py` for a full one with streaming + tool-call delta
   assembly). Accept an optional `transport: httpx.AsyncBaseTransport` so
   tests can use `httpx.MockTransport` — no network in unit tests.
2. **Error mapping** — convert provider errors to the typed exceptions in
   `src/llm/errors.py` (`RateLimited` with `retry_after`,
   `ProviderUnavailable`, `ContextTooLong`, `ProviderBadRequest`). The
   resilience layer keys off these.
3. **Catalog + key storage + pricing + UI label** — same as the fast path.
4. **Resolution** — wire the provider into
   `src/domains/llm_settings/resolver.py` (construction branch). It gets
   wrapped in the resilience decorators automatically.
5. **Tests** — mapping matrix with `httpx.MockTransport` (text, tool calls,
   usage incl. cached tokens, 429 with `retry-after`), plus a resolver case.
   See `tests/llm/test_openai_provider.py`.

## Embedding providers: one extra rule

`document_chunks.embedding` is `Vector(1024)` — every embedding provider
must produce 1024-dimension vectors (OpenAI's `text-embedding-3-*`, Gemini's
`gemini-embedding-001` and Cohere's `embed-v4.0` take a dimensions
parameter; Voyage's `voyage-3.5` and Mistral's `mistral-embed` are natively
1024 — for compatible APIs that reject the `dimensions` parameter, set
`send_dimensions=False` on the catalog entry). A provider with a different
dimension requires a migration **and re-ingesting every document** — vectors
from different models are not comparable, which is also why the settings UI
warns when switching embedding providers.
