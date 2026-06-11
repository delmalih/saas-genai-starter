import os
import time
from collections.abc import AsyncIterator, Callable

# Test settings must be in place before any src import triggers get_settings().
os.environ["APP_ENV"] = "test"
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from src.core.auth import JwksCache
from src.core.config import get_settings
from src.core.db import Base, get_db
from src.main import create_app

from tests.jwt_utils import KID, jwk_dict, make_token

AuthHeaderFactory = Callable[..., dict[str, str]]


@pytest.fixture(scope="session")
def signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture(autouse=True)
def jwks_endpoint(monkeypatch: pytest.MonkeyPatch, signing_key: Ed25519PrivateKey) -> None:
    """Serve the test JWKS instead of calling the real Better Auth endpoint."""
    key = jwt.PyJWK(jwk_dict(signing_key))

    async def fake_refresh(self: JwksCache) -> None:
        self._keys = {KID: key}
        self._fetched_at = time.monotonic()

    monkeypatch.setattr(JwksCache, "_refresh", fake_refresh)


@pytest.fixture
def auth_headers(signing_key: Ed25519PrivateKey) -> AuthHeaderFactory:
    def make(
        user_id: str = "user-123",
        email: str | None = "test@example.com",
        name: str | None = "Test User",
    ) -> dict[str, str]:
        token = make_token(signing_key, sub=user_id, email=email, name=name)
        return {"Authorization": f"Bearer {token}"}

    return make


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session joined to an outer transaction that is always rolled back —
    tests never leak state into each other or into the test database.

    `create_savepoint` makes in-request `session.commit()` release a savepoint
    instead of committing the outer transaction.
    """
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # Mirror the production shape of the Better Auth schema (read-only
        # lookups in repositories) without running the auth service.
        await connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS auth")
        await connection.exec_driver_sql(
            'CREATE TABLE IF NOT EXISTS auth."user" (id text PRIMARY KEY, email text, name text)'
        )
        await connection.run_sync(Base.metadata.create_all)
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def app(db_session: AsyncSession) -> FastAPI:
    application = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
