# Contributing

Thanks for your interest in improving **saas-genai-starter**! This project is a
production-grade boilerplate, so the bar is "would I ship this to a client" —
but the contribution loop is meant to be fast and friendly.

## Getting started

**Prerequisites**: Node ≥ 22 (`corepack enable pnpm`),
[uv](https://docs.astral.sh/uv/), and a Docker runtime.

```bash
git clone https://github.com/delmalih/saas-genai-starter && cd saas-genai-starter
make setup    # install deps + create .env files
make migrate  # database schema
make dev      # postgres + redis (docker), API on :8000, web on :3000
make worker   # second terminal — document ingestion
```

## The gate

Every change must keep these green before you open a PR:

```bash
make lint   # ruff + mypy (api), eslint + tsc (web), formatting
make test   # pytest (api), component/build checks (web)
```

If you touch the API surface, regenerate the typed client and commit the result:

```bash
make generate-client
```

CI runs the same checks and will block a PR that drifts.

## Conventions

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org),
  scoped, with the ticket id when there is one — e.g.
  `feat(llm): add Together provider [SGS-080]`.
- **Code style**: TypeScript strict + functional components on the web; Python
  3.12 with strict ruff + mypy on the api. Architecture decisions you shouldn't
  silently change are documented in [`CLAUDE.md`](CLAUDE.md).
- **Tests are part of the change**, not a follow-up. Provider work is covered by
  a parameterized checklist test — see below.

## Adding an LLM provider (the common contribution)

Most providers speak the OpenAI-compatible API, so adding one is a catalog
entry, not a new class. The full checklist (catalog, key column, pricing, UI
label) lives in
[`docs/extending-llm-providers.md`](docs/extending-llm-providers.md). The
parameterized test in `apps/api/tests/llm/test_compatible_providers.py` enforces
it — a missing pricing entry or key column fails CI.

Several of these are open as
[`good first issue`](https://github.com/delmalih/saas-genai-starter/labels/good%20first%20issue).

## Making the starter your own

If you're using this as a boilerplate rather than contributing to it, see
[`BOOTSTRAP.md`](BOOTSTRAP.md) — it (and `scripts/bootstrap.py`) rebrands and
re-domains the starter from a handful of parameters.

## Pull request process

1. Fork, branch (`feat/short-description`), make your change with tests.
2. Run `make lint && make test` (and `make generate-client` if the API changed).
3. Open a PR using the template; link the issue it closes.
4. Be responsive to review — the maintainer aims to reply quickly.

By contributing, you agree your contributions are licensed under the project's
[MIT license](LICENSE), and you are expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
