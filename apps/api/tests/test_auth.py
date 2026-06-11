import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.jwt_utils import KID, make_token


@pytest.fixture(scope="module")
def other_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


async def test_valid_token(client: httpx.AsyncClient, signing_key: Ed25519PrivateKey) -> None:
    response = await client.get(
        "/me", headers={"Authorization": f"Bearer {make_token(signing_key)}"}
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


async def test_expired_token(client: httpx.AsyncClient, signing_key: Ed25519PrivateKey) -> None:
    token = make_token(signing_key, expires_in=-60)
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


async def test_unknown_kid(client: httpx.AsyncClient, signing_key: Ed25519PrivateKey) -> None:
    token = make_token(signing_key, kid="rotated-away")
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "signing key" in response.json()["error"]["message"].lower()


async def test_missing_sub_claim(client: httpx.AsyncClient, signing_key: Ed25519PrivateKey) -> None:
    token = make_token(signing_key, sub="")
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
