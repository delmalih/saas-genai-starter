# Tech Steps — Development Backlog

Jira-style backlog for `saas-genai-starter`. Tickets are grouped by epic and ordered by
dependency. IDs are stable (`SGS-XXX`) — reference them in branch names (`sgs-021-llm-resilience`)
and commit messages (`feat(llm): add retry/backoff [SGS-021]`).

Estimates are in ideal dev-days (d). Status legend: `[ ]` todo · `[~]` in progress · `[x]` done.

---

## EPIC 0 — Foundation & Tooling

Goal: a contributor can `git clone` → `make dev` → working stack in under 10 minutes.

### [x] SGS-001 — Repository scaffold (0.5d)
Monorepo layout with two apps and shared tooling:
```
apps/web   → Next.js 15 (pnpm)
apps/api   → FastAPI, Python 3.12 (uv)
infra/     → Terraform
evals/     → eval harness + datasets
```
**Acceptance criteria**
- `apps/web` bootstrapped with Next.js 15 (App Router, TypeScript strict), Tailwind CSS, shadcn/ui initialized.
- `apps/api` bootstrapped with `uv` (pyproject.toml), FastAPI, ruff + mypy configured.
- Root `Makefile` with documented targets: `dev`, `test`, `lint`, `evals` (stubs OK at this stage).
- MIT `LICENSE`, `.gitignore`, `.editorconfig`, placeholder `README.md`.
- Git repo initialized, first commit.

### [x] SGS-002 — Local dev environment (0.5d)
**Depends on:** SGS-001
- `docker-compose.yml`: `postgres:16` with `pgvector` extension, `redis:7`.
- `.env.example` for both apps, with comments for every variable (no real secrets, ever).
- `make dev` boots compose + API (uvicorn reload) + web (next dev) concurrently.
- A `make setup` target installs deps (pnpm install, uv sync) and creates the DB.
**Acceptance criteria**
- Fresh clone → `make setup && make dev` → web on :3000, API on :8000, both healthy.
- Documented in README "Quickstart" section.

### [x] SGS-003 — API skeleton: config, DB, migrations, logging (1d)
**Depends on:** SGS-002
- `src/core/config.py`: pydantic-settings, env-driven, fail-fast on missing required vars.
- `src/core/db.py`: SQLAlchemy 2 async engine + session dependency.
- Alembic wired (`make migrate`, `make makemigration m="..."`).
- Structured JSON logging (request id, tenant id once available), human-readable in dev.
- `GET /health` (liveness) and `GET /health/ready` (DB connectivity check).
- Domain-driven layout: `src/domains/<domain>/{router,service,repository,models,schemas}.py`.
**Acceptance criteria**
- `alembic upgrade head` runs clean on a fresh DB.
- pytest setup with an async test client and a per-test transactional DB fixture.

### [x] SGS-004 — Web skeleton: route groups, layout, design system (1d)
**Depends on:** SGS-001
- Route groups: `app/(marketing)/` (starter landing page) and `app/(app)/` (protected app shell).
- React Server Components by default; `"use client"` only where required.
- Base layout: sidebar navigation, top bar, theme tokens, dark mode.
- shadcn/ui components vendored under `components/ui/`.
**Acceptance criteria**
- Marketing page and an empty authenticated shell render; navigation stubs for Chat, Documents, Usage, Settings.

### [x] SGS-005 — Typed API client generation (0.5d)
**Depends on:** SGS-003, SGS-004
- Generate TypeScript types from the FastAPI OpenAPI schema (`openapi-typescript`).
- Thin fetch wrapper in `apps/web/lib/api/` handling auth header, errors, and SSE streams.
- `make generate-client` target; CI fails if the generated client is stale.
**Acceptance criteria**
- A round-trip call from web → `GET /health` works with full type safety.

### [x] SGS-006 — CI pipeline (0.5d)
**Depends on:** SGS-003, SGS-004
- GitHub Actions on PR + main: web (lint, typecheck, build), api (ruff, mypy, pytest with Postgres service container), client freshness check (SGS-005).
- Status badge in README.
**Acceptance criteria**
- CI green on main; a failing test or lint error blocks the PR.

