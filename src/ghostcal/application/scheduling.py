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

from ghostcal.application.event_types import BookingQuestion
from ghostcal.application.ports.clock import Clock
from ghostcal.domain.availability import EventType, Schedule, compute_slots
from ghostcal.domain.calendar import RecurringEvent, expand
from ghostcal.domain.time import TimeRange

MAX_GUESTS = 10


class SchedulingError(Exception):
    """Base class for scheduling use-case errors."""


class EventTypeNotFound(SchedulingError):
    pass


class SlotUnavailable(SchedulingError):
    """The requested start time is not (or no longer) a bookable slot."""


class OrganizationNotFound(SchedulingError):
    pass


class InvalidBookingInput(SchedulingError):
    """Required custom questions are unanswered, or guest input is invalid."""


@dataclass(frozen=True, slots=True)
class PublicEventType:
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    duration_min: int
    location_type: str
    questions: tuple[BookingQuestion, ...] = ()


@dataclass(frozen=True, slots=True)
class BookingPage:
    organization_name: str
    event_types: list[PublicEventType]


@dataclass(frozen=True, slots=True)
class HostRef:
    """One potential host of an event type, with their schedule."""

    host_id: uuid.UUID
    name: str
    email: str
    timezone: str
    schedule: Schedule


@dataclass(frozen=True, slots=True)
class EventContext:
    """Everything the engine needs about an event type, plus who can host it.

    ``hosts`` is the candidate pool: one entry for a solo event type (the owner), several for a
    round-robin one. The singular ``host_*``/``schedule`` fields mirror the primary host
    (``hosts[0]``) and keep the solo path simple.
    """

    event_type_id: uuid.UUID
    host_id: uuid.UUID
    host_name: str
    host_email: str
    host_timezone: str
    title: str
    location_type: str
    date_window_days: int
    event: EventType
    schedule: Schedule
    kind: str = "solo"
    hosts: tuple[HostRef, ...] = ()
    questions: tuple[BookingQuestion, ...] = ()
    capacity: int = 1
    redirect_url: str | None = None


@dataclass(frozen=True, slots=True)
class BookingRequest:
    event_type_id: uuid.UUID
    start_at: datetime
    # Zero-knowledge: the booking page sends None — the real name is inside ``invitee_private``.
    invitee_name: str | None
    invitee_email: str
    invitee_timezone: str
    guest_emails: tuple[str, ...] = ()
    # Sealed-box blob (base64) with the invitee's name + answers + notes, encrypted client-side to
    # the org public key. Opaque to the server (zero-knowledge); None if nothing was submitted.
    invitee_private: str | None = None


@dataclass(frozen=True, slots=True)
class BookingConfirmation:
    booking_id: uuid.UUID
    host_id: uuid.UUID
    event_title: str
    host_name: str
    host_email: str
    host_timezone: str
    # None for booking-page bookings (zero-knowledge); the server never learns the invitee's name.
    invitee_name: str | None
    invitee_email: str
    invitee_timezone: str
    location_type: str
    start_at: datetime
    end_at: datetime
    guest_emails: tuple[str, ...] = ()
    # Other required hosts on a collective booking (each also gets the host notification).
    additional_host_emails: tuple[str, ...] = ()


