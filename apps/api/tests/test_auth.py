import json
import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.core.auth import JwksCache

KID = "test-key"


@pytest.fixture(scope="module")
def private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture(scope="module")
def other_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def jwk_dict(private_key: Ed25519PrivateKey, kid: str) -> dict[str, Any]:
    public_jwk = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(private_key.public_key()))
    return {**public_jwk, "kid": kid, "alg": "EdDSA"}


def make_token(
    private_key: Ed25519PrivateKey,
    kid: str = KID,
    expires_in: int = 600,
    **claims: Any,
) -> str:
    now = int(time.time())
    payload = {"sub": "user-123", "email": "test@example.com", "iat": now - 10}
    payload["exp"] = now + expires_in
    payload.update(claims)
    return jwt.encode(payload, private_key, algorithm="EdDSA", headers={"kid": kid})


@pytest.fixture(autouse=True)
def jwks_endpoint(monkeypatch: pytest.MonkeyPatch, private_key: Ed25519PrivateKey) -> None:
    """Serve the test JWKS instead of calling the real Better Auth endpoint."""
    keys = {"keys": [jwk_dict(private_key, KID)]}

    async def fake_refresh(self: JwksCache) -> None:
        self._keys = {KID: jwt.PyJWK(keys["keys"][0])}
        self._fetched_at = time.monotonic()

    monkeypatch.setattr(JwksCache, "_refresh", fake_refresh)


async def test_valid_token(client: httpx.AsyncClient, private_key: Ed25519PrivateKey) -> None:
    response = await client.get(
        "/me", headers={"Authorization": f"Bearer {make_token(private_key)}"}
    )
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123", "email": "test@example.com"}


async def test_missing_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_garbage_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


async def test_expired_token(client: httpx.AsyncClient, private_key: Ed25519PrivateKey) -> None:
    token = make_token(private_key, expires_in=-60)
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


async def test_bad_signature(
    client: httpx.AsyncClient, other_private_key: Ed25519PrivateKey
) -> None:
    # Signed by a key the JWKS does not know — same kid, different key pair.
    token = make_token(other_private_key, kid=KID)
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_unknown_kid(client: httpx.AsyncClient, private_key: Ed25519PrivateKey) -> None:
    token = make_token(private_key, kid="rotated-away")
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "signing key" in response.json()["error"]["message"].lower()


async def test_missing_sub_claim(client: httpx.AsyncClient, private_key: Ed25519PrivateKey) -> None:
    token = make_token(private_key, sub="")
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