---

## EPIC 1 — Auth & Multi-Tenancy

Goal: organizations with roles, every API query automatically tenant-scoped.
Decision: **Better Auth** in the Next.js app (Postgres-backed), FastAPI validates its JWTs via JWKS.

### [x] SGS-010 — Better Auth setup (1d)
**Depends on:** SGS-004
- Better Auth in `apps/web`: email/password + Google OAuth, Postgres adapter (same DB, `auth` schema), JWT plugin enabled (JWKS endpoint exposed).
- Login, signup, forgot-password pages; `(app)` route group gated by session middleware.
**Acceptance criteria**
- Signup → login → logout flows work locally; Google OAuth documented as optional (env-gated).

### [x] SGS-011 — API auth dependency (0.5d)
**Depends on:** SGS-003, SGS-010
- FastAPI dependency `CurrentUser`: validates the Better Auth JWT against the web app's JWKS (cached), extracts `user_id`.
- 401 handling with a consistent error envelope.
**Acceptance criteria**
- Protected test endpoint rejects missing/invalid tokens; integration test covers expiry and bad signature.

### [x] SGS-012 — Organizations, memberships, roles (1d)
**Depends on:** SGS-011
- Models: `Organization`, `Membership(user_id, org_id, role)` with roles `owner | admin | member` (string constants, no enum-typed DB columns).
- On signup: auto-create a personal organization, user becomes `owner`.
- Endpoints: list my orgs, create org, update org, list/update/remove members.
- Role checks as composable FastAPI dependencies (`require_role("admin")`).
**Acceptance criteria**
- A `member` cannot manage members; an `owner` cannot be removed by an `admin`. Tests cover the role matrix.

### [x] SGS-013 — Tenant scoping layer (1d)
**Depends on:** SGS-012
- `CurrentTenant` dependency: resolves the active org from the `X-Org-Id` header, verifies membership.
- Repository base class that **always** filters by `tenant_id` — domain code cannot forget the filter (constructor takes the tenant, query builders inject it).
- Every tenant-owned table carries `tenant_id` (indexed). Document Postgres RLS as a hardening option (not implemented in v1).
**Acceptance criteria**
- A dedicated cross-tenant test proves user A can never read tenant B's rows through any repository method.

### [x] SGS-014 — Team invitations (1d)
**Depends on:** SGS-012
- Invite by email: single-use token (7-day expiry), accept page handling both existing users and new signups.
- Email delivery behind an interface: console/log driver in dev, Resend driver in prod (env-gated).
- Pending invitations list with revoke.
**Acceptance criteria**
- Full invite → accept → membership flow tested; expired/revoked tokens are rejected.

### [x] SGS-015 — Settings & org switcher UI (1d)
**Depends on:** SGS-013, SGS-014
- Org switcher in the sidebar (persists active org, sets `X-Org-Id` on API calls).
- Settings pages: profile, organization (rename), members (list, roles, invite, remove).
**Acceptance criteria**
- Switching orgs visibly switches all data in the app shell.

---

## EPIC 2 — LLM Layer

Goal: the production-grade LLM plumbing that differentiates this starter — cost tracking,
resilience, rate limiting. This epic is the core value of the repo.

### [x] SGS-020 — Provider abstraction (1d)
**Depends on:** SGS-003
- `src/llm/`: `LLMProvider` protocol with `complete()`, `stream()`, `embed()` — supports tool use and structured outputs (JSON schema).
- Anthropic implementation (default model `claude-sonnet-4-6`), normalized message/response types so domain code never imports `anthropic` directly.
- Embeddings provider: Voyage AI default, behind the same abstraction (Claude does not provide embeddings).
**Acceptance criteria**
- Unit tests with a fake provider; one smoke test against the real API (skipped when no key is present).

