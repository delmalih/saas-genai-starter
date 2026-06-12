import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.errors import register_error_handlers
from src.core.health import router as health_router
from src.core.logging import setup_logging
from src.core.telemetry import setup_telemetry
from src.domains.admin.router import router as admin_router
from src.domains.chat.router import router as chat_router
from src.domains.documents.router import router as documents_router
from src.domains.llm_settings.router import router as llm_settings_router
from src.domains.tenants.router import invitations_router
from src.domains.tenants.router import router as tenants_router
from src.domains.usage.router import router as usage_router
from src.domains.users.router import router as users_router


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="saas-genai-starter API",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        # The web app calls the API from the browser with Authorization and
        # X-Org-Id headers — both trigger CORS preflights.
        allow_origins=[settings.web_base_url],
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Org-Id"],
        max_age=600,
    )

    @app.middleware("http")
    async def log_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Every log line in the request carries these via structlog contextvars.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=uuid.uuid4().hex[:12],
            tenant_id=request.headers.get("X-Org-Id"),
        )
        return await call_next(request)

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(users_router)
    app.include_router(tenants_router)
    app.include_router(invitations_router)
    app.include_router(chat_router)
    app.include_router(usage_router)
    app.include_router(documents_router)
    app.include_router(llm_settings_router)
    app.include_router(admin_router)
    setup_telemetry(app)
    return app


app = create_app()
