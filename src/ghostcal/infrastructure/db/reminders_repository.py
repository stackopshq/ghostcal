"""SQL implementation of the reminder gateway (non-tenant; via SECURITY DEFINER functions)."""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.reminders import DueReminder, ReminderGateway

_DUE = text(
    "SELECT booking_id, organization_id, minutes_before, invitee_name, invitee_email, "
    "invitee_timezone, event_title, host_name, host_email, host_timezone, location_type, "
    "start_at, end_at FROM due_booking_reminders(:offsets)"
).bindparams(bindparam("offsets", type_=ARRAY(Integer)))


class SqlReminderGateway(ReminderGateway):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def due(self, offsets: tuple[int, ...]) -> list[DueReminder]:
        rows = (await self._session.execute(_DUE, {"offsets": list(offsets)})).all()
        return [
            DueReminder(
                booking_id=r.booking_id,
                organization_id=r.organization_id,
                minutes_before=r.minutes_before,
                invitee_name=r.invitee_name,
                invitee_email=r.invitee_email,
                invitee_timezone=r.invitee_timezone,
                event_title=r.event_title,
                host_name=r.host_name,
                host_email=r.host_email,
                host_timezone=r.host_timezone,
                location_type=r.location_type,
                start_at=r.start_at,
                end_at=r.end_at,
            )
            for r in rows
        ]

    async def claim(
        self, booking_id: uuid.UUID, organization_id: uuid.UUID, minutes_before: int
    ) -> bool:
        return bool(
            (
                await self._session.execute(
                    text("SELECT claim_booking_reminder(:b, :o, :m) AS claimed"),
                    {"b": str(booking_id), "o": str(organization_id), "m": minutes_before},
                )
            ).scalar_one()
        )
