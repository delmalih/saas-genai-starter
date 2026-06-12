# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) — or any AI coding assistant —
when working with code in this repository.

## Project Overview

`saas-genai-starter` is an **open-source, production-grade SaaS starter for GenAI products**.
It is a public portfolio project: code quality, architecture clarity, and documentation matter
as much as features. The pitch: "the starter I wish I had when founding my last SaaS" —
it covers what demo-grade starters ignore: multi-tenancy, LLM cost tracking, resilience,
observability, infra as code, tests, and evals.

**Everything in this repo is written in English** (code, comments, docs, commit messages,
README), even if the maintainer communicates in French. Never write French in committed files.

## Workflow

- The development backlog lives in `tech-steps.md` (Jira-style tickets, `SGS-XXX` IDs).
  Work ticket by ticket, respect the dependency order, and update the ticket checkbox
  (`[ ]` → `[~]` → `[x]`) when starting/finishing one.
- Branch names: `sgs-021-llm-resilience`. Commit messages: conventional commits with the
  ticket ID, e.g. `feat(llm): add retry with exponential backoff [SGS-021]`.
- Every ticket has acceptance criteria — they define "done". Write the tests they imply.
- Asked to turn this starter into a new product (rename, rebrand, new domain)?
  Follow `BOOTSTRAP.md` — collect its parameters, run `scripts/bootstrap.py`,
  then `make generate-client && make lint && make test` as the gate.

## Commands

```bash
make setup        # Install all deps (pnpm install, uv sync) + create local DB
make dev          # Boot docker-compose (postgres+pgvector, redis) + API + web
make worker       # ARQ worker (document ingestion) — needed for uploads
make test         # Run all tests (web + api)
make lint         # ruff + mypy (api), eslint + tsc (web)
make evals        # RAG eval harness — REAL API calls (Anthropic + Voyage keys), ~7 min
make migrate      # alembic upgrade head
make makemigration m="..."   # Autogenerate an alembic migration
make generate-client          # Regenerate the typed TS client from OpenAPI
```

App-specific:
```bash
cd apps/web && pnpm dev       # Next.js only (port 3000)
cd apps/api && uv run uvicorn src.main:app --reload   # API only (port 8000)
cd apps/api && uv run pytest                           # API tests only
```

## Architecture

```
apps/
├── web/                  # Next.js 15, App Router, TypeScript strict
│   ├── app/(marketing)/  # Public landing page
│   ├── app/(app)/        # Protected app: chat, documents, usage, settings, admin
│   ├── components/ui/    # shadcn/ui (vendored)
│   └── lib/api/          # Typed client generated from FastAPI OpenAPI + fetch/SSE wrapper
├── api/                  # FastAPI, Python 3.12, managed with uv
│   ├── src/core/         # config (pydantic-settings), db (SQLAlchemy 2 async), logging, telemetry
│   ├── src/domains/      # One package per domain: tenants/, chat/, documents/, usage/, billing/
│   │   └── <domain>/     # router.py, service.py, repository.py, models.py, schemas.py
│   ├── src/llm/          # Provider abstraction, resilience, cost accounting, rate limiting
│   └── tests/
infra/terraform/          # GCP modules: cloud-run, cloud-sql, secret-manager, cloud-tasks, gcs
evals/                    # YAML datasets + LLM-as-judge runner
```

### Key architectural decisions (do not silently change these)

- **Auth**: Better Auth lives in the Next.js app (Postgres-backed, `auth` schema). FastAPI
  validates Better Auth JWTs via the web app's JWKS endpoint. The API never manages
  credentials itself.
- **Multi-tenancy**: every tenant-owned table has an indexed `tenant_id`. Data access goes
  through a repository base class that injects the tenant filter — domain code can never
  forget it. The active org comes from the `X-Org-Id` header, verified against membership.
  Postgres RLS is documented as a hardening option, not implemented in v1.
