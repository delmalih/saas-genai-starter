import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, Request

from src.core.config import get_settings
from src.core.errors import AuthServiceUnavailable, Unauthorized

JWT_ALGORITHMS = ["EdDSA"]  # Better Auth signs with Ed25519 by default


class JwksCache:
    """Fetches and caches the Better Auth JWKS.

    Keys rotate rarely; a short TTL plus an on-miss refresh covers rotation
    without hitting the auth service on every request.
    """

    def __init__(self, url: str, ttl_seconds: float = 300) -> None:
        self._url = url
        self._ttl = ttl_seconds
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None

    async def _refresh(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self._url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AuthServiceUnavailable() from exc
        self._keys = {
            key_data["kid"]: jwt.PyJWK(key_data)
            for key_data in response.json().get("keys", [])
            if "kid" in key_data
        }
        self._fetched_at = time.monotonic()

    async def get_key(self, kid: str) -> jwt.PyJWK:
        is_stale = self._fetched_at is None or time.monotonic() - self._fetched_at > self._ttl
        if is_stale or kid not in self._keys:
            await self._refresh()
        try:
            return self._keys[kid]
        except KeyError as exc:
            raise Unauthorized("Unknown signing key") from exc


@lru_cache
def get_jwks_cache() -> JwksCache:
    return JwksCache(get_settings().auth_jwks_url)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str | None


async def get_current_user(
    request: Request,
    jwks: Annotated[JwksCache, Depends(get_jwks_cache)],
) -> AuthenticatedUser:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Missing bearer token")

    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Malformed token") from exc
    if not kid:
        raise Unauthorized("Missing key id")

    key = await jwks.get_key(kid)
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key=key,
            algorithms=JWT_ALGORITHMS,
            audience=settings.auth_jwt_audience,
            issuer=settings.auth_jwt_issuer,
            options={"verify_aud": settings.auth_jwt_audience is not None},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid token") from exc

    user_id = claims.get("sub")
    if not user_id:
        raise Unauthorized("Missing subject claim")
    return AuthenticatedUser(user_id=user_id, email=claims.get("email"))


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
