"""Scheduling use cases: read availability and create bookings.

Framework-free orchestration. Persistence is reached through the ``SchedulingRepository`` port
(implemented in the infrastructure layer); the availability math is the pure domain engine; the
current time enters via the ``Clock`` port. This keeps the use cases unit-testable with a fake
repository and a fixed clock.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from ghostcal.application.ports.clock import Clock
from ghostcal.domain.availability import EventType, Schedule, compute_slots
from ghostcal.domain.time import TimeRange


class SchedulingError(Exception):
    """Base class for scheduling use-case errors."""


class EventTypeNotFound(SchedulingError):
    pass


class SlotUnavailable(SchedulingError):
    """The requested start time is not (or no longer) a bookable slot."""


@dataclass(frozen=True, slots=True)
class EventContext:
    """Everything the engine needs about an event type, plus who hosts it."""

    event_type_id: uuid.UUID
    host_id: uuid.UUID
    title: str
    location_type: str
    date_window_days: int
    event: EventType
    schedule: Schedule


@dataclass(frozen=True, slots=True)
class BookingRequest:
    event_type_id: uuid.UUID
    start_at: datetime
    invitee_name: str
    invitee_email: str
    invitee_timezone: str


@dataclass(frozen=True, slots=True)
class BookingConfirmation:
    booking_id: uuid.UUID
    start_at: datetime
    end_at: datetime


class SchedulingRepository(Protocol):
    async def get_event_context(self, event_type_id: uuid.UUID) -> EventContext | None: ...

    async def get_busy(
        self, host_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[TimeRange]: ...

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
        """Insert a confirmed booking. Raise ``SlotUnavailable`` on overlap (race)."""
        ...


async def get_availability(
    repo: SchedulingRepository,
    clock: Clock,
    *,
    event_type_id: uuid.UUID,
    from_date: date,
    to_date: date,
) -> list[TimeRange]:
    context = await repo.get_event_context(event_type_id)
    if context is None:
        raise EventTypeNotFound(str(event_type_id))

    now = clock.now()
    capped_to = _cap_window(from_date, to_date, context.date_window_days)
    busy = await repo.get_busy(context.host_id, *_busy_bounds(from_date, capped_to))
    return compute_slots(
        schedule=context.schedule,
        event=context.event,
        busy=busy,
        now=now,
        from_date=from_date,
        to_date=capped_to,
    )


async def create_booking(
    repo: SchedulingRepository,
    clock: Clock,
    request: BookingRequest,
) -> BookingConfirmation:
    if request.start_at.tzinfo is None:
        raise SlotUnavailable("start_at must be timezone-aware")

    context = await repo.get_event_context(request.event_type_id)
    if context is None:
        raise EventTypeNotFound(str(request.event_type_id))

    now = clock.now()
    # Re-validate against freshly computed availability for that local day: the slot must still
    # be offered. The DB exclusion constraint is the final guard against races.
    day = request.start_at.astimezone(ZoneInfo(context.schedule.timezone)).date()
    busy = await repo.get_busy(context.host_id, *_busy_bounds(day, day))
    slots = compute_slots(
        schedule=context.schedule,
        event=context.event,
        busy=busy,
        now=now,
        from_date=day,
        to_date=day,
    )
    if not any(slot.start == request.start_at for slot in slots):
        raise SlotUnavailable(request.start_at.isoformat())

    end_at = request.start_at + context.event.duration
    booking_id = await repo.insert_booking(
        context=context,
        start_at=request.start_at,
        end_at=end_at,
        invitee_name=request.invitee_name,
        invitee_email=request.invitee_email,
        invitee_timezone=request.invitee_timezone,
    )
    return BookingConfirmation(booking_id=booking_id, start_at=request.start_at, end_at=end_at)


def _cap_window(from_date: date, to_date: date, window_days: int) -> date:
    """Never offer slots beyond the event type's booking window."""
    horizon = from_date + timedelta(days=window_days)
    return min(to_date, horizon)


def _busy_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    """UTC bounds covering the date range with a one-day margin on each side.

    Local-time windows of a day can land on the previous/next UTC day, so we widen the busy
    lookup to avoid missing an overlapping booking near a date boundary.
    """
    start = datetime.combine(from_date - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(to_date + timedelta(days=2), datetime.min.time(), tzinfo=UTC)
    return start, end
