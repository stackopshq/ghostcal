"""SQL implementation of the invitee management repository (RLS-scoped to the booking's org)."""

from __future__ import annotations

import uuid
from dataclasses import replace

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.manage import BookingDetail, ManageRepository
from ghostcal.infrastructure.db import models


async def cancel_booking_or_group(session: AsyncSession, booking: models.Booking) -> None:
    """Cancel the booking; for a collective meeting, cancel all of its linked host rows."""
    if booking.collective_group_id is not None:
        await session.execute(
            update(models.Booking)
            .where(
                models.Booking.collective_group_id == booking.collective_group_id,
                models.Booking.status == "confirmed",
            )
            .values(status="cancelled")
        )
    else:
        booking.status = "cancelled"  # flushed on commit; frees the slot


class SqlBookingManageRepository(ManageRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def get_detail(self, booking_id: uuid.UUID) -> BookingDetail | None:
        row = (
            await self._session.execute(
                select(
                    models.Booking,
                    models.EventType.title,
                    models.EventType.slug,
                    models.EventType.location_type,
                    models.EventType.duration_min,
                    models.Organization.slug,
                    models.User.name,
                    models.User.email,
                    models.User.timezone,
                )
                .join(models.EventType, models.Booking.event_type_id == models.EventType.id)
                .join(
                    models.Organization,
                    models.Booking.organization_id == models.Organization.id,
                )
                .join(models.User, models.Booking.host_id == models.User.id)
                .where(models.Booking.id == booking_id)
            )
        ).first()
        if row is None:
            return None
        booking, title, event_slug, location_type, duration_min, org_slug, name, email, tz = row
        return BookingDetail(
            booking_id=booking.id,
            event_type_id=booking.event_type_id,
            host_id=booking.host_id,
            external_event_uid=booking.external_event_uid,
            event_title=title,
            host_name=name,
            host_email=email,
            host_timezone=tz,
            organization_slug=org_slug,
            event_slug=event_slug,
            invitee_name=booking.invitee_name,
            invitee_email=booking.invitee_email,
            invitee_timezone=booking.invitee_timezone,
            duration_min=duration_min,
            location_type=location_type,
            start_at=booking.start_at,
            end_at=booking.end_at,
            status=booking.status,
        )

    async def cancel(self, booking_id: uuid.UUID) -> BookingDetail | None:
        detail = await self.get_detail(booking_id)
        if detail is None or detail.status != "confirmed":
            return None
        booking = await self._session.get(models.Booking, booking_id)
        assert booking is not None
        await cancel_booking_or_group(self._session, booking)
        return replace(detail, status="cancelled")