- **LLM layer** (`src/llm/`): domain code never imports vendor SDKs — always go through
  the `ChatProvider`/`EmbeddingProvider` protocols. Normalized messages use
  Anthropic-shaped content blocks as the lingua franca; each provider translates
  (see `openai_provider.py`). Every call records tenant, feature tag, tokens (incl.
  cached), cost (Decimal pricing table), and latency to `llm_usage`. Resilience
  (retry/backoff, circuit breaker — 429s never trip the breaker) and per-tenant rate
  limiting (Redis, fail-open) live in this layer.
- **BYO keys / multi-provider** (pivot 2026-06-12): each org picks provider + model and
  stores its own API keys, Fernet-encrypted (`SECRET_ENCRYPTION_KEY`), write-only through
  the API (`is_set` + last4 only). Resolution: org key → server env key → 503 with
  guidance. Providers resolved per tenant in `src/domains/llm_settings/resolver.py`
  (cached by key fingerprint). Model allowlists live in `src/llm/catalog.py`.
- **Model registry**: standalone entry points (worker, alembic, scripts) must import
  `src/all_models.py` — without it, lazy ForeignKey resolution fails with
  "could not find table". A fresh-interpreter test guards this.
- **Platform admin** (`/admin`): gated by the `ADMIN_EMAILS` allowlist; non-admins get
  404 (never 403). The only module allowed to query tenant-owned tables without a
  TenantContext. Per-org rate-limit overrides live on `organizations` and ride in
  `TenantContext`.
- **Evals** (`evals/`): `make evals` runs the real pipeline + LLM judge; baseline in
  `evals/results/`. Treat a score drop as a regression. Embedding calls are paced for
  the Voyage free tier (~3 req/min).
- **Async jobs**: behind a `TaskQueue` interface. ARQ (Redis) is the local/default driver;
  Cloud Tasks is the production driver. Workers are idempotent and retried (max 3).
- **Storage**: behind an interface — local disk in dev, GCS in prod. Tenant-prefixed paths.
- **Streaming**: chat uses SSE. Usage must be recorded even on client disconnect or
  mid-stream failure.
- **Vector search**: pgvector (HNSW, cosine) in the same Postgres — no separate vector DB.
  Chunks keep document id + page number for citations.

## Code Conventions

### TypeScript / Next.js
- React Server Components by default; add `"use client"` only when required. Minimize
  `useEffect`/`useState`.
- TypeScript strict. Prefer `interface` over `type`. No `enum` — use const maps.
- Functional components, named exports. Directories in lowercase-with-dashes.
- Tailwind (mobile-first) + shadcn/ui patterns; `cva` for variants, `clsx`/`tailwind-merge`
  for class merging.

### Python / FastAPI
- Python 3.12, fully typed, mypy-clean. Ruff for lint + format.
- SQLAlchemy 2 style (`Mapped[...]`, `mapped_column`), async sessions everywhere.
- Pydantic v2 schemas at the API boundary; domain services take/return domain types.
- Dependency injection via FastAPI `Depends` for auth, tenant, db session.
- Raise typed exceptions (`RateLimited`, `ProviderUnavailable`, ...) — a single exception
  handler maps them to the error envelope. No bare `except`.
- Tests: pytest + pytest-asyncio, transactional DB fixture per test, fake LLM provider for
  unit tests, real-API smoke tests marked and skipped without keys.

### General
- No secrets in code or committed files, ever — env vars only, `.env.example` documents them.
- Comments only for non-obvious constraints; never narrate what code does.
- Every PR: tests for the ticket's acceptance criteria, CI green, generated client fresh.
- Cross-tenant isolation is the #1 invariant — when touching any repository or query,
  preserve and test tenant scoping.

## Environment

- Local infra via `docker-compose`: postgres:16 + pgvector, redis:7.
- Required env vars (see `.env.example`): `DATABASE_URL`, `REDIS_URL`,
  `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`, `NEXT_PUBLIC_API_URL`,
  `SECRET_ENCRYPTION_KEY` (Fernet, for org-provided API keys).
- LLM keys are optional server-side (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `VOYAGE_API_KEY`) — they are the fallback when an org has not configured its own
  keys in Settings → AI Provider.
- Optional/env-gated: Google OAuth creds, Resend (emails), `ADMIN_EMAILS`,
  OTel (`OTEL_ENABLED`), Stripe (billing flag), GCS bucket.
