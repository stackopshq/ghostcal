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

# Supported custom-question input types (collected from the invitee at booking time).
QUESTION_TYPES: tuple[str, ...] = ("text", "textarea", "phone", "select", "checkbox")


@dataclass(frozen=True, slots=True)
class BookingQuestion:
    id: str
    label: str
    type: str = "text"
    required: bool = False
    options: tuple[str, ...] = ()


def question_to_dict(question: BookingQuestion) -> dict[str, object]:
    return {
        "id": question.id,
        "label": question.label,
        "type": question.type,
        "required": question.required,
        "options": list(question.options),
    }


def question_from_dict(raw: dict[str, object]) -> BookingQuestion:
    raw_options = raw.get("options")
    options = raw_options if isinstance(raw_options, list) else []
    return BookingQuestion(
        id=str(raw.get("id", "")),
        label=str(raw.get("label", "")),
        type=str(raw.get("type", "text")),
        required=bool(raw.get("required", False)),
        options=tuple(str(o) for o in options),
    )


def questions_to_json(questions: tuple[BookingQuestion, ...]) -> list[dict[str, object]]:
    return [question_to_dict(q) for q in questions]


def questions_from_json(raw: object) -> tuple[BookingQuestion, ...]:
    items = raw if isinstance(raw, list) else []
    return tuple(question_from_dict(r) for r in items)


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
    questions: tuple[BookingQuestion, ...] = ()


@dataclass(frozen=True, slots=True)
class EventTypeData:
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_slug: str
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
    questions: tuple[BookingQuestion, ...] = ()


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
    _validate_questions(data.questions)


def _validate_questions(questions: tuple[BookingQuestion, ...]) -> None:
    seen: set[str] = set()
    for q in questions:
        if not q.id.strip():
            raise InvalidEventType("question id is required")
        if q.id in seen:
            raise InvalidEventType(f"duplicate question id: {q.id}")
        seen.add(q.id)
        if not q.label.strip():
            raise InvalidEventType(f"question '{q.id}' needs a label")
        if q.type not in QUESTION_TYPES:
            raise InvalidEventType(f"unknown question type: {q.type}")
        if q.type == "select" and not q.options:
            raise InvalidEventType(f"select question '{q.id}' needs options")


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