### [x] SGS-021 — Resilience: retries, timeouts, circuit breaker (1d)
**Depends on:** SGS-020
- Exponential backoff with jitter on 429/5xx/timeouts (respect `retry-after`), configurable attempt budget.
- Per-call timeout; simple circuit breaker (open after N consecutive failures, half-open probe).
- Errors mapped to typed exceptions (`RateLimited`, `ProviderUnavailable`, `ContextTooLong`).
**Acceptance criteria**
- Tests simulate 429 storms and provider outages; the breaker opens and recovers as configured.

### [x] SGS-022 — Token & cost accounting (1d)
**Depends on:** SGS-020, SGS-013
- Every LLM call records: tenant, feature tag (e.g. `chat`, `rag`, `extraction`), model, input/output/cached tokens, computed cost, latency.
- Pricing table in code (per-model, versioned, easy to update), `llm_usage` table + repository.
- Aggregation queries: cost per tenant per day per feature.
**Acceptance criteria**
- Costs match the pricing table in tests; usage rows are written even when the call fails mid-stream (partial usage captured).

### [x] SGS-023 — Prompt caching (0.5d)
**Depends on:** SGS-020
- Anthropic prompt caching enabled for stable prefixes (system prompts, tool definitions); cache hits reflected in cost accounting (cached-token pricing).
**Acceptance criteria**
- Smoke test demonstrates cache-read tokens on a repeated call; costs account for the discount.

### [x] SGS-024 — Per-tenant rate limiting (0.5d)
**Depends on:** SGS-013
- Redis-backed sliding-window limiter on LLM-consuming endpoints (requests/min and tokens/day per tenant, env-configurable).
- 429 responses include `Retry-After`; limits surfaced in the usage UI later.
**Acceptance criteria**
- Tests prove isolation: tenant A exhausting its quota does not affect tenant B.

### [x] SGS-025 — Chat (no RAG yet): API + UI (1.5d)
**Depends on:** SGS-021, SGS-022, SGS-024
- Models: `Conversation`, `Message` (tenant-scoped).
- `POST /chat/{conversation_id}/messages` streaming via SSE; persists assistant message on completion; handles client disconnect (usage still recorded).
- Web: chat UI with streaming rendering, conversation list, new conversation.
**Acceptance criteria**
- E2E happy path: create conversation → stream a reply → reload page → history intact. Usage rows recorded with feature tag `chat`.

### [x] SGS-026 — Usage dashboard (1d)
**Depends on:** SGS-022, SGS-025
- `(app)/usage`: cost over time (day granularity), breakdown by feature and model, token counts, current rate-limit status.
- API aggregation endpoints with date-range params.
**Acceptance criteria**
- Dashboard matches `llm_usage` aggregates; renders correctly for an empty tenant.

---

## EPIC 3 — RAG Module ("Chat with your documents")

Goal: the demonstrator feature — full ingestion pipeline + cited retrieval in chat.

### [x] SGS-030 — Document upload & storage (1d)
**Depends on:** SGS-013
- `Document` model (tenant-scoped): name, mime type, size, status (`uploaded → processing → ready | failed`), error message.
- Upload endpoint (PDF/TXT, size limit env-configured). Storage behind an interface: local disk in dev, GCS in prod.
**Acceptance criteria**
- Upload rejects oversized/unsupported files with clear errors; files land in tenant-prefixed paths.

### [x] SGS-031 — Async ingestion worker (1d)
**Depends on:** SGS-030
- ARQ worker (Redis) processing ingestion jobs; job enqueue behind a `TaskQueue` interface (Cloud Tasks adapter comes in SGS-041, ARQ stays the local/default driver).
- Status transitions + retries (max 3) + dead-letter logging on permanent failure.
**Acceptance criteria**
- Killing the worker mid-job and restarting resumes cleanly; failed docs end in `failed` with a useful message.

