"""SQL implementation of the scheduling repository port.

Bound to a session already scoped to one organization (RLS via ``org_session``) and that
organization's id. Maps ORM rows to the pure domain/engine types the use cases consume.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, insert, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.event_types import questions_from_json as _to_questions
from ghostcal.application.scheduling import (
    EventContext,
    HostRef,
    PublicEventType,
    SlotUnavailable,
)
from ghostcal.domain.availability import DateOverride, EventType, Schedule, WeeklyRule
from ghostcal.domain.calendar import RecurringEvent
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

        # Owner uses the event type's configured schedule; round-robin pool members each use their
        # own first schedule. The pool is the owner for solo event types.
        owner = await self._host_ref(event_row.owner_id, event_row.schedule_id)
        if event_row.kind in ("round_robin", "collective"):
            pool_ids = (
                (
                    await self._session.execute(
                        select(models.EventTypeHost.user_id)
                        .where(models.EventTypeHost.event_type_id == event_row.id)
                        .order_by(models.EventTypeHost.created_at)
                    )
                )
                .scalars()
                .all()
            )
            hosts = [await self._host_ref(uid) for uid in pool_ids] or [owner]
        else:
            hosts = [owner]
        primary = hosts[0]
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
            host_id=primary.host_id,
            host_name=primary.name,
            host_email=primary.email,
            host_timezone=primary.timezone,
            title=event_row.title,
            location_type=event_row.location_type,
            date_window_days=event_row.date_window_days,
            event=event,
            schedule=primary.schedule,
            kind=event_row.kind,
            hosts=tuple(hosts),
            questions=_to_questions(event_row.booking_questions),
            capacity=event_row.capacity,
            redirect_url=event_row.redirect_url,
        )

    async def _host_ref(self, user_id: uuid.UUID, schedule_id: uuid.UUID | None = None) -> HostRef:
        user = (
            await self._session.execute(
                select(models.User.name, models.User.email, models.User.timezone).where(
                    models.User.id == user_id
                )
            )
        ).one()
        schedule = await self._load_schedule(schedule_id, user_id)
        return HostRef(
            host_id=user_id,
            name=user.name,
            email=user.email,
            timezone=user.timezone,
            schedule=schedule,
        )

    async def get_event_type_id_by_slug(self, slug: str) -> uuid.UUID | None:
        return (
            await self._session.execute(
                select(models.EventType.id).where(
                    models.EventType.slug == slug,
                    models.EventType.active.is_(True),
                )
            )
        ).scalar_one_or_none()

    async def get_organization_name(self) -> str | None:
        return (
            await self._session.execute(
                select(models.Organization.name).where(models.Organization.id == self._org_id)
            )
        ).scalar_one_or_none()

    async def get_org_public_key(self) -> str | None:
        return (
            await self._session.execute(
                select(models.Organization.zk_public_key).where(
                    models.Organization.id == self._org_id
                )
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
                questions=_to_questions(r.booking_questions),
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
        # Confirmed bookings that occupy the host (group bookings don't — they share a slot)...
        rows = (
            await self._session.execute(
                select(models.Booking.start_at, models.Booking.end_at).where(
                    models.Booking.host_id == host_id,
                    models.Booking.status == "confirmed",
                    models.Booking.blocks_host.is_(True),
                    models.Booking.start_at < end,
                    models.Booking.end_at > start,
                )
            )
        ).all()
        # ...plus busy time synced from the host's external (CalDAV) calendar.
        external = (
            await self._session.execute(
                select(models.ExternalBusy.start_at, models.ExternalBusy.end_at).where(
                    models.ExternalBusy.host_id == host_id,
                    models.ExternalBusy.start_at < end,
                    models.ExternalBusy.end_at > start,
                )
            )
        ).all()
        return [TimeRange(row.start_at, row.end_at) for row in (*rows, *external)]

    async def busy_events(
        self, host_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[RecurringEvent]:
        """The host's own events, unexpanded — the recurrence is expanded in the domain.

        Scoped by **calendar ownership**, not by who created the event: an event a colleague put on
        your calendar occupies you, and a calendar merely shared *with* you is someone else's time,
        not yours.

        A recurring event's master row usually starts long before the window it still occupies —
        a weekly stand-up created in March is what makes you busy in July — so recurring masters are
        fetched regardless of the window, and the domain decides which occurrences fall inside it.
        Only times are selected here: ``content`` is sealed, and the scheduler has no use for it.
        """
        own_calendars = select(models.Calendar.id).where(models.Calendar.owner_id == host_id)
        rows = (
            await self._session.execute(
                select(
                    models.CalendarEvent.id,
                    models.CalendarEvent.start_at,
                    models.CalendarEvent.end_at,
                    models.CalendarEvent.all_day,
                    models.CalendarEvent.timezone,
                    models.CalendarEvent.rrule,
                    models.CalendarEvent.exdates,
                ).where(
                    models.CalendarEvent.calendar_id.in_(own_calendars),
                    models.CalendarEvent.start_at < end,
                    or_(
                        models.CalendarEvent.rrule.is_not(None),
                        models.CalendarEvent.end_at > start,
                    ),
                )
            )
        ).all()
        return [
            RecurringEvent(
                id=str(r.id),
                start_at=r.start_at,
                end_at=r.end_at,
                timezone=r.timezone,
                all_day=r.all_day,
                rrule=r.rrule,
                exdates=tuple(datetime.fromisoformat(x) for x in (r.exdates or [])),
            )
            for r in rows
        ]

    async def busy_subscription_events(
        self, host_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[TimeRange]:
        """Cached events from the host's subscribed calendars — but only the blocking ones.

        `blocks_availability` is the whole point of the join: a subscription is informational
        until its owner says otherwise. Without that filter, subscribing to public holidays
        would close eleven days of the year and nothing would explain why.

        No recurrence expansion here, unlike `busy_events`: an ICS feed hands us concrete
        occurrences, already dated. `summary` is never selected — the scheduler needs to know
        that you are busy, never with what.
        """
        blocking = select(models.CalendarSubscription.id).where(
            models.CalendarSubscription.owner_id == host_id,
            models.CalendarSubscription.blocks_availability.is_(True),
        )
        rows = (
            await self._session.execute(
                select(
                    models.SubscriptionEvent.start_at,
                    models.SubscriptionEvent.end_at,
                ).where(
                    models.SubscriptionEvent.subscription_id.in_(blocking),
                    models.SubscriptionEvent.start_at < end,
                    models.SubscriptionEvent.end_at > start,
                )
            )
        ).all()
        return [TimeRange(r.start_at, r.end_at) for r in rows]

    async def host_loads(self, host_ids: tuple[uuid.UUID, ...]) -> dict[uuid.UUID, int]:
        if not host_ids:
            return {}
        rows = (
            await self._session.execute(
                select(models.Booking.host_id, func.count())
                .where(
                    models.Booking.host_id.in_(host_ids),
                    models.Booking.status == "confirmed",
                )
                .group_by(models.Booking.host_id)
            )
        ).all()
        loads = dict.fromkeys(host_ids, 0)
        for host_id, count in rows:
            loads[host_id] = count
        return loads

    async def slot_booking_counts(self, event_type_id: uuid.UUID) -> dict[datetime, int]:
        rows = (
            await self._session.execute(
                select(models.Booking.start_at, func.count())
                .where(
                    models.Booking.event_type_id == event_type_id,
                    models.Booking.status == "confirmed",
                )
                .group_by(models.Booking.start_at)
            )
        ).all()
        return dict(rows)  # type: ignore[arg-type]

    async def insert_booking(
        self,
        *,
        context: EventContext,
        host_id: uuid.UUID,
        start_at: datetime,
        end_at: datetime,
        invitee_name: str | None,
        invitee_email: str,
        invitee_timezone: str,
        guest_emails: tuple[str, ...] = (),
        invitee_private: str | None = None,
        blocks_host: bool = True,
        max_at_slot: int | None = None,
    ) -> uuid.UUID:
        # Serialize concurrent attempts on the same (host, slot) so the loser gets a clean
        # SlotUnavailable instead of racing on the constraint. The EXCLUDE constraint remains the
        # ultimate guarantee against overlapping confirmed bookings; for group events (which don't
        # block the host) the capacity check below, run under this lock, is the guard.
        lock_key = f"{host_id}:{start_at.isoformat()}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": lock_key},
        )
        if max_at_slot is not None:
            taken = (
                await self._session.execute(
                    select(func.count())
                    .select_from(models.Booking)
                    .where(
                        models.Booking.event_type_id == context.event_type_id,
                        models.Booking.start_at == start_at,
                        models.Booking.status == "confirmed",
                    )
                )
            ).scalar_one()
            if taken >= max_at_slot:
                raise SlotUnavailable(start_at.isoformat())
        try:
            result = await self._session.execute(
                insert(models.Booking)
                .values(
                    organization_id=self._org_id,
                    event_type_id=context.event_type_id,
                    host_id=host_id,
                    invitee_name=invitee_name,
                    invitee_email=invitee_email,
                    invitee_timezone=invitee_timezone,
                    start_at=start_at,
                    end_at=end_at,
                    status="confirmed",
                    guest_emails=list(guest_emails),
                    invitee_private=invitee_private,
                    blocks_host=blocks_host,
                )
                .returning(models.Booking.id)
            )
        except IntegrityError as exc:
            raise SlotUnavailable(start_at.isoformat()) from exc
        return result.scalar_one()

    async def insert_collective_booking(
        self,
        *,
        context: EventContext,
        host_ids: tuple[uuid.UUID, ...],
        start_at: datetime,
        end_at: datetime,
        invitee_name: str | None,
        invitee_email: str,
        invitee_timezone: str,
        guest_emails: tuple[str, ...] = (),
        invitee_private: str | None = None,
    ) -> uuid.UUID:
        group_id = uuid.uuid4()
        # Lock every host/slot (sorted, to avoid deadlocks between concurrent collective bookings).
        for host_id in sorted(host_ids, key=str):
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                {"k": f"{host_id}:{start_at.isoformat()}"},
            )
        primary_id: uuid.UUID | None = None
        try:
            for host_id in host_ids:
                booking_id = (
                    await self._session.execute(
                        insert(models.Booking)
                        .values(
                            organization_id=self._org_id,
                            event_type_id=context.event_type_id,
                            host_id=host_id,
                            invitee_name=invitee_name,
                            invitee_email=invitee_email,
                            invitee_timezone=invitee_timezone,
                            start_at=start_at,
                            end_at=end_at,
                            status="confirmed",
                            guest_emails=list(guest_emails),
                            invitee_private=invitee_private,
                            collective_group_id=group_id,
                        )
                        .returning(models.Booking.id)
                    )
                ).scalar_one()
                if primary_id is None:
                    primary_id = booking_id
        except IntegrityError as exc:
            raise SlotUnavailable(start_at.isoformat()) from exc
        assert primary_id is not None  # host_ids is non-empty for collective
        return primary_id

    async def set_external_event(
        self, booking_id: uuid.UUID, uid: str | None, url: str | None
    ) -> None:
        await self._session.execute(
            update(models.Booking)
            .where(models.Booking.id == booking_id)
            .values(external_event_uid=uid, external_event_url=url)
        )
