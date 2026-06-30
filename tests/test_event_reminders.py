"""Unit tests for calendar-event reminder dispatch (no DB): recurrence-aware, idempotent, ZK."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from ghostcal.application.event_reminders import DueEvent, dispatch_event_reminders

ORG = uuid.uuid4()
EV = uuid.uuid4()


def _event() -> DueEvent:
    return DueEvent(
        event_id=EV,
        organization_id=ORG,
        owner_email="owner@example.com",
        owner_timezone="UTC",
        start_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),  # Monday 09:00 UTC
        end_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        timezone="UTC",
        rrule="FREQ=WEEKLY;BYDAY=MO",
        exdates=(),
        reminder_minutes=60,
    )


class FakeGateway:
    def __init__(self, events: list[DueEvent]) -> None:
        self._events = events
        self.claimed: set[tuple[uuid.UUID, datetime]] = set()

    async def due_events(self) -> list[DueEvent]:
        return self._events

    async def claim(self, event_id: uuid.UUID, organization_id: uuid.UUID, occ: datetime) -> bool:
        key = (event_id, occ)
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, html: str, attachments: object = None) -> None:
        self.sent.append({"to": to, "subject": subject, "html": html})


async def test_reminder_fires_once_when_due_and_is_idempotent() -> None:
    gw = FakeGateway([_event()])
    mailer = FakeMailer()
    now = datetime(2026, 6, 1, 8, 2, tzinfo=UTC)  # reminder moment (08:00) just passed
    window = timedelta(minutes=5)

    sent = await dispatch_event_reminders(gw, mailer, now=now, scan_window=window)
    assert sent == 1
    assert mailer.sent[0]["to"] == "owner@example.com"
    assert "08:00" not in mailer.sent[0]["html"]  # email shows the *event* time, not the reminder
    # Zero-knowledge: the email never names the event.
    assert "encrypted" in mailer.sent[0]["html"].lower()

    # A second run with the same now claims nothing new.
    again = await dispatch_event_reminders(gw, mailer, now=now, scan_window=window)
    assert again == 0


async def test_reminder_not_sent_before_its_moment() -> None:
    gw = FakeGateway([_event()])
    mailer = FakeMailer()
    now = datetime(2026, 6, 1, 7, 0, tzinfo=UTC)  # before the 08:00 reminder moment
    sent = await dispatch_event_reminders(gw, mailer, now=now, scan_window=timedelta(minutes=5))
    assert sent == 0
    assert mailer.sent == []