### [x] SGS-032 — Parse, chunk, embed (1.5d)
**Depends on:** SGS-031, SGS-020
- PDF text extraction (pymupdf), plain-text passthrough.
- Chunking: recursive, token-aware (target ~512 tokens, ~64 overlap), preserves page numbers for citations.
- Embed via the provider abstraction; store in `chunks` table with a pgvector column (HNSW index).
- Embedding usage recorded in cost accounting (feature tag `ingestion`).
**Acceptance criteria**
- A 50-page PDF ingests end-to-end locally in < 60s; chunks carry document id, page, and position.

### [x] SGS-033 — Retrieval & citations (1d)
**Depends on:** SGS-032
- Retrieval service: embed query → pgvector cosine top-k (tenant-scoped) → optional re-rank hook (no-op v1).
- Citation type: document name, page, snippet, score.
**Acceptance criteria**
- Retrieval unit-tested against a seeded fixture corpus; cross-tenant leakage test passes.

### [x] SGS-034 — RAG chat with tool use (1.5d)
**Depends on:** SGS-033, SGS-025
- Chat agent gains tools: `search_documents` (retrieval) and `get_workspace_stats` (e.g. "how many documents have I uploaded?" — demonstrates tool use over tenant data).
- Responses include structured citations; web UI renders citation chips with a source panel (document + page + snippet).
- Feature tag `rag` in cost accounting.
**Acceptance criteria**
- Asking a question about an uploaded document streams an answer with at least one correct citation; asking about workspace stats triggers the second tool.

### [x] SGS-035 — Structured metadata extraction (0.5d)
**Depends on:** SGS-032
- On ingestion, one structured-output call extracts: title, language, summary (2 sentences), topics (max 5). Stored on the document, shown in the UI.
**Acceptance criteria**
- Extraction is schema-validated; a failure does not fail ingestion (document stays `ready`, metadata nullable).

### [x] SGS-036 — Documents UI (1d)
**Depends on:** SGS-030, SGS-035
- `(app)/documents`: upload with progress, list with status polling (or SSE), metadata display, delete (removes chunks + storage object).
**Acceptance criteria**
- Full lifecycle from the UI: upload → processing → ready → chat about it → delete.

---

## EPIC 7 — Bring-Your-Own-Key & Multi-Provider (priority: before the EPIC 4 deploy tickets)

Goal: organizations choose their LLM provider + model and supply their own
API keys from the UI — the hosted demo costs the maintainer $0 in LLM usage,
and self-hosters aren't locked to one vendor. Strategy decision 2026-06-12.

### [ ] SGS-070 — Org LLM settings + encrypted key storage (1d)
**Depends on:** SGS-013
- `org_llm_settings` (one row per org): chat_provider (`anthropic | openai`),
  chat_model, embedding_provider (`voyage | openai`), API keys **encrypted at
  rest** (Fernet, key from a new `SECRET_ENCRYPTION_KEY` env var).
- Keys are write-only through the API: responses expose `is_set` + last 4
  chars, never the value. Admin+ can update; member can read the masked view.
- Fallback chain: org settings → env keys (self-host default) → 503.
**Acceptance criteria**
- Keys never appear in any API response, log line or trace; cross-tenant
  test proves org A cannot use or read org B's keys.

### [ ] SGS-071 — Multi-provider resolution (1d)
**Depends on:** SGS-070, SGS-020
- `OpenAIProvider` (chat + embeddings) implementing the existing protocols;
  model allowlist per provider in code (with pricing table entries).
- Factory becomes per-tenant: chat/embedding providers resolved from org
  settings at request/job time (no global lru_cache); worker passes tenant.
- A "test connection" endpoint validates a key with a 1-token call.
**Acceptance criteria**
- Same conversation flow works against both providers (fakes in tests);
  usage rows carry the right model + cost for each provider's pricing.

### [ ] SGS-072 — Provider settings UI (0.5d)
**Depends on:** SGS-071, SGS-015
- Settings page section "AI Provider": provider select, model select
  (filtered by provider), key inputs with masked state, test-connection
  button, clear error states. Chat shows a friendly prompt when no key is
  configured anywhere.
**Acceptance criteria**
- A fresh org can paste a key, pick a model and chat within a minute.

---

