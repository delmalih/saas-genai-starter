import json
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KID = "test-key"


def jwk_dict(private_key: Ed25519PrivateKey, kid: str = KID) -> dict[str, Any]:
    public_jwk = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(private_key.public_key()))
    return {**public_jwk, "kid": kid, "alg": "EdDSA"}


def make_token(
    private_key: Ed25519PrivateKey,
    kid: str = KID,
    expires_in: int = 600,
    **claims: Any,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": "user-123",
        "email": "test@example.com",
        "iat": now - 10,
        "exp": now + expires_in,
    }
    payload.update(claims)
    return jwt.encode(payload, private_key, algorithm="EdDSA", headers={"kid": kid})
