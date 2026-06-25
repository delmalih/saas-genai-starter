# Contributing to saas-genai-starter

Thanks for contributing! This guide covers everything you need to get started.

---

## Setup

**Prerequisites:** Node.js 22+, Python 3.12+, Docker, [uv](https://github.com/astral-sh/uv), pnpm

```bash
# Install all dependencies and create local env files
make setup

# Start local infra (Docker) + API + web
make dev
```

- API runs at `http://localhost:8000`
- Web runs at `http://localhost:3000`

---

## Lint & Test

```bash
# Run all lint checks
make lint

# Run all tests
make test
```

Both must pass before submitting a PR.

---

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Fireworks AI chat provider
fix: handle missing API key gracefully
docs: update provider setup guide
chore: bump dependency versions
```

---

## Adding a New AI Provider

The fastest contribution path is adding a new chat or embedding provider — see
the step-by-step [provider guide](docs/extending-llm-providers.md). Most
providers speak the OpenAI-compatible API, so adding one is a **catalog entry**,
not a new class.

The essentials (the guide has the full checklist):
1. Add the provider to the catalog in `apps/api/src/llm/catalog.py` (write a
   native client under `apps/api/src/llm/` only if it isn't OpenAI-compatible).
2. Add its encrypted key column (plus an Alembic migration via
   `make makemigration`), settings field, and env fallback.
3. Add per-model pricing in `apps/api/src/llm/pricing.py`.
4. Add the key label in `apps/web/components/settings/ai-provider-card.tsx`,
   then run `make generate-client` and **commit the regenerated
   `apps/web/lib/api/` files** — CI fails if they drift.
5. Add the provider id to the expected set in
   `tests/test_llm_settings.py::test_catalog_lists_providers` — it pins the
   catalog, so that test fails until you update it by hand.
6. Run `make lint && make test`. The parameterized test in
   `tests/llm/test_compatible_providers.py` enforces the pricing/key/settings
   checklist, but the catalog-list test in step 5 is not automatic.

---

## Issue Templates

When opening an issue, use the appropriate template:

- **Bug report** — unexpected behavior, errors, crashes
- **Feature request** — new providers, new capabilities, improvements

---

## Pull Request Checklist

- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] Typed client regenerated if the API changed (`make generate-client`)
- [ ] New env vars added to `.env.example`
- [ ] PR description references the related issue (`Closes #N`)

---

## Code of Conduct & license

By contributing you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md)
and that your contributions are licensed under the project's [MIT license](LICENSE).

Using this repo as a starter for your own product rather than contributing? See
[`BOOTSTRAP.md`](BOOTSTRAP.md).