## EPIC 4 — Infra, Deploy & Observability

Goal: a reproducible cloud environment and a public live demo at **$0/month**
(strategy decision 2026-06-12): Cloud Run free tier (scale to zero) + Neon
Postgres free tier + Upstash Redis free tier + GCS always-free bucket +
Vercel Hobby; LLM usage is BYO-key (EPIC 7). GCP still requires a billing
account on file — set a low budget alert.

### [x] SGS-040 — API container & production hardening (0.5d)
**Depends on:** SGS-003
- Multi-stage Dockerfile (uv, non-root user, healthcheck), gunicorn/uvicorn workers config, production settings profile (CORS, docs disabled or gated).
**Acceptance criteria**
- `docker build` + run locally serves the API identically to dev.

### [ ] SGS-041 — Terraform: $0 baseline (1.5d)
**Depends on:** SGS-040, SGS-046
- Modules under `infra/terraform/modules/`: `cloud-run` (API service,
  scale-to-zero, within the always-free tier), `cloud-tasks` (ingestion
  queue, OIDC push), `gcs` (documents bucket, always-free us region),
  `secret-manager`, `artifact-registry`; WIF for CI.
- Managed free-tier externals are NOT terraformed (keep the surface small):
  Neon Postgres (DATABASE_URL) and Upstash Redis (REDIS_URL) provisioned
  manually, wired through Secret Manager. Documented in `docs/deploy.md`.
- One `environments/demo/` composition; remote state in GCS.
**Acceptance criteria**
- `terraform apply` from a clean GCP project yields a working API URL;
  `terraform destroy` is clean. `docs/deploy.md` covers Neon/Upstash setup.

### [ ] SGS-046 — Cloud Tasks queue driver + push ingestion endpoint (1d)
**Depends on:** SGS-031
- `CloudTasksQueue` implementing `TaskQueue`: enqueue = HTTP push task
  targeting `POST /internal/jobs/ingest` on the API service itself —
  the separate always-on ARQ worker disappears in prod, so ingestion
  scales to zero too. ARQ remains the local/default driver (`QUEUE_DRIVER`).
- `/internal/jobs/*` endpoints verify the Cloud Tasks OIDC token (audience +
  service account email); 403 otherwise. Retries via queue config (max 3).
**Acceptance criteria**
- Local tests cover the endpoint (valid/invalid OIDC, job execution);
  driver switch is config-only.

### [ ] SGS-042 — Web deployment (Vercel Hobby) (0.5d)
**Depends on:** SGS-004
- Vercel project config (Hobby tier), env wiring (API URL, Better Auth
  secrets, Neon pooled DATABASE_URL), preview deployments on PRs.
**Acceptance criteria**
- main → production deploy; PR → preview URL.

### [ ] SGS-043 — CD workflows (0.5d)
**Depends on:** SGS-041, SGS-042, SGS-006
- GitHub Actions: build/push API image → deploy Cloud Run on main (Workload Identity Federation, no JSON keys); migrations run as a release step against Neon before traffic switch.
**Acceptance criteria**
- A merged PR reaches the demo environment with zero manual steps.

### [x] SGS-044 — OpenTelemetry & structured logs (1d)
**Depends on:** SGS-025
- OTel tracing on API + worker (FastAPI, SQLAlchemy, httpx instrumentation), trace context propagated into LLM call spans (model, tokens, cost as span attributes).
- Export: console in dev, Cloud Trace in prod. Request id + tenant id on every log line.
**Acceptance criteria**
- A single chat request produces one connected trace: HTTP → service → LLM call → DB writes.

### [ ] SGS-045 — Public demo environment (0.5d)
**Depends on:** SGS-043, SGS-072
- BYO-key demo: visitors sign up, paste their own provider key (EPIC 7) and
  use the product — the maintainer pays no LLM cost. Landing + empty states
  explain this. Aggressive platform rate limits stay on.
**Acceptance criteria**
- A stranger with an Anthropic or OpenAI key can sign up and chat with a
  document on the live demo; nothing in the demo consumes maintainer keys.

