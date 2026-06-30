"""SQL implementation of the calendar repository (org-scoped session, RLS applies)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.calendar import (
    BusyBlock,
    CalendarRecord,
    CalendarRepository,
    EventInput,
    EventRecord,
)
from ghostcal.infrastructure.db import models


class SqlCalendarRepository(CalendarRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_calendars(self, owner_id: uuid.UUID) -> list[CalendarRecord]:
        rows = (
            (
                await self._session.execute(
                    select(models.Calendar)
                    .where(models.Calendar.owner_id == owner_id)
                    .order_by(models.Calendar.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [_calendar(r) for r in rows]

    async def ensure_default_calendar(self, owner_id: uuid.UUID) -> CalendarRecord:
        existing = (
            await self._session.execute(
                select(models.Calendar)
                .where(
                    models.Calendar.owner_id == owner_id,
                    models.Calendar.is_default.is_(True),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _calendar(existing)
        row = (
            await self._session.execute(
                insert(models.Calendar)
                .values(
                    organization_id=self._org_id,
                    owner_id=owner_id,
                    name="My calendar",
                    color="#00f0ff",
                    is_default=True,
                )
                .returning(models.Calendar)
            )
        ).scalar_one()
        return _calendar(row)

    async def create_calendar(
        self, owner_id: uuid.UUID, *, name: str, color: str
    ) -> CalendarRecord:
        row = (
            await self._session.execute(
                insert(models.Calendar)
                .values(organization_id=self._org_id, owner_id=owner_id, name=name, color=color)
                .returning(models.Calendar)
            )
        ).scalar_one()
        return _calendar(row)

    async def get_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> EventRecord | None:
        row = (
            await self._session.execute(
                select(models.CalendarEvent).where(
                    models.CalendarEvent.id == event_id,
                    models.CalendarEvent.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        return _event(row) if row is not None else None

    async def create_event(self, owner_id: uuid.UUID, data: EventInput) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.CalendarEvent)
                .values(organization_id=self._org_id, owner_id=owner_id, **_event_values(data))
                .returning(models.CalendarEvent.id)
            )
        ).scalar_one()

    async def update_event(
        self, owner_id: uuid.UUID, event_id: uuid.UUID, data: EventInput
    ) -> bool:
        result = await self._session.execute(
            update(models.CalendarEvent)
            .where(
                models.CalendarEvent.id == event_id,
                models.CalendarEvent.owner_id == owner_id,
            )
            .values(**_event_values(data))
            .returning(models.CalendarEvent.id)
        )
        return result.first() is not None

    async def delete_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.CalendarEvent)
            .where(
                models.CalendarEvent.id == event_id,
                models.CalendarEvent.owner_id == owner_id,
            )
            .returning(models.CalendarEvent.id)
        )
        return result.first() is not None

    async def events_overlapping(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[EventRecord]:
        rows = (
            (
                await self._session.execute(
                    select(models.CalendarEvent).where(
                        models.CalendarEvent.owner_id == owner_id,
                        models.CalendarEvent.start_at < end,
                        or_(
                            models.CalendarEvent.rrule.is_not(None),
                            models.CalendarEvent.end_at > start,
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_event(r) for r in rows]

    async def bookings_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[BusyBlock]:
        rows = (
            await self._session.execute(
                select(models.Booking.start_at, models.Booking.end_at, models.EventType.title)
                .join(models.EventType, models.Booking.event_type_id == models.EventType.id)
                .where(
                    models.Booking.host_id == owner_id,
                    models.Booking.status == "confirmed",
                    models.Booking.start_at < end,
                    models.Booking.end_at > start,
                )
            )
        ).all()
        return [BusyBlock(start_at=r.start_at, end_at=r.end_at, title=r.title) for r in rows]

    async def external_busy_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[BusyBlock]:
        rows = (
            await self._session.execute(
                select(models.ExternalBusy.start_at, models.ExternalBusy.end_at).where(
                    models.ExternalBusy.host_id == owner_id,
                    models.ExternalBusy.start_at < end,
                    models.ExternalBusy.end_at > start,
                )
            )
        ).all()
        return [BusyBlock(start_at=r.start_at, end_at=r.end_at, title=None) for r in rows]


def _calendar(row: models.Calendar) -> CalendarRecord:
    return CalendarRecord(id=row.id, name=row.name, color=row.color, is_default=row.is_default)


def _event(row: models.CalendarEvent) -> EventRecord:
    return EventRecord(
        id=row.id,
        calendar_id=row.calendar_id,
        start_at=row.start_at,
        end_at=row.end_at,
        timezone=row.timezone,
        all_day=row.all_day,
        rrule=row.rrule,
        exdates=tuple(row.exdates),
        content=row.content,
    )


def _event_values(data: EventInput) -> dict[str, object]:
    return {
        "calendar_id": data.calendar_id,
        "start_at": data.start_at,
        "end_at": data.end_at,
        "timezone": data.timezone,
        "all_day": data.all_day,
        "rrule": data.rrule,
        "exdates": list(data.exdates),
        "status": "confirmed",
        "content": data.content,
    }
