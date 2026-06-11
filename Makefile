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

evals: ## Run the RAG eval harness (requires API keys) — SGS-050
	@echo "Not implemented yet (SGS-050)"

migrate: ## Apply database migrations — wired in SGS-003
	@echo "Not implemented yet (SGS-003)"

makemigration: ## Autogenerate a migration: make makemigration m="add users" — wired in SGS-003
	@echo "Not implemented yet (SGS-003)"

generate-client: ## Regenerate the typed TS client from OpenAPI — wired in SGS-005
	@echo "Not implemented yet (SGS-005)"