---

## EPIC 5 — Evals, Admin, Docs & Launch

### [ ] SGS-050 — Eval harness (1d)
**Depends on:** SGS-034
- `evals/`: YAML dataset format (`question`, `expected_facts`, `source_document`), runner that executes the real RAG pipeline against a fixture corpus, LLM-as-judge scoring (faithfulness + citation correctness, 0–1).
- `make evals` prints a score table and writes `evals/results/<git-sha>.json`.
**Acceptance criteria**
- Deterministic-ish runs (temperature 0, fixed judge prompt); a regression in retrieval visibly drops the score.

### [ ] SGS-051 — Eval dataset & baseline (0.5d)
**Depends on:** SGS-050
- 12–15 curated cases over 3 public-domain fixture documents, including negative cases ("the answer is not in the corpus" → expect refusal).
- Baseline score committed and referenced in the README.
**Acceptance criteria**
- `make evals` ≥ 0.8 on baseline; negative cases pass (no hallucinated citations).

### [ ] SGS-052 — Admin panel (1d)
**Depends on:** SGS-026
- Internal-only page (env-gated allowlist of admin emails): tenant list, per-tenant usage/cost, document counts, rate-limit overrides.
**Acceptance criteria**
- Non-admin users get a 404 (not a 403 — don't reveal the route exists).

### [ ] SGS-053 — README & docs (1d)
**Depends on:** everything above
- README: pitch, architecture diagram (mermaid), demo GIF, quickstart (the <10 min path), **"Why these choices"** section (multi-tenancy strategy, cost tracking design, RLS trade-off, queue abstraction), link to live demo.
- `docs/`: deploy guide, auth flow diagram, extending-the-LLM-layer guide.
**Acceptance criteria**
- A senior dev unfamiliar with the repo can explain the architecture after reading the README alone.

### [ ] SGS-054 — Launch (0.5d)
**Depends on:** SGS-053, SGS-045
- 2-min demo video; LinkedIn launch post; submissions: awesome lists, relevant newsletters; GitHub topics/social preview image set.
**Acceptance criteria**
- Repo public, CI badge green, demo live, post published.

---

## EPIC 6 — Billing (optional, post-launch)

### [ ] SGS-060 — Stripe module (2d)
**Depends on:** SGS-013
- Feature-flagged (`BILLING_ENABLED`): plans (free/pro), Stripe Checkout, customer portal, webhook handler (signature-verified, idempotent), subscription state on the organization.
**Acceptance criteria**
- Stripe test-mode E2E: subscribe → webhook updates plan → cancel → downgrade. Disabled flag = zero Stripe code paths executed.

### [ ] SGS-061 — Plan-based quotas (1d)
**Depends on:** SGS-060, SGS-024
- Rate/token limits resolved from the org's plan; upgrade prompts in the UI when limits are hit.
**Acceptance criteria**
- Free-plan tenant hits the cap and sees the upgrade path; pro tenant does not.

---

## Suggested execution order

```
Week 1:  SGS-001 → 006 (foundation), SGS-010 → 011          [done]
Week 2:  SGS-012 → 015 (multi-tenancy), SGS-020 → 021       [done]
Week 3:  SGS-022 → 026 (LLM layer + chat + usage)           [done]
Week 4:  SGS-030 → 036 (RAG), SGS-040 + 044 (container/otel)[done]
Week 5:  SGS-070 → 072 (BYO keys, multi-provider)
Week 6:  SGS-046, SGS-041 → 043, SGS-045 ($0 infra + demo)
Week 7:  SGS-050 → 054 (evals + docs + launch)
Post-launch: EPIC 6
```

Total estimate: ~34 ideal dev-days. Pivot 2026-06-12: BYO-key multi-provider
(EPIC 7) added; infra retargeted to a $0/month stack — Cloud Run free tier +
Cloud Tasks push (no always-on worker) + Neon Postgres + Upstash Redis + GCS
always-free + Vercel Hobby; LLM costs carried by each org's own keys.
