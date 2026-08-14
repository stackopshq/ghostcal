"""The email route: which sender gets built, and what an SMTP message actually contains.

The bug these cover shipped on 2026-08-14: a production deployment with no route configured
answered 200 to every booking and wrote the confirmations to a log file. Nothing failed, so
nothing was noticed until an invitee said they had received nothing.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ghostcal.application.ports.email import Attachment
from ghostcal.config import Settings
from ghostcal.infrastructure.email.sender import (
    LogEmailSender,
    ResendEmailSender,
    SmtpEmailSender,
    build_email_sender,
)

REQUIRED = {
    "database_url": "postgresql+asyncpg://u:p@localhost/db",
    "redis_url": "redis://localhost:6379/0",
    "secret_key": "x" * 48,
    "token_encryption_key": "y" * 48,
}


def settings(**overrides: object) -> Settings:
    return Settings(**{**REQUIRED, **overrides})  # type: ignore[arg-type]


def test_resend_wins_when_both_routes_are_configured() -> None:
    sender = build_email_sender(
        settings(environment="production", resend_api_key="re_x", smtp_host="smtp.example.com")
    )
    assert isinstance(sender, ResendEmailSender)


def test_smtp_is_used_when_no_resend_key() -> None:
    sender = build_email_sender(settings(environment="production", smtp_host="smtp.example.com"))
    assert isinstance(sender, SmtpEmailSender)


def test_development_still_falls_back_to_logging() -> None:
    assert isinstance(build_email_sender(settings(environment="development")), LogEmailSender)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_no_route_outside_development_refuses_to_start(environment: str) -> None:
    # The heart of it. Without this, the deployment boots, serves bookings, and drops mail.
    with pytest.raises(ValidationError, match="no email route configured"):
        settings(environment=environment)


def test_smtp_message_carries_both_parts_and_the_invitation() -> None:
    sender = SmtpEmailSender(
        host="smtp.example.com",
        port=587,
        username=None,
        password=None,
        sender="GhostCal <noreply@example.com>",
        starttls=True,
    )
    message = sender.build_message(
        "invitee@example.com",
        "Confirmed: intro call",
        "<p>See you Tuesday</p>",
        [
            Attachment(
                filename="invite.ics", content=b"BEGIN:VCALENDAR", content_type="text/calendar"
            )
        ],
    )

    assert message["To"] == "invitee@example.com"
    assert message["Subject"] == "Confirmed: intro call"
    types = {part.get_content_type() for part in message.walk()}
    # A calendar client that only reads text/plain must still get something readable, and the
    # .ics has to survive as an attachment rather than being inlined into the body.
    assert {"text/plain", "text/html", "text/calendar"} <= types
    attachments = [p for p in message.iter_attachments() if p.get_filename() == "invite.ics"]
    assert len(attachments) == 1
    assert attachments[0].get_payload(decode=True) == b"BEGIN:VCALENDAR"
