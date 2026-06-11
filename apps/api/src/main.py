from fastapi import FastAPI

from src.core.config import get_settings
from src.core.health import router as health_router
from src.core.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="saas-genai-starter API",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.include_router(health_router)
    return app


app = create_app()
