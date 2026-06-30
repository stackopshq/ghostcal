"""Calendar event reminders: find occurrences whose reminder moment has arrived and email the owner.

Recurrence is expanded here (in Python) with the domain engine; the gateway only lists reminder-
enabled events and atomically claims each (event, occurrence) so a reminder is sent at most once.
The email never names the event — the content is zero-knowledge.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from ghostcal.application.notifications import send_event_reminder
from ghostcal.application.ports.email import EmailSender
from ghostcal.domain.calendar import RecurringEvent, expand

logger = logging.getLogger("ghostcal.event_reminders")


@dataclass(frozen=True, slots=True)
class DueEvent:
    event_id: uuid.UUID
    organization_id: uuid.UUID
    owner_email: str
    owner_timezone: str
    start_at: datetime
    end_at: datetime
    timezone: str
    rrule: str | None
    exdates: tuple[str, ...]
    reminder_minutes: int


class EventReminderGateway:
    async def due_events(self) -> list[DueEvent]:
        """All reminder-enabled events that may still have an upcoming occurrence."""
        raise NotImplementedError

    async def claim(
        self, event_id: uuid.UUID, organization_id: uuid.UUID, occurrence_start: datetime
    ) -> bool:
        """Insert the (event, occurrence) marker. Return True only if THIS call inserted it."""
        raise NotImplementedError


def _recurring(ev: DueEvent) -> RecurringEvent:
    return RecurringEvent(
        id=str(ev.event_id),
        start_at=ev.start_at,
        end_at=ev.end_at,
        timezone=ev.timezone,
        rrule=ev.rrule,
        exdates=tuple(datetime.fromisoformat(x) for x in ev.exdates),
    )


async def dispatch_event_reminders(
    gateway: EventReminderGateway, mailer: EmailSender, *, now: datetime, scan_window: timedelta
) -> int:
    """Send reminders whose moment fell in ``(now - scan_window, now]``. Returns the count sent."""
    sent = 0
    for ev in await gateway.due_events():
        offset = timedelta(minutes=ev.reminder_minutes)
        # An occurrence's reminder fires at (start - offset). Look at occurrences whose reminder
        # moment could land in this scan window.
        window_start = now - scan_window
        window_end = now + offset + scan_window
        for occ in expand(_recurring(ev), window_start, window_end):
            reminder_at = occ.start - offset
            if not (window_start < reminder_at <= now):
                continue
            if not await gateway.claim(ev.event_id, ev.organization_id, occ.start):
                continue
            try:
                await send_event_reminder(
                    mailer,
                    to=ev.owner_email,
                    start_at=occ.start,
                    timezone=ev.owner_timezone,
                    minutes_before=ev.reminder_minutes,
                )
                sent += 1
            except Exception:
                logger.exception("failed to send event reminder for %s", ev.event_id)
    return sent
