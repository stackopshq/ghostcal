"""Transactional email: Resend, or an ordinary SMTP relay, with a logging fallback in dev."""

from __future__ import annotations

import asyncio
import base64
import logging
import smtplib
import ssl
from collections.abc import Sequence
from email.message import EmailMessage

import httpx

from ghostcal.application.ports.email import Attachment, EmailSender
from ghostcal.config import Settings

logger = logging.getLogger("ghostcal.email")

_RESEND_ENDPOINT = "https://api.resend.com/emails"


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


class SmtpEmailSender:
    """Send through an ordinary SMTP relay — the one the rest of the deployment already uses.

    Uses the standard library rather than adding an async SMTP dependency: one message per
    booking is not a throughput problem, and ``asyncio.to_thread`` keeps the event loop free
    for the price of a thread. Fewer dependencies is worth more here than fewer threads.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str,
        starttls: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._starttls = starttls

    def build_message(
        self,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        # A plain-text part first, then the HTML alternative: a booking confirmation that
        # renders as raw markup in a text-only client is worse than one sentence of prose.
        message.set_content("This message needs an HTML-capable mail client to display correctly.")
        message.add_alternative(html, subtype="html")
        for attachment in attachments or ():
            maintype, _, subtype = attachment.content_type.partition("/")
            message.add_attachment(
                attachment.content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.filename,
            )
        return message

    def _send_blocking(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=20) as client:
            if self._starttls:
                client.starttls(context=ssl.create_default_context())
            if self._username and self._password:
                client.login(self._username, self._password)
            client.send_message(message)

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        message = self.build_message(to, subject, html, attachments)
        await asyncio.to_thread(self._send_blocking, message)


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
            "Email NOT sent (no email route configured). to=%s subject=%s attachments=[%s]\n%s",
            to,
            subject,
            names,
            html,
        )


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.resend_api_key is not None:
        return ResendEmailSender(settings.resend_api_key.get_secret_value(), settings.email_from)
    if settings.smtp_host is not None:
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=(
                settings.smtp_password.get_secret_value() if settings.smtp_password else None
            ),
            sender=settings.email_from,
            starttls=settings.smtp_starttls,
        )
    # Reachable in development only: Settings refuses to build without a route anywhere else,
    # so this fallback can no longer be the reason a live deployment drops mail in silence.
    logger.warning("No email route configured — emails will be logged, not sent.")
    return LogEmailSender()
