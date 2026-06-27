"""Event-type management use cases (host dashboard).

An event type is a bookable meeting template owned by a host inside an organization. For this
first slice it uses the owner's availability schedule implicitly (schedule_id stays null and the
booking layer falls back to the owner's schedule); explicit schedule selection comes later.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

# Allowed meeting locations. The canonical list lives in the application layer.
LOCATION_TYPES: tuple[str, ...] = (
    "google_meet",
    "ms_teams",
    "zoom",
    "in_person",
    "phone",
    "custom",
)


class EventTypeError(Exception):
    """Base class for event-type use-case errors."""


class EventTypeNotFound(EventTypeError):
    pass


class InvalidEventType(EventTypeError):
    pass


class EventTypeInUse(EventTypeError):
    """The event type has bookings and cannot be deleted."""


@dataclass(frozen=True, slots=True)
class EventTypeInput:
    title: str
    duration_min: int
    slot_interval_min: int = 15
    buffer_before_min: int = 0
    buffer_after_min: int = 0
    min_notice_min: int = 0
    date_window_days: int = 60
    max_per_day: int | None = None
    location_type: str = "google_meet"
    description: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class EventTypeData:
    id: uuid.UUID
    organization_id: uuid.UUID
    slug: str
    title: str
    description: str | None
    duration_min: int
    slot_interval_min: int
    buffer_before_min: int
    buffer_after_min: int
    min_notice_min: int
    date_window_days: int
    max_per_day: int | None
    location_type: str
    active: bool


class EventTypesRepository:
    async def list_for_owner(self, owner_id: uuid.UUID) -> list[EventTypeData]:
        raise NotImplementedError

    async def get(self, event_type_id: uuid.UUID, owner_id: uuid.UUID) -> EventTypeData | None:
        raise NotImplementedError

    async def create(self, owner_id: uuid.UUID, slug: str, data: EventTypeInput) -> uuid.UUID:
        raise NotImplementedError

    async def update(
        self, event_type_id: uuid.UUID, owner_id: uuid.UUID, data: EventTypeInput
    ) -> bool:
        raise NotImplementedError

    async def delete(self, event_type_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        """Return False if not found. Raise ``EventTypeInUse`` if it has bookings."""
        raise NotImplementedError


def _slugify(title: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
    base = "-".join(filter(None, base.split("-")))[:80] or "event"
    # Random suffix guarantees uniqueness without surfacing slug conflicts to the user.
    return f"{base}-{secrets.token_hex(3)}"


def _validate(data: EventTypeInput) -> None:
    if not data.title.strip():
        raise InvalidEventType("title is required")
    if data.duration_min <= 0:
        raise InvalidEventType("duration must be positive")
    if data.slot_interval_min <= 0:
        raise InvalidEventType("slot interval must be positive")
    if data.location_type not in LOCATION_TYPES:
        raise InvalidEventType(f"unknown location type: {data.location_type}")
    if data.max_per_day is not None and data.max_per_day <= 0:
        raise InvalidEventType("max per day must be positive")


async def list_event_types(repo: EventTypesRepository, owner_id: uuid.UUID) -> list[EventTypeData]:
    return await repo.list_for_owner(owner_id)


async def get_event_type(
    repo: EventTypesRepository, event_type_id: uuid.UUID, owner_id: uuid.UUID
) -> EventTypeData:
    event_type = await repo.get(event_type_id, owner_id)
    if event_type is None:
        raise EventTypeNotFound(str(event_type_id))
    return event_type


async def create_event_type(
    repo: EventTypesRepository, owner_id: uuid.UUID, data: EventTypeInput
) -> uuid.UUID:
    _validate(data)
    return await repo.create(owner_id, _slugify(data.title), data)


async def update_event_type(
    repo: EventTypesRepository,
    event_type_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: EventTypeInput,
) -> None:
    _validate(data)
    if not await repo.update(event_type_id, owner_id, data):
        raise EventTypeNotFound(str(event_type_id))


async def delete_event_type(
    repo: EventTypesRepository, event_type_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    if not await repo.delete(event_type_id, owner_id):
        raise EventTypeNotFound(str(event_type_id))
