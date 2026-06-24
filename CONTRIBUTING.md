# Contributing to saas-genai-starter

Thanks for contributing! This guide covers everything you need to get started.

---

## Setup

**Prerequisites:** Node.js 18+, Python 3.11+, Docker, [uv](https://github.com/astral-sh/uv), pnpm

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

The fastest contribution path is adding a new chat or embedding provider.

Providers live in `apps/api/src/llm/`. Use an existing provider as a template.

Steps:
1. Add the provider class in `apps/api/src/llm/`
2. Register it in the provider registry
3. Add the API key to `apps/api/.env.example` with a comment
4. Add a brief entry in `README.md` under the providers section
5. Run `make lint && make test`

---

## Issue Templates

When opening an issue, use the appropriate template:

- **Bug report** — unexpected behavior, errors, crashes
- **Feature request** — new providers, new capabilities, improvements

---

## Pull Request Checklist

- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] New env vars added to `.env.example`
- [ ] PR description references the related issue (`Closes #N`)
