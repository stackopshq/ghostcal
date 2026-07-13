"""SQL implementation of the calendar repository (org-scoped session, RLS applies)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.calendar import (
    BusyBlock,
    CalendarRecord,
    CalendarRepository,
    EventInput,
    EventRecord,
    ShareRecord,
    SubEvent,
)
from ghostcal.infrastructure.db import models


class SqlCalendarRepository(CalendarRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_calendars(self, owner_id: uuid.UUID) -> list[CalendarRecord]:
        owned = (
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
        shared = (
            await self._session.execute(
                select(models.Calendar, models.User.name)
                .join(models.CalendarShare, models.CalendarShare.calendar_id == models.Calendar.id)
                .join(models.User, models.User.id == models.Calendar.owner_id)
                .where(models.CalendarShare.shared_with_user_id == owner_id)
                .order_by(models.Calendar.created_at)
            )
        ).all()
        return [_calendar(c) for c in owned] + [
            _calendar(c, is_shared=True, owner_name=name) for c, name in shared
        ]

    async def share_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        if not await self._owns(owner_id, calendar_id):
            return False
        await self._session.execute(
            pg_insert(models.CalendarShare)
            .values(
                organization_id=self._org_id,
                calendar_id=calendar_id,
                shared_with_user_id=user_id,
            )
            .on_conflict_do_nothing(index_elements=["calendar_id", "shared_with_user_id"])
        )
        return True

    async def unshare_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        if not await self._owns(owner_id, calendar_id):
            return False
        await self._session.execute(
            delete(models.CalendarShare).where(
                models.CalendarShare.calendar_id == calendar_id,
                models.CalendarShare.shared_with_user_id == user_id,
            )
        )
        return True

    async def list_shares(self, owner_id: uuid.UUID, calendar_id: uuid.UUID) -> list[ShareRecord]:
        if not await self._owns(owner_id, calendar_id):
            return []
        rows = (
            await self._session.execute(
                select(models.User.id, models.User.name)
                .join(
                    models.CalendarShare, models.CalendarShare.shared_with_user_id == models.User.id
                )
                .where(models.CalendarShare.calendar_id == calendar_id)
                .order_by(models.User.name)
            )
        ).all()
        return [ShareRecord(user_id=r.id, name=r.name) for r in rows]

    async def _owns(self, owner_id: uuid.UUID, calendar_id: uuid.UUID) -> bool:
        return (
            await self._session.execute(
                select(models.Calendar.id).where(
                    models.Calendar.id == calendar_id, models.Calendar.owner_id == owner_id
                )
            )
        ).scalar_one_or_none() is not None

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
        # The viewer's own events plus events from calendars shared with them (read-only).
        shared_calendars = (
            select(models.CalendarShare.calendar_id)
            .where(models.CalendarShare.shared_with_user_id == owner_id)
            .scalar_subquery()
        )
        rows = (
            (
                await self._session.execute(
                    select(models.CalendarEvent).where(
                        models.CalendarEvent.start_at < end,
                        or_(
                            models.CalendarEvent.rrule.is_not(None),
                            models.CalendarEvent.end_at > start,
                        ),
                        or_(
                            models.CalendarEvent.owner_id == owner_id,
                            models.CalendarEvent.calendar_id.in_(shared_calendars),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_event(r, read_only=r.owner_id != owner_id) for r in rows]

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
                select(
                    models.ExternalBusy.start_at,
                    models.ExternalBusy.end_at,
                    models.ExternalBusy.summary,
                    models.ExternalBusy.connection_id,
                ).where(
                    models.ExternalBusy.host_id == owner_id,
                    models.ExternalBusy.start_at < end,
                    models.ExternalBusy.end_at > start,
                )
            )
        ).all()
        return [
            BusyBlock(
                start_at=r.start_at,
                end_at=r.end_at,
                title=r.summary,
                connection_id=r.connection_id,
            )
            for r in rows
        ]

    async def subscription_events_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[SubEvent]:
        rows = (
            await self._session.execute(
                select(
                    models.SubscriptionEvent.subscription_id,
                    models.SubscriptionEvent.start_at,
                    models.SubscriptionEvent.end_at,
                    models.SubscriptionEvent.all_day,
                    models.SubscriptionEvent.summary,
                ).where(
                    models.SubscriptionEvent.owner_id == owner_id,
                    models.SubscriptionEvent.start_at < end,
                    models.SubscriptionEvent.end_at > start,
                )
            )
        ).all()
        return [
            SubEvent(
                subscription_id=r.subscription_id,
                start_at=r.start_at,
                end_at=r.end_at,
                all_day=r.all_day,
                summary=r.summary,
            )
            for r in rows
        ]


def _calendar(
    row: models.Calendar, *, is_shared: bool = False, owner_name: str | None = None
) -> CalendarRecord:
    return CalendarRecord(
        id=row.id,
        name=row.name,
        color=row.color,
        is_default=row.is_default,
        is_shared=is_shared,
        owner_name=owner_name,
    )


def _event(row: models.CalendarEvent, *, read_only: bool = False) -> EventRecord:
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
        reminder_minutes=row.reminder_minutes,
        read_only=read_only,
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
        "reminder_minutes": data.reminder_minutes,
    }
