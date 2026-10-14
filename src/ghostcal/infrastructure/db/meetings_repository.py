"""SQL implementation of the meetings (bookings) read repository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.meetings import BookingSummary, MeetingsRepository
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.manage_repository import cancel_booking_or_group


def _summary(booking: models.Booking, title: str, *, status: str | None = None) -> BookingSummary:
    return BookingSummary(
        id=booking.id,
        event_title=title,
        invitee_name=booking.invitee_name,
        invitee_email=booking.invitee_email,
        invitee_timezone=booking.invitee_timezone,
        start_at=booking.start_at,
        end_at=booking.end_at,
        status=status or booking.status,
        location=booking.location,
        meeting_url=booking.meeting_url,
        external_event_uid=booking.external_event_uid,
        invitee_private=booking.invitee_private,
        organization_id=booking.organization_id,
        guest_emails=list(booking.guest_emails or []),
    )


class SqlMeetingsRepository(MeetingsRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_for_host(
        self, host_id: uuid.UUID, *, upcoming: bool, now: datetime
    ) -> list[BookingSummary]:
        stmt = (
            select(models.Booking, models.EventType.title)
            .join(models.EventType, models.Booking.event_type_id == models.EventType.id)
            .where(
                models.Booking.host_id == host_id,
                models.Booking.status == "confirmed",
            )
        )
        if upcoming:
            stmt = stmt.where(models.Booking.start_at >= now).order_by(models.Booking.start_at)
        else:
            stmt = stmt.where(models.Booking.start_at < now).order_by(
                models.Booking.start_at.desc()
            )

        rows = (await self._session.execute(stmt)).all()
        return [_summary(booking, title) for booking, title in rows]

    async def _own_confirmed(
        self, booking_id: uuid.UUID, host_id: uuid.UUID
    ) -> tuple[models.Booking, str] | None:
        row = (
            await self._session.execute(
                select(models.Booking, models.EventType.title)
                .join(models.EventType, models.Booking.event_type_id == models.EventType.id)
                .where(
                    models.Booking.id == booking_id,
                    models.Booking.host_id == host_id,
                    models.Booking.status == "confirmed",
                )
            )
        ).first()
        return None if row is None else (row[0], row[1])

    async def cancel(self, booking_id: uuid.UUID, host_id: uuid.UUID) -> BookingSummary | None:
        found = await self._own_confirmed(booking_id, host_id)
        if found is None:
            return None
        booking, title = found
        await cancel_booking_or_group(self._session, booking)
        return _summary(booking, title, status="cancelled")

    async def set_meeting_url(
        self, booking_id: uuid.UUID, host_id: uuid.UUID, meeting_url: str
    ) -> BookingSummary | None:
        found = await self._own_confirmed(booking_id, host_id)
        if found is None:
            return None
        booking, title = found
        rows = [booking]
        if booking.collective_group_id is not None:
            # One meeting, one link: every co-host row of a collective booking carries it.
            rows = list(
                (
                    await self._session.scalars(
                        select(models.Booking).where(
                            models.Booking.collective_group_id == booking.collective_group_id,
                            models.Booking.status == "confirmed",
                        )
                    )
                ).all()
            )
        for row in rows:
            row.meeting_url = meeting_url
        await self._session.flush()
        return _summary(booking, title)
