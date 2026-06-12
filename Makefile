.PHONY: setup dev dev-api dev-web test test-api test-web lint lint-api lint-web evals migrate makemigration generate-client

setup: ## Install all dependencies and create local env files
	pnpm install
	cd apps/api && uv sync
	test -f apps/api/.env || cp apps/api/.env.example apps/api/.env
	test -f apps/web/.env || cp apps/web/.env.example apps/web/.env

dev: ## Boot local infra + API + web
	docker compose up -d --wait
	$(MAKE) -j2 dev-api dev-web

dev-api:
	cd apps/api && uv run uvicorn src.main:app --reload --port 8000

dev-web:
	pnpm --filter web dev

worker: ## Run the ARQ background worker (document ingestion)
	cd apps/api && uv run arq src.worker.WorkerSettings

test: test-api test-web

test-api:
	cd apps/api && uv run pytest

test-web:
	pnpm --filter web test --if-present

lint: lint-api lint-web

lint-api:
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-web:
	pnpm --filter web lint
	pnpm --filter web exec tsc --noEmit

evals: ## Run the RAG eval harness (requires ANTHROPIC_API_KEY + VOYAGE_API_KEY)
	cd apps/api && PYTHONPATH=. uv run python ../../evals/runner.py $(ARGS)

migrate: ## Apply database migrations
	cd apps/api && uv run alembic upgrade head

makemigration: ## Autogenerate a migration: make makemigration m="add users"
	cd apps/api && uv run alembic revision --autogenerate -m "$(m)"

generate-client: ## Regenerate the typed TS client from the FastAPI OpenAPI schema
	cd apps/api && PYTHONPATH=. uv run python scripts/export_openapi.py > ../web/lib/api/openapi.json
	pnpm --filter web exec openapi-typescript lib/api/openapi.json -o lib/api/schema.d.ts
