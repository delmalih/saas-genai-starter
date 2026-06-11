from functools import lru_cache
from typing import Protocol

import httpx
import structlog

from src.core.config import get_settings

logger = structlog.get_logger(__name__)


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, text: str) -> None: ...


class ConsoleEmailSender:
    """Local dev driver: emails land in the server logs."""

    async def send(self, to: str, subject: str, text: str) -> None:
        logger.info("email.console", to=to, subject=subject, body=text)


class ResendEmailSender:
    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    async def send(self, to: str, subject: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"from": self._sender, "to": [to], "subject": subject, "text": text},
            )
            response.raise_for_status()


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_settings()
    if settings.resend_api_key:
        return ResendEmailSender(settings.resend_api_key, settings.email_from)
    return ConsoleEmailSender()
