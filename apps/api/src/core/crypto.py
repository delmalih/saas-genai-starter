from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import get_settings


class EncryptionNotConfigured(Exception):
    def __init__(self) -> None:
        super().__init__(
            "SECRET_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().secret_encryption_key
    if not key:
        raise EncryptionNotConfigured()
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Stored secret cannot be decrypted — SECRET_ENCRYPTION_KEY changed?"
        ) from exc
