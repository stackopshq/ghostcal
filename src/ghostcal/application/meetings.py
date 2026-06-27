"""Meetings (bookings) read use cases for the host dashboard."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class BookingSummary:
    id: uuid.UUID
    event_title: str
    invitee_name: str
    invitee_email: str
    invitee_timezone: str
    start_at: datetime
    end_at: datetime
    status: str
    location: str | None
    meeting_url: str | None


class MeetingsRepository:
    async def list_for_host(
        self, host_id: uuid.UUID, *, upcoming: bool, now: datetime
    ) -> list[BookingSummary]:
        """Confirmed bookings for the host. ``upcoming`` selects future vs past, ordered
        chronologically (ascending for upcoming, most-recent-first for past)."""
        raise NotImplementedError


async def list_meetings(
    repo: MeetingsRepository, host_id: uuid.UUID, *, upcoming: bool, now: datetime
) -> list[BookingSummary]:
    return await repo.list_for_host(host_id, upcoming=upcoming, now=now)