class SchedulingRepository(Protocol):
    async def get_event_context(self, event_type_id: uuid.UUID) -> EventContext | None: ...

    async def get_event_type_id_by_slug(self, slug: str) -> uuid.UUID | None: ...

    async def get_organization_name(self) -> str | None: ...

    async def get_org_public_key(self) -> str | None:
        """The org's zero-knowledge public key (booking pages seal answers to it)."""
        ...

    async def list_active_event_types(self) -> list[PublicEventType]: ...

    async def get_busy(
        self, host_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[TimeRange]: ...

    async def busy_events(
        self, host_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[RecurringEvent]:
        """The host's own calendar events, unexpanded. Times only — the content stays sealed."""
        ...

    async def host_loads(self, host_ids: tuple[uuid.UUID, ...]) -> dict[uuid.UUID, int]:
        """Confirmed-booking counts per host (for round-robin load balancing)."""
        ...

    async def slot_booking_counts(self, event_type_id: uuid.UUID) -> dict[datetime, int]:
        """Confirmed-booking counts per start time for an event type (group capacity)."""
        ...

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
        """Insert a confirmed booking. Raise ``SlotUnavailable`` on overlap (race), or when
        ``max_at_slot`` is set and the slot already holds that many bookings (group capacity)."""
        ...

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
        """Insert one confirmed booking per required host, linked by a collective group id.

        Returns the primary (first host's) booking id. Raise ``SlotUnavailable`` if any host
        overlaps an existing booking (the whole insert is rolled back)."""
        ...

    async def set_external_event(
        self, booking_id: uuid.UUID, uid: str | None, url: str | None
    ) -> None: ...


async def get_event_type(repo: SchedulingRepository, *, event_type_id: uuid.UUID) -> EventContext:
    context = await repo.get_event_context(event_type_id)
    if context is None:
        raise EventTypeNotFound(str(event_type_id))
    return context


async def get_booking_page(repo: SchedulingRepository) -> BookingPage:
    name = await repo.get_organization_name()
    if name is None:
        raise OrganizationNotFound("organization not found")
    return BookingPage(organization_name=name, event_types=await repo.list_active_event_types())


async def busy_for(
    repo: SchedulingRepository, host_id: uuid.UUID, start: datetime, end: datetime
) -> list[TimeRange]:
    """What "busy" means. One definition, and this is it.

    Three sources, and the third is the one that was missing:

    - confirmed bookings that occupy the host (a group booking does not: invitees share a slot);
    - busy time synced from the host's external (CalDAV) calendar;
    - **the host's own GhostCal events.**

    Without the third, "Dentist, 14:00" in your own calendar did not stop a stranger booking you at
    14:00 through your booking page — the engine simply could not see it. The agenda view has always
    shown all three together; the scheduler only ever looked at two, and so the product held two
    contradictory answers to "am I free?".

    Times only. The events' contents stay sealed and are never opened here — the scheduler does not
    need to know *what* you are doing to know that you are doing something.
    """
    busy = await repo.get_busy(host_id, start, end)
    for event in await repo.busy_events(host_id, start, end):
        busy.extend(TimeRange(occ.start, occ.end) for occ in expand(event, start, end))
    return busy


async def _host_day_slots(
    repo: SchedulingRepository,
    host: HostRef,
    event: EventType,
    now: datetime,
    from_date: date,
    to_date: date,
) -> list[TimeRange]:
    busy = await busy_for(repo, host.host_id, *_busy_bounds(from_date, to_date))
    return compute_slots(
        schedule=host.schedule,
        event=event,
        busy=busy,
        now=now,
        from_date=from_date,
        to_date=to_date,
    )


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
    # Count how many hosts offer each slot start. Solo/round-robin offer a slot if ANY host is free
    # (union); collective requires EVERY host free (intersection).
    by_start: dict[datetime, TimeRange] = {}
    counts: dict[datetime, int] = {}
    for host in context.hosts:
        for slot in await _host_day_slots(repo, host, context.event, now, from_date, capped_to):
            by_start.setdefault(slot.start, slot)
            counts[slot.start] = counts.get(slot.start, 0) + 1
    if context.kind == "collective":
        needed = len(context.hosts)
        offered = [slot for start, slot in by_start.items() if counts[start] == needed]
    elif context.kind == "group":
        # The host's free slots, minus those already at capacity.
        booked = await repo.slot_booking_counts(event_type_id)
        offered = [
            slot for start, slot in by_start.items() if booked.get(start, 0) < context.capacity
        ]
    else:
        offered = list(by_start.values())
    return sorted(offered, key=lambda slot: slot.start)


async def _choose_host(repo: SchedulingRepository, candidates: list[HostRef]) -> HostRef:
    """Round-robin: pick the least-loaded host, breaking ties by pool order (stable)."""
    if len(candidates) == 1:
        return candidates[0]
    loads = await repo.host_loads(tuple(h.host_id for h in candidates))
    return min(enumerate(candidates), key=lambda pair: (loads.get(pair[1].host_id, 0), pair[0]))[1]


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

    invitee_private = _require_private(context.questions, request.invitee_private)
    guests = _clean_guests(request.guest_emails)

    now = clock.now()
    # Re-validate against freshly computed availability: each host must still offer the slot. The
    # DB exclusion constraint is the final guard against races.
    candidates: list[HostRef] = []
    for host in context.hosts:
        day = request.start_at.astimezone(ZoneInfo(host.schedule.timezone)).date()
        slots = await _host_day_slots(repo, host, context.event, now, day, day)
        if any(slot.start == request.start_at for slot in slots):
            candidates.append(host)

    end_at = request.start_at + context.event.duration

    if context.kind == "collective":
        # Every host must be free; book all of them as one linked meeting.
        if len(candidates) != len(context.hosts):
            raise SlotUnavailable(request.start_at.isoformat())
        hosts = context.hosts
        booking_id = await repo.insert_collective_booking(
            context=context,
            host_ids=tuple(h.host_id for h in hosts),
            start_at=request.start_at,
            end_at=end_at,
            invitee_name=request.invitee_name,
            invitee_email=request.invitee_email,
            invitee_timezone=request.invitee_timezone,
            guest_emails=guests,
            invitee_private=invitee_private,
        )
        primary = hosts[0]
        additional = tuple(h.email for h in hosts[1:])
    else:
        if not candidates:
            raise SlotUnavailable(request.start_at.isoformat())
        primary = await _choose_host(repo, candidates)
        is_group = context.kind == "group"
        booking_id = await repo.insert_booking(
            context=context,
            host_id=primary.host_id,
            start_at=request.start_at,
            end_at=end_at,
            invitee_name=request.invitee_name,
            invitee_email=request.invitee_email,
            invitee_timezone=request.invitee_timezone,
            guest_emails=guests,
            invitee_private=invitee_private,
            blocks_host=not is_group,
            max_at_slot=context.capacity if is_group else None,
        )
        additional = ()

    return BookingConfirmation(
        booking_id=booking_id,
        host_id=primary.host_id,
        event_title=context.title,
        host_name=primary.name,
        host_email=primary.email,
        host_timezone=primary.timezone,
        invitee_name=request.invitee_name,
        invitee_email=request.invitee_email,
        invitee_timezone=request.invitee_timezone,
        location_type=context.location_type,
        start_at=request.start_at,
        end_at=end_at,
        guest_emails=guests,
        additional_host_emails=additional,
    )


def _require_private(
    questions: tuple[BookingQuestion, ...], invitee_private: str | None
) -> str | None:
    """Enforce that a sealed blob is present when the event type has required questions.

    Answers are zero-knowledge (sealed client-side), so the server cannot validate individual
    fields — the booking page enforces per-field requirements before sealing. The server only
    checks that *something* was submitted when any question is required."""
    if invitee_private is None and any(q.required for q in questions):
        raise InvalidBookingInput("answers to the required questions are missing")
    return invitee_private


def _clean_guests(guest_emails: tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for raw in guest_emails:
        email = raw.strip().lower()
        if email and email not in seen:
            seen.append(email)
    if len(seen) > MAX_GUESTS:
        raise InvalidBookingInput(f"at most {MAX_GUESTS} guests are allowed")
    return tuple(seen)


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
