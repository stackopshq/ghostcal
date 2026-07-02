"""Event attendee use cases (personal calendar invitations + RSVP).

Zero-knowledge: the event title/notes are sealed. Inviting a guest is an explicit choice to share
those details, so the organiser's browser passes the cleartext (title/location) at send time; the
server builds an ICS invitation email and never persists that cleartext. Only the guest email and
their RSVP status are stored (the server needs them to send and track invitations).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from ghostcal.application.notifications import send_event_invitation
from ghostcal.application.ports.email import EmailSender


class AttendeeError(Exception):
    pass


class EventNotOwned(AttendeeError):
    pass


@dataclass(frozen=True, slots=True)
class AttendeeRecord:
    id: uuid.UUID
    email: str
    name: str | None
    status: str


@dataclass(frozen=True, slots=True)
class NewAttendee:
    id: uuid.UUID
    email: str
    name: str | None
    token: str  # plaintext (for the link); only the hash is stored


@dataclass(frozen=True, slots=True)
class InvitationPreview:
    start_at: datetime
    end_at: datetime
    timezone: str
    all_day: bool
    status: str


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


class AttendeeRepository:
    async def owns_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def add(
        self, event_id: uuid.UUID, *, email: str, name: str | None, token_hash: str
    ) -> uuid.UUID:
        raise NotImplementedError

    async def list_for_event(self, event_id: uuid.UUID) -> list[AttendeeRecord]:
        raise NotImplementedError

    async def remove(self, event_id: uuid.UUID, attendee_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def token_for(self, event_id: uuid.UUID, attendee_id: uuid.UUID) -> str | None:
        """The stored token hash for one attendee (to rebuild an unsent invite link is impossible —
        the plaintext isn't kept; this returns the hash only for internal checks)."""
        raise NotImplementedError


class InvitationGateway:
    async def preview(self, token_hash: str) -> InvitationPreview | None:
        raise NotImplementedError

    async def respond(self, token_hash: str, status: str) -> bool:
        raise NotImplementedError


async def add_attendee(
    repo: AttendeeRepository,
    owner_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    email: str,
    name: str | None,
) -> NewAttendee:
    """Add a guest to an event the caller owns. Returns the plaintext RSVP token (shown once so the
    caller's browser can send the invitation link)."""
    if not await repo.owns_event(owner_id, event_id):
        raise EventNotOwned(str(event_id))
    token = secrets.token_urlsafe(24)
    email = email.strip().lower()
    attendee_id = await repo.add(event_id, email=email, name=name, token_hash=hash_token(token))
    return NewAttendee(id=attendee_id, email=email, name=name, token=token)


async def list_attendees(
    repo: AttendeeRepository, owner_id: uuid.UUID, event_id: uuid.UUID
) -> list[AttendeeRecord]:
    if not await repo.owns_event(owner_id, event_id):
        raise EventNotOwned(str(event_id))
    return await repo.list_for_event(event_id)


async def remove_attendee(
    repo: AttendeeRepository, owner_id: uuid.UUID, event_id: uuid.UUID, attendee_id: uuid.UUID
) -> None:
    if not await repo.owns_event(owner_id, event_id):
        raise EventNotOwned(str(event_id))
    await repo.remove(event_id, attendee_id)


async def send_invitation(
    mailer: EmailSender,
    *,
    to: str,
    title: str,
    location: str,
    organizer_name: str,
    start_at: datetime,
    end_at: datetime,
    all_day: bool,
    rsvp_url: str,
) -> None:
    """Email one guest an ICS invitation + RSVP link. The cleartext title/location come from the
    organiser's browser and are used only to build this email — never stored."""
    await send_event_invitation(
        mailer,
        to=to,
        title=title,
        location=location,
        organizer_name=organizer_name,
        start_at=start_at,
        end_at=end_at,
        all_day=all_day,
        rsvp_url=rsvp_url,
    )


async def preview_invitation(gateway: InvitationGateway, *, token: str) -> InvitationPreview | None:
    return await gateway.preview(hash_token(token))


async def respond_invitation(gateway: InvitationGateway, *, token: str, status: str) -> bool:
    return await gateway.respond(hash_token(token), status)
