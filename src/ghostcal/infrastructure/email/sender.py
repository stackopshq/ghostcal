"""Transactional email via Brevo or Resend, with a logging fallback when neither is configured."""

from __future__ import annotations

import base64
import logging
from collections.abc import Sequence
from email.utils import parseaddr

import httpx

from ghostcal.application.ports.email import Attachment, EmailSender
from ghostcal.config import Settings

logger = logging.getLogger("ghostcal.email")

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class ResendEmailSender:
    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "from": self._sender,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if attachments:
            payload["attachments"] = [
                {
                    "filename": a.filename,
                    "content": base64.b64encode(a.content).decode("ascii"),
                    "content_type": a.content_type,
                }
                for a in attachments
            ]
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()


class BrevoEmailSender:
    """Transactional email through Brevo's HTTP API.

    Deliberately the API and not Brevo's SMTP relay. The relay is one more set of
    credentials to carry, and a self-serve product is deployed on customer machines
    whose egress address nobody knows in advance — an SMTP relay that authorises by
    IP cannot follow it. One key posted from anywhere can.
    """

    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        # Brevo wants the sender split into a structured object, where Resend takes the
        # RFC 5322 string as-is. Passing `GhostCal <noreply@…>` through unsplit is
        # rejected, so the same `email_from` setting has to be parsed for this provider.
        name, address = parseaddr(sender)
        self._sender: dict[str, str] = {"email": address or sender}
        if name:
            self._sender["name"] = name

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "sender": self._sender,
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        }
        if attachments:
            # `attachment`, singular, and the field is `name` rather than `filename` —
            # Brevo's shape, not Resend's. It also carries no content type: the provider
            # derives it from the extension.
            payload["attachment"] = [
                {
                    "name": a.filename,
                    "content": base64.b64encode(a.content).decode("ascii"),
                }
                for a in attachments
            ]
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _BREVO_ENDPOINT,
                headers={"api-key": self._api_key},
                json=payload,
            )
            response.raise_for_status()


class LogEmailSender:
    """Dev fallback: log the message instead of sending it (no provider configured)."""

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        names = ", ".join(a.filename for a in attachments) if attachments else "none"
        logger.warning(
            "Email NOT sent (no provider key). to=%s subject=%s attachments=[%s]\n%s",
            to,
            subject,
            names,
            html,
        )


def build_email_sender(settings: Settings) -> EmailSender:
    # Brevo wins when both are set: it is the provider the estate authenticated its
    # sending domain with, so it is the one whose messages survive a DMARC p=reject.
    if settings.brevo_api_key is not None:
        return BrevoEmailSender(settings.brevo_api_key.get_secret_value(), settings.email_from)
    if settings.resend_api_key is not None:
        return ResendEmailSender(settings.resend_api_key.get_secret_value(), settings.email_from)
    logger.warning(
        "Neither GHOSTCAL_BREVO_API_KEY nor GHOSTCAL_RESEND_API_KEY is set "
        "— emails will be logged, not sent."
    )
    return LogEmailSender()
