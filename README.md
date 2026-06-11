# saas-genai-starter

> **Work in progress** — not ready for use yet.

A production-grade, open-source SaaS starter for GenAI products: multi-tenancy, LLM cost
tracking, resilience, observability, infra as code, tests, and evals — the parts that
demo-grade starters ignore.

**Stack**: Next.js 15 · FastAPI (Python 3.12) · PostgreSQL 16 + pgvector · Claude API ·
Terraform (GCP Cloud Run) · Vercel.

## Quickstart

```bash
make setup   # install dependencies, create the local database
make dev     # postgres + redis (docker), API on :8000, web on :3000
```

See `CLAUDE.md` for architecture and conventions, and `tech-steps.md` for the roadmap.
