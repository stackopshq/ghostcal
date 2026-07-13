"""Account export use cases: data portability (GDPR art. 20). See ADR-0006 §5.

A zero-knowledge product cannot export server-side. Event content, task content and the invitee's
answers are sealed to the organization's public key — the server holds ciphertext it can never open,
so an endpoint that "returns everything" would hand the user a file full of base64 and call it
portability.

So this returns the user's complete record set **including the sealed blobs, verbatim**, and the
browser — which holds the org private key, unwrapped at login — decrypts them and assembles the
final archive. The sealed fields are named ``*_sealed`` throughout to make it obvious, at the
boundary, which parts still need opening.

Nothing secret is exported: no password hash, no refresh token, no webhook signing secret, no CalDAV
password, no wrapped key material. An export is a file that ends up in a Downloads folder.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time


class ExportError(Exception):
    """Base class for export errors."""


class UnknownUser(ExportError):
    pass


@dataclass(frozen=True)
class ProfileExport:
    id: uuid.UUID
    email: str
    name: str
    timezone: str
    email_verified_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class OrganizationExport:
    id: uuid.UUID
    name: str
    slug: str
    role: str


@dataclass(frozen=True)
class CalendarEventExport:
    id: uuid.UUID
    calendar_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    all_day: bool
    timezone: str
    rrule: str | None
    exdates: list[str]
    status: str
    reminder_minutes: int | None
    # Sealed {title, description, location}. Opened in the browser, never here.
    content_sealed: str | None


@dataclass(frozen=True)
class CalendarExport:
    id: uuid.UUID
    name: str
    color: str
    is_default: bool
    events: list[CalendarEventExport] = field(default_factory=list)


@dataclass(frozen=True)
class TaskExport:
    id: uuid.UUID
    due_at: datetime | None
    completed: bool
    completed_at: datetime | None
    reminder_minutes: int | None
    # Sealed {title, notes}.
    content_sealed: str | None


@dataclass(frozen=True)
class BookingExport:
    """A booking the user hosted. Its invitee is a second data subject, so only what the host can
    already see on their own dashboard is exported — nothing is newly disclosed by exporting."""

    id: uuid.UUID
    event_type_title: str
    start_at: datetime
    end_at: datetime
    status: str
    invitee_email: str
    invitee_timezone: str
    location: str | None
    # Sealed {name, answers, notes} — the invitee sealed this to the org key at booking time.
    invitee_private_sealed: str | None


@dataclass(frozen=True)
class AvailabilityRuleExport:
    weekday: int
    start_time: time
    end_time: time


@dataclass(frozen=True)
class AvailabilityOverrideExport:
    date: date
    is_available: bool
    start_time: time | None
    end_time: time | None


@dataclass(frozen=True)
class ScheduleExport:
    id: uuid.UUID
    name: str
    timezone: str
    rules: list[AvailabilityRuleExport] = field(default_factory=list)
    overrides: list[AvailabilityOverrideExport] = field(default_factory=list)


@dataclass(frozen=True)
class EventTypeExport:
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    duration_min: int
    kind: str
    active: bool


@dataclass(frozen=True)
class SubscriptionExport:
    id: uuid.UUID
    name: str
    url: str
    color: str
    status: str


@dataclass(frozen=True)
class CaldavConnectionExport:
    """CalDAV link metadata. The stored password is deliberately absent — see the module
    docstring."""

    id: uuid.UUID
    server_url: str
    username: str
    calendar_name: str | None
    status: str


@dataclass(frozen=True)
class AccountExport:
    profile: ProfileExport
    organizations: list[OrganizationExport] = field(default_factory=list)
    calendars: list[CalendarExport] = field(default_factory=list)
    tasks: list[TaskExport] = field(default_factory=list)
    bookings: list[BookingExport] = field(default_factory=list)
    event_types: list[EventTypeExport] = field(default_factory=list)
    schedules: list[ScheduleExport] = field(default_factory=list)
    subscriptions: list[SubscriptionExport] = field(default_factory=list)
    caldav_connections: list[CaldavConnectionExport] = field(default_factory=list)


class ExportRepository:
    async def profile(self, user_id: uuid.UUID) -> ProfileExport | None:
        raise NotImplementedError

    async def organizations(self, user_id: uuid.UUID) -> list[OrganizationExport]:
        raise NotImplementedError

    async def calendars(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[CalendarExport]:
        """The user's calendars in one organization, each with its events (content still sealed)."""
        raise NotImplementedError

    async def tasks(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[TaskExport]:
        raise NotImplementedError

    async def bookings(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[BookingExport]:
        raise NotImplementedError

    async def event_types(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[EventTypeExport]:
        raise NotImplementedError

    async def schedules(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[ScheduleExport]:
        raise NotImplementedError

    async def subscriptions(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[SubscriptionExport]:
        raise NotImplementedError

    async def caldav_connections(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[CaldavConnectionExport]:
        raise NotImplementedError


class ExportService:
    def __init__(self, repo: ExportRepository) -> None:
        self._repo = repo

    async def export(self, user_id: uuid.UUID) -> AccountExport:
        profile = await self._repo.profile(user_id)
        if profile is None:
            raise UnknownUser("unknown user")

        organizations = await self._repo.organizations(user_id)
        export = AccountExport(profile=profile, organizations=organizations)

        # Only records the user owns or hosts — a member of a shared organization is entitled to
        # their own data, not to the organization's.
        for org in organizations:
            export.calendars.extend(await self._repo.calendars(org.id, user_id))
            export.tasks.extend(await self._repo.tasks(org.id, user_id))
            export.bookings.extend(await self._repo.bookings(org.id, user_id))
            export.event_types.extend(await self._repo.event_types(org.id, user_id))
            export.schedules.extend(await self._repo.schedules(org.id, user_id))
            export.subscriptions.extend(await self._repo.subscriptions(org.id, user_id))
            export.caldav_connections.extend(await self._repo.caldav_connections(org.id, user_id))
        return export
