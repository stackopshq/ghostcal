"""SQL implementation of the calendar-event reminder gateway (non-tenant; SECURITY DEFINER fns)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.event_reminders import DueEvent, EventReminderGateway

_DUE = text(
    "SELECT event_id, organization_id, owner_email, owner_timezone, start_at, end_at, "
    "timezone, rrule, exdates, reminder_minutes FROM reminder_calendar_events()"
)


class SqlEventReminderGateway(EventReminderGateway):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def due_events(self) -> list[DueEvent]:
        rows = (await self._session.execute(_DUE)).all()
        return [
            DueEvent(
                event_id=r.event_id,
                organization_id=r.organization_id,
                owner_email=r.owner_email,
                owner_timezone=r.owner_timezone,
                start_at=r.start_at,
                end_at=r.end_at,
                timezone=r.timezone,
                rrule=r.rrule,
                exdates=tuple(str(x) for x in r.exdates),
                reminder_minutes=r.reminder_minutes,
            )
            for r in rows
        ]

    async def claim(
        self, event_id: uuid.UUID, organization_id: uuid.UUID, occurrence_start: datetime
    ) -> bool:
        return bool(
            (
                await self._session.execute(
                    text("SELECT claim_calendar_event_reminder(:e, :o, :s) AS claimed"),
                    {"e": str(event_id), "o": str(organization_id), "s": occurrence_start},
                )
            ).scalar_one()
        )
