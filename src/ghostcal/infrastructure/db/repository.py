"""SQL implementation of the scheduling repository port.

Bound to a session already scoped to one organization (RLS via ``org_session``) and that
organization's id. Maps ORM rows to the pure domain/engine types the use cases consume.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.scheduling import EventContext, PublicEventType, SlotUnavailable
from ghostcal.domain.availability import DateOverride, EventType, Schedule, WeeklyRule
from ghostcal.domain.time import TimeRange
from ghostcal.infrastructure.db import models


class SqlSchedulingRepository:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def get_event_context(self, event_type_id: uuid.UUID) -> EventContext | None:
        event_row = (
            await self._session.execute(
                select(models.EventType).where(
                    models.EventType.id == event_type_id,
                    models.EventType.active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if event_row is None:
            return None

        host = (
            await self._session.execute(
                select(models.User.name, models.User.email, models.User.timezone).where(
                    models.User.id == event_row.owner_id
                )
            )
        ).one()
        schedule = await self._load_schedule(event_row.schedule_id, event_row.owner_id)
        event = EventType(
            duration=timedelta(minutes=event_row.duration_min),
            slot_interval=timedelta(minutes=event_row.slot_interval_min),
            buffer_before=timedelta(minutes=event_row.buffer_before_min),
            buffer_after=timedelta(minutes=event_row.buffer_after_min),
            min_notice=timedelta(minutes=event_row.min_notice_min),
            max_per_day=event_row.max_per_day,
        )
        return EventContext(
            event_type_id=event_row.id,
            host_id=event_row.owner_id,
            host_name=host.name,
            host_email=host.email,
            host_timezone=host.timezone,
            title=event_row.title,
            location_type=event_row.location_type,
            date_window_days=event_row.date_window_days,
            event=event,
            schedule=schedule,
        )

    async def get_organization_name(self) -> str | None:
        return (
            await self._session.execute(
                select(models.Organization.name).where(models.Organization.id == self._org_id)
            )
        ).scalar_one_or_none()

    async def list_active_event_types(self) -> list[PublicEventType]:
        rows = (
            (
                await self._session.execute(
                    select(models.EventType)
                    .where(models.EventType.active.is_(True))
                    .order_by(models.EventType.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [
            PublicEventType(
                id=r.id,
                slug=r.slug,
                title=r.title,
                description=r.description,
                duration_min=r.duration_min,
                location_type=r.location_type,
            )
            for r in rows
        ]

    async def _load_schedule(self, schedule_id: uuid.UUID | None, owner_id: uuid.UUID) -> Schedule:
        if schedule_id is not None:
            stmt = select(models.AvailabilitySchedule).where(
                models.AvailabilitySchedule.id == schedule_id
            )
        else:
            # Fallback: the owner's first schedule (single-schedule setups).
            stmt = (
                select(models.AvailabilitySchedule)
                .where(models.AvailabilitySchedule.owner_id == owner_id)
                .order_by(models.AvailabilitySchedule.created_at)
                .limit(1)
            )
        schedule_row = (await self._session.execute(stmt)).scalar_one_or_none()
        # No schedule configured yet → no availability (engine yields no slots).
        if schedule_row is None:
            return Schedule(timezone="UTC", rules=())

        rule_rows = (
            (
                await self._session.execute(
                    select(models.AvailabilityRule).where(
                        models.AvailabilityRule.schedule_id == schedule_row.id
                    )
                )
            )
            .scalars()
            .all()
        )
        override_rows = (
            (
                await self._session.execute(
                    select(models.AvailabilityOverride).where(
                        models.AvailabilityOverride.schedule_id == schedule_row.id
                    )
                )
            )
            .scalars()
            .all()
        )

        return Schedule(
            timezone=schedule_row.timezone,
            rules=tuple(
                WeeklyRule(weekday=r.weekday, start=r.start_time, end=r.end_time) for r in rule_rows
            ),
            overrides=tuple(
                DateOverride(
                    day=o.date,
                    is_available=o.is_available,
                    start=o.start_time,
                    end=o.end_time,
                )
                for o in override_rows
            ),
        )

    async def get_busy(self, host_id: uuid.UUID, start: datetime, end: datetime) -> list[TimeRange]:
        rows = (
            await self._session.execute(
                select(models.Booking.start_at, models.Booking.end_at).where(
                    models.Booking.host_id == host_id,
                    models.Booking.status == "confirmed",
                    models.Booking.start_at < end,
                    models.Booking.end_at > start,
                )
            )
        ).all()
        return [TimeRange(row.start_at, row.end_at) for row in rows]

    async def insert_booking(
        self,
        *,
        context: EventContext,
        start_at: datetime,
        end_at: datetime,
        invitee_name: str,
        invitee_email: str,
        invitee_timezone: str,
    ) -> uuid.UUID:
        # Serialize concurrent attempts on the same (host, slot) so the loser gets a clean
        # SlotUnavailable instead of racing on the constraint. The EXCLUDE constraint remains the
        # ultimate guarantee against overlapping confirmed bookings.
        lock_key = f"{context.host_id}:{start_at.isoformat()}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": lock_key},
        )
        try:
            result = await self._session.execute(
                insert(models.Booking)
                .values(
                    organization_id=self._org_id,
                    event_type_id=context.event_type_id,
                    host_id=context.host_id,
                    invitee_name=invitee_name,
                    invitee_email=invitee_email,
                    invitee_timezone=invitee_timezone,
                    start_at=start_at,
                    end_at=end_at,
                    status="confirmed",
                )
                .returning(models.Booking.id)
            )
        except IntegrityError as exc:
            raise SlotUnavailable(start_at.isoformat()) from exc
        return result.scalar_one()
