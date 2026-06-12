# --- Builder: resolve and install dependencies with uv -----------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first — cached as long as the lockfile doesn't change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

# --- Runtime ------------------------------------------------------------------
FROM python:3.12-slim-bookworm

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

USER appuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

# Cloud Run injects PORT; single worker per instance, concurrency handled
# by the platform scaling instances.
CMD exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}
