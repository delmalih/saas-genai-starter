# Bootstrap this starter into your product

This guide is written for **coding agents** (Claude Code, Cursor…) as much as
for humans. Given a handful of parameters, it turns the starter into a named,
branded, domain-adapted product with green tests.

## Parameters to collect

| Parameter | Example | Used for |
|---|---|---|
| Product name | `Acme Notes` | UI titles, metadata, README |
| Slug | `acme-notes` | package names, OTel service, Terraform/CI resource names |
| Tagline | `Notes that write themselves` | landing page hero |
| Description | one sentence | meta description, JSON-LD, README |
| GitHub repo | `acme/acme-notes` | links, CI workload identity |

## Step 1 — Rename and rebrand

```bash
python3 scripts/bootstrap.py --name "Acme Notes" --slug acme-notes \
  --tagline "..." --description "..." --github-repo acme/acme-notes
```

The script reads the current identity from `bootstrap.config.json`, rewrites
every occurrence across git-tracked files (longest match first, including the
`snake_case` slug variant), and updates the manifest so it can be run again
later. It deliberately skips lockfiles and generated assets.

Then regenerate what derives from the code and verify nothing broke:

```bash
make generate-client   # OpenAPI title carries the new name
make lint && make test # the gate: everything must stay green
```

## Step 2 — Adapt the example domain

The starter ships a "chat with your documents" RAG product as the example
domain. Keep what your product needs, replace the rest:

- **Domains live in `apps/api/src/domains/`** — one package per domain
  (`router/service/repository/models/schemas`). Copy the shape of
  `documents/` for a new domain; every tenant-owned table uses
  `TenantOwnedMixin` and repositories extend the tenant-scoped base class
  (isolation is enforced there, not in code review).
- **New tables**: `make makemigration m="..."` (and import the models module
  in `apps/api/src/all_models.py` so the worker sees them).
- **Frontend routes live in `apps/web/app/(app)/`** — session-gated by
  `middleware.ts` (add new top-level routes to its matcher). Data fetching
  goes through the generated typed client (`make generate-client` after any
  API change).
- **Landing page**: `apps/web/app/(marketing)/page.tsx` (hero + feature
  grid + JSON-LD), social card in `apps/web/app/opengraph-image.tsx`.
- The LLM layer (`apps/api/src/llm/`), BYO-key settings, usage tracking,
  rate limiting, billing and admin are product-agnostic — leave them.

## Step 3 — Wire your own deployment (optional)

The demo deployment is parameterized but its *values* are this repo's:

- `infra/terraform/environments/demo/variables.tf` — project id, region,
  web URL, admin emails (the slug rename already updated resource names).
  The tfstate bucket in `main.tf`'s backend block must be globally unique.
- GitHub Actions variables `GCP_PROJECT_ID` / `GCP_WIF_PROVIDER` /
  `GCP_DEPLOYER_SA` — from `terraform output` after the first apply.
- Vercel project env: `NEXT_PUBLIC_API_URL`, `BETTER_AUTH_URL`,
  `BETTER_AUTH_SECRET`, `DATABASE_URL` (+ `DATABASE_URL_UNPOOLED`).
- `docs/deploy.md` walks the full sequence (Neon, Upstash, secrets,
  bootstrap image, first apply).

## Step 4 — Final checks

```bash
make lint && make test     # green gate
pnpm --filter web build    # production build
git grep -i "genai starter" # nothing left behind except this guide's history
```

What NOT to rename: Better Auth table names (`auth` schema), Alembic
revision ids, and `docs/` references to third-party services.
