"""Meetings (bookings) read use cases for the host dashboard."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from ghostcal.application.meeting_rooms import new_room_url


class MeetingNotFound(Exception):
    pass


class InvalidMeetingUrl(ValueError):
    pass


# Same bound as the column had before it was encrypted; a real meeting link is far shorter.
MAX_MEETING_URL_LENGTH = 2048


@dataclass(frozen=True, slots=True)
class BookingSummary:
    id: uuid.UUID
    event_title: str
    # None for booking-page bookings (zero-knowledge); the dashboard shows the name from the
    # decrypted ``invitee_private`` blob instead.
    invitee_name: str | None
    invitee_email: str
    invitee_timezone: str
    start_at: datetime
    end_at: datetime
    status: str
    location: str | None
    meeting_url: str | None
    external_event_uid: str | None = None
    # Sealed-box blob with the invitee's answers + notes; the dashboard decrypts it in-browser.
    invitee_private: str | None = None
    organization_id: uuid.UUID | None = None
    guest_emails: list[str] = field(default_factory=list)


class MeetingsRepository:
    async def list_for_host(
        self, host_id: uuid.UUID, *, upcoming: bool, now: datetime
    ) -> list[BookingSummary]:
        """Confirmed bookings for the host. ``upcoming`` selects future vs past, ordered
        chronologically (ascending for upcoming, most-recent-first for past)."""
        raise NotImplementedError

    async def cancel(self, booking_id: uuid.UUID, host_id: uuid.UUID) -> BookingSummary | None:
        """Mark the host's confirmed booking cancelled (freeing the slot). Return the cancelled
        booking, or None if not found."""
        raise NotImplementedError

    async def set_meeting_url(
        self, booking_id: uuid.UUID, host_id: uuid.UUID, meeting_url: str
    ) -> BookingSummary | None:
        """Store the meeting link on the host's upcoming confirmed booking (every row of a
        collective meeting). Return the updated booking, or None if not found."""
        raise NotImplementedError


def validate_meeting_url(raw: str) -> str:
    """An absolute https URL, which is what every video service hands out. Anything else
    (javascript:, http:, a bare host) is refused: the link goes into an email to the invitee."""
    url = raw.strip()
    if len(url) > MAX_MEETING_URL_LENGTH or any(c.isspace() for c in url):
        raise InvalidMeetingUrl(raw)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise InvalidMeetingUrl(raw)
    return url


async def list_meetings(
    repo: MeetingsRepository, host_id: uuid.UUID, *, upcoming: bool, now: datetime
) -> list[BookingSummary]:
    return await repo.list_for_host(host_id, upcoming=upcoming, now=now)


async def cancel_meeting(
    repo: MeetingsRepository, booking_id: uuid.UUID, host_id: uuid.UUID
) -> BookingSummary:
    cancelled = await repo.cancel(booking_id, host_id)
    if cancelled is None:
        raise MeetingNotFound(str(booking_id))
    return cancelled


async def share_meeting_link(
    repo: MeetingsRepository, booking_id: uuid.UUID, host_id: uuid.UUID, raw_url: str
) -> BookingSummary:
    updated = await repo.set_meeting_url(booking_id, host_id, validate_meeting_url(raw_url))
    if updated is None:
        raise MeetingNotFound(str(booking_id))
    return updated


async def share_generated_room(
    repo: MeetingsRepository, booking_id: uuid.UUID, host_id: uuid.UUID, location_type: str
) -> BookingSummary:
    """Create a fresh room with a provider that needs no account (kMeet) and share it like a
    pasted link. Raise ``InvalidMeetingUrl`` for a provider GhostCal cannot generate rooms for."""
    url = new_room_url(location_type)
    if url is None:
        raise InvalidMeetingUrl(location_type)
    return await share_meeting_link(repo, booking_id, host_id, url)
