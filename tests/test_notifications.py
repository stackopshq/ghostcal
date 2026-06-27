"""Unit tests for booking notification emails (no DB, no real provider)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace

from ghostcal.application.notifications import (
    build_ics,
    send_booking_cancellation,
    send_booking_confirmation,
)
from ghostcal.application.ports.email import Attachment
from ghostcal.application.scheduling import BookingConfirmation

BOOKING_ID = uuid.uuid4()
CONF = BookingConfirmation(
    booking_id=BOOKING_ID,
    host_id=uuid.uuid4(),
    event_title="Intro call",
    host_name="Kevin",
    host_email="kevin@example.com",
    host_timezone="Europe/Zurich",
    invitee_name="Alice",
    invitee_email="alice@example.com",
    invitee_timezone="America/New_York",
    location_type="google_meet",
    start_at=datetime(2027, 6, 7, 13, 0, tzinfo=UTC),
    end_at=datetime(2027, 6, 7, 13, 30, tzinfo=UTC),
)


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[SimpleNamespace] = []

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        self.sent.append(
            SimpleNamespace(to=to, subject=subject, html=html, attachments=list(attachments or []))
        )


def test_build_ics_has_required_fields() -> None:
    ics = build_ics(CONF)
    assert "BEGIN:VEVENT" in ics
    assert f"UID:{BOOKING_ID}@ghostcal" in ics
    assert "DTSTART:20270607T130000Z" in ics
    assert "DTEND:20270607T133000Z" in ics
    assert "SUMMARY:Intro call with Kevin" in ics


async def test_confirmation_emails_invitee_and_host() -> None:
    mailer = FakeMailer()
    await send_booking_confirmation(mailer, CONF)

    assert {m.to for m in mailer.sent} == {"alice@example.com", "kevin@example.com"}
    for m in mailer.sent:
        assert "Intro call" in m.subject
        assert len(m.attachments) == 1
        assert m.attachments[0].filename == "invite.ics"
        assert m.attachments[0].content_type == "text/calendar"


async def test_cancellation_emails_invitee() -> None:
    mailer = FakeMailer()
    await send_booking_cancellation(
        mailer,
        invitee_email="alice@example.com",
        invitee_timezone="America/New_York",
        event_title="Intro call",
        host_name="Kevin",
        start_at=CONF.start_at,
    )
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "alice@example.com"
    assert "Cancelled" in mailer.sent[0].subject
