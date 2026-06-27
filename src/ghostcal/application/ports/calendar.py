"""Calendar client port: read busy time from and write events to an external calendar (CalDAV).

The application depends on this interface; the CalDAV library lives behind the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ghostcal.domain.time import TimeRange


class CalendarError(Exception):
    pass


class CalendarAuthError(CalendarError):
    """Credentials or server URL rejected."""


@dataclass(frozen=True, slots=True)
class CalendarInfo:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class CalendarCredentials:
    server_url: str
    username: str
    password: str


class CalendarClient(Protocol):
    async def list_calendars(self, creds: CalendarCredentials) -> list[CalendarInfo]:
        """Validate credentials and return the available calendars."""
        ...

    async def fetch_busy(
        self, creds: CalendarCredentials, calendar_url: str, start: datetime, end: datetime
    ) -> list[TimeRange]:
        """Busy intervals (UTC) from events overlapping [start, end)."""
        ...

    async def create_event(
        self,
        creds: CalendarCredentials,
        calendar_url: str,
        *,
        uid: str,
        summary: str,
        description: str,
        location: str,
        start: datetime,
        end: datetime,
    ) -> str:
        """Create an event and return its URL."""
        ...

    async def delete_event(
        self, creds: CalendarCredentials, calendar_url: str, uid: str
    ) -> None: ...
