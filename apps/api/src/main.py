from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.errors import register_error_handlers
from src.core.health import router as health_router
from src.core.logging import setup_logging
from src.domains.chat.router import router as chat_router
from src.domains.tenants.router import invitations_router
from src.domains.tenants.router import router as tenants_router
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
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(users_router)
    app.include_router(tenants_router)
    app.include_router(invitations_router)
    app.include_router(chat_router)
    return app


app = create_app()
