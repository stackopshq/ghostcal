"""Calendar use cases: CRUD for calendars/events and the unified agenda read.

Framework-free. Persistence is a port (``CalendarRepository``); the recurrence math is the pure
domain engine. Event ``content`` is an opaque sealed blob — the server never reads it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from ghostcal.domain.calendar import RecurringEvent, expand

# Overall cap on agenda items returned in one read (defence-in-depth against expansion blow-up).
MAX_AGENDA_ITEMS = 5000


class CalendarError(Exception):
    pass


class CalendarNotFound(CalendarError):
    pass


class EventNotFound(CalendarError):
    pass


@dataclass(frozen=True, slots=True)
class CalendarRecord:
    id: uuid.UUID
    name: str
    color: str
    is_default: bool
    # Set when this calendar belongs to another member and was shared with the viewer (read-only).
    is_shared: bool = False
    owner_name: str | None = None


@dataclass(frozen=True, slots=True)
class ShareRecord:
    user_id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class EventInput:
    calendar_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    timezone: str
    all_day: bool = False
    rrule: str | None = None
    exdates: tuple[str, ...] = ()
    content: str | None = None  # sealed blob
    reminder_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class EventRecord:
    id: uuid.UUID
    calendar_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    timezone: str
    all_day: bool
    rrule: str | None
    exdates: tuple[str, ...]
    content: str | None
    reminder_minutes: int | None
    # True when this event comes from a calendar shared with the viewer (not theirs to edit).
    read_only: bool = False


@dataclass(frozen=True, slots=True)
class BusyBlock:
    start_at: datetime
    end_at: datetime
    title: str | None  # cleartext label for bookings/external busy (None when unknown)


@dataclass(frozen=True, slots=True)
class SubEvent:
    subscription_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    all_day: bool
    summary: str | None


@dataclass(frozen=True, slots=True)
class AgendaItem:
    source: str  # "event" | "booking" | "external" | "subscription"
    start: datetime
    end: datetime
    all_day: bool = False
    calendar_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    content: str | None = None  # sealed blob (events) — decrypted in the browser
    title: str | None = None  # cleartext label (bookings/external)
    read_only: bool = False  # event from a calendar shared with the viewer
    reminder_minutes: int | None = None  # minutes before start to alert (events only)


class CalendarRepository:
    async def list_calendars(self, owner_id: uuid.UUID) -> list[CalendarRecord]:
        raise NotImplementedError

    async def ensure_default_calendar(self, owner_id: uuid.UUID) -> CalendarRecord:
        """Return the owner's default calendar, creating it on first use."""
        raise NotImplementedError

    async def create_calendar(
        self, owner_id: uuid.UUID, *, name: str, color: str
    ) -> CalendarRecord:
        raise NotImplementedError

    async def share_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Share the owner's calendar with another member. False if they don't own it."""
        raise NotImplementedError

    async def unshare_calendar(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        raise NotImplementedError

    async def list_shares(self, owner_id: uuid.UUID, calendar_id: uuid.UUID) -> list[ShareRecord]:
        raise NotImplementedError

    async def get_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> EventRecord | None:
        raise NotImplementedError

    async def create_event(self, owner_id: uuid.UUID, data: EventInput) -> uuid.UUID:
        raise NotImplementedError

    async def update_event(
        self, owner_id: uuid.UUID, event_id: uuid.UUID, data: EventInput
    ) -> bool:
        raise NotImplementedError

    async def delete_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def events_overlapping(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[EventRecord]:
        """Stored events that might have an occurrence in the window (recurring ones included)."""
        raise NotImplementedError

    async def bookings_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[BusyBlock]:
        raise NotImplementedError

    async def external_busy_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[BusyBlock]:
        raise NotImplementedError

    async def subscription_events_in_range(
        self, owner_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[SubEvent]:
        raise NotImplementedError


async def list_calendars(repo: CalendarRepository, owner_id: uuid.UUID) -> list[CalendarRecord]:
    calendars = await repo.list_calendars(owner_id)
    # Ensure the user has at least one calendar of their own (shared ones don't count).
    if not any(not c.is_shared for c in calendars):
        return [await repo.ensure_default_calendar(owner_id), *calendars]
    return calendars


async def share_calendar(
    repo: CalendarRepository, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if not await repo.share_calendar(owner_id, calendar_id, user_id):
        raise CalendarNotFound(str(calendar_id))


async def unshare_calendar(
    repo: CalendarRepository, owner_id: uuid.UUID, calendar_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if not await repo.unshare_calendar(owner_id, calendar_id, user_id):
        raise CalendarNotFound(str(calendar_id))


async def list_shares(
    repo: CalendarRepository, owner_id: uuid.UUID, calendar_id: uuid.UUID
) -> list[ShareRecord]:
    return await repo.list_shares(owner_id, calendar_id)


async def get_event(
    repo: CalendarRepository, owner_id: uuid.UUID, event_id: uuid.UUID
) -> EventRecord:
    event = await repo.get_event(owner_id, event_id)
    if event is None:
        raise EventNotFound(str(event_id))
    return event


async def create_event(
    repo: CalendarRepository, owner_id: uuid.UUID, data: EventInput
) -> uuid.UUID:
    if data.end_at < data.start_at:
        raise CalendarError("end_at must not be before start_at")
    return await repo.create_event(owner_id, data)


async def update_event(
    repo: CalendarRepository, owner_id: uuid.UUID, event_id: uuid.UUID, data: EventInput
) -> None:
    if data.end_at < data.start_at:
        raise CalendarError("end_at must not be before start_at")
    if not await repo.update_event(owner_id, event_id, data):
        raise EventNotFound(str(event_id))


async def delete_event(repo: CalendarRepository, owner_id: uuid.UUID, event_id: uuid.UUID) -> None:
    if not await repo.delete_event(owner_id, event_id):
        raise EventNotFound(str(event_id))


def _to_recurring(e: EventRecord) -> RecurringEvent:
    exdates = tuple(datetime.fromisoformat(x) for x in e.exdates)
    return RecurringEvent(
        id=str(e.id),
        start_at=e.start_at,
        end_at=e.end_at,
        timezone=e.timezone,
        all_day=e.all_day,
        rrule=e.rrule,
        exdates=exdates,
    )


async def get_agenda(
    repo: CalendarRepository, owner_id: uuid.UUID, start: datetime, end: datetime
) -> list[AgendaItem]:
    """The owner's unified agenda over ``[start, end)``: events + bookings + external busy."""
    items: list[AgendaItem] = []

    events = await repo.events_overlapping(owner_id, start, end)
    by_id = {str(e.id): e for e in events}
    for e in events:
        if len(items) >= MAX_AGENDA_ITEMS:
            break
        for occ in expand(_to_recurring(e), start, end):
            src = by_id[occ.event_id]
            items.append(
                AgendaItem(
                    source="event",
                    start=occ.start,
                    end=occ.end,
                    all_day=occ.all_day,
                    calendar_id=src.calendar_id,
                    event_id=src.id,
                    content=src.content,
                    read_only=src.read_only,
                    reminder_minutes=src.reminder_minutes,
                )
            )

    for b in await repo.bookings_in_range(owner_id, start, end):
        items.append(AgendaItem(source="booking", start=b.start_at, end=b.end_at, title=b.title))
    for b in await repo.external_busy_in_range(owner_id, start, end):
        items.append(AgendaItem(source="external", start=b.start_at, end=b.end_at, title=b.title))
    for se in await repo.subscription_events_in_range(owner_id, start, end):
        items.append(
            AgendaItem(
                source="subscription",
                start=se.start_at,
                end=se.end_at,
                all_day=se.all_day,
                calendar_id=se.subscription_id,  # frontend colours/toggles it like a calendar
                title=se.summary,
                read_only=True,
            )
        )

    return sorted(items, key=lambda i: i.start)


# Re-exported for the route layer's type hints.
__all__ = [
    "AgendaItem",
    "BusyBlock",
    "CalendarError",
    "CalendarNotFound",
    "CalendarRecord",
    "CalendarRepository",
    "EventInput",
    "EventNotFound",
    "EventRecord",
    "ShareRecord",
    "create_event",
    "delete_event",
    "get_agenda",
    "get_event",
    "list_calendars",
    "list_shares",
    "share_calendar",
    "unshare_calendar",
    "update_event",
]
