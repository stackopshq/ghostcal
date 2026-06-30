"""Reminder dispatch use case: send due booking reminders, exactly once per (booking, offset).

The gateway lists reminders that are due now and atomically claims each one (insert-or-skip), so
concurrent worker runs never double-send. Sends are best-effort, like all booking emails.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ghostcal.application.notifications import send_booking_reminder
from ghostcal.application.ports.email import EmailSender

logger = logging.getLogger("ghostcal.reminders")


@dataclass(frozen=True, slots=True)
class DueReminder:
    booking_id: uuid.UUID
    organization_id: uuid.UUID
    minutes_before: int
    # No invitee_name: it is zero-knowledge. Reminders are addressed to the invitee, not by name.
    invitee_email: str
    invitee_timezone: str
    event_title: str
    host_name: str
    host_email: str
    host_timezone: str
    location_type: str
    start_at: datetime
    end_at: datetime


class ReminderGateway:
    async def due(self, offsets: tuple[int, ...]) -> list[DueReminder]:
        raise NotImplementedError

    async def claim(
        self, booking_id: uuid.UUID, organization_id: uuid.UUID, minutes_before: int
    ) -> bool:
        """Insert the (booking, offset) marker. Return True only if THIS call inserted it."""
        raise NotImplementedError


async def dispatch_reminders(
    gateway: ReminderGateway,
    mailer: EmailSender,
    *,
    offsets: tuple[int, ...],
    manage_url: Callable[[DueReminder], str] | None = None,
) -> int:
    """Send every due reminder once. ``manage_url`` is an optional callable(DueReminder) -> str."""
    reminders = await gateway.due(offsets)
    sent = 0
    for reminder in reminders:
        if not await gateway.claim(
            reminder.booking_id, reminder.organization_id, reminder.minutes_before
        ):
            continue
        link = manage_url(reminder) if manage_url is not None else None
        try:
            await send_booking_reminder(
                mailer,
                invitee_email=reminder.invitee_email,
                invitee_timezone=reminder.invitee_timezone,
                event_title=reminder.event_title,
                host_name=reminder.host_name,
                location_type=reminder.location_type,
                start_at=reminder.start_at,
                minutes_before=reminder.minutes_before,
                manage_url=link,
            )
            sent += 1
        except Exception:
            logger.exception("failed to send reminder for booking %s", reminder.booking_id)
    return sent
