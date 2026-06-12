# Deployment — the $0/month stack

> **Status: in progress** — the Terraform for this lives in
> `infra/terraform/` and is being built (see `tech-steps.md`, EPIC 4).
> This page documents the target architecture and the manual pieces.

The demo deployment is designed to cost **$0/month** at hobby traffic:

| Concern | Service | Free tier |
|---|---|---|
| LLM + embeddings | **Users' own keys** (BYO, per org) | n/a |
| API + ingestion | Cloud Run (scale-to-zero) + Cloud Tasks push | Always-free tier |
| Postgres + pgvector | [Neon](https://neon.tech) | 0.5 GB, autosuspend/resume |
| Redis (rate limits) | [Upstash](https://upstash.com) | 500k commands/month |
| Document storage | GCS (us region) | 5 GB always-free |
| Frontend | Vercel Hobby | Free |
| Email | Resend | 3,000/month |

Notes and gotchas:

- **GCP requires a billing account on file** even within the free tier —
  set a budget alert.
- **Neon**: use the *direct* (non-pooled) connection string for the API and
  Alembic — asyncpg's prepared statements break behind the pgbouncer pooler.
  The Next.js app (Better Auth) can use the pooled string.
- **Worker**: in production the always-on ARQ worker is replaced by Cloud
  Tasks pushing to an internal HTTP endpoint on the API service itself
  (OIDC-verified), so ingestion scales to zero too. ARQ remains the local
  driver.
- **Redis is optional in a pinch**: the rate limiter fails open with an
  error log if Redis is unreachable.
