"""Transactional email via Resend, with a logging fallback when no API key is configured."""

from __future__ import annotations

import logging

import httpx

from ghostcal.application.ports.email import EmailSender
from ghostcal.config import Settings

logger = logging.getLogger("ghostcal.email")

_RESEND_ENDPOINT = "https://api.resend.com/emails"


class ResendEmailSender:
    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    async def send(self, *, to: str, subject: str, html: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"from": self._sender, "to": [to], "subject": subject, "html": html},
            )
            response.raise_for_status()


class LogEmailSender:
    """Dev fallback: log the message instead of sending it (no provider configured)."""

    async def send(self, *, to: str, subject: str, html: str) -> None:
        logger.warning("Email NOT sent (no RESEND key). to=%s subject=%s\n%s", to, subject, html)


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.resend_api_key is not None:
        return ResendEmailSender(settings.resend_api_key.get_secret_value(), settings.email_from)
    logger.warning("GHOSTCAL_RESEND_API_KEY is not set — emails will be logged, not sent.")
    return LogEmailSender()
