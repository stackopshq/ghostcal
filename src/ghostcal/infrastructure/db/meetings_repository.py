"""SQL implementation of the meetings (bookings) read repository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.meetings import BookingSummary, MeetingsRepository
from ghostcal.infrastructure.db import models


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
        return [
            BookingSummary(
                id=booking.id,
                event_title=title,
                invitee_name=booking.invitee_name,
                invitee_email=booking.invitee_email,
                invitee_timezone=booking.invitee_timezone,
                start_at=booking.start_at,
                end_at=booking.end_at,
                status=booking.status,
                location=booking.location,
                meeting_url=booking.meeting_url,
            )
            for booking, title in rows
        ]

    async def cancel(self, booking_id: uuid.UUID, host_id: uuid.UUID) -> BookingSummary | None:
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
        if row is None:
            return None
        booking, title = row
        booking.status = "cancelled"  # flushed on commit; frees the slot
        return BookingSummary(
            id=booking.id,
            event_title=title,
            invitee_name=booking.invitee_name,
            invitee_email=booking.invitee_email,
            invitee_timezone=booking.invitee_timezone,
            start_at=booking.start_at,
            end_at=booking.end_at,
            status="cancelled",
            location=booking.location,
            meeting_url=booking.meeting_url,
        )
