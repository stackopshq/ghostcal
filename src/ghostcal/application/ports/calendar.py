"""Calendar client port: read busy time from and write events to an external calendar (CalDAV).

The application depends on this interface; the CalDAV library lives behind the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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


@dataclass(frozen=True, slots=True)
class BusyEvent:
    """A busy interval from an external calendar, with its summary if the server exposed one."""

    start: datetime
    end: datetime
    summary: str | None = None


class CalendarClient(Protocol):
    async def list_calendars(self, creds: CalendarCredentials) -> list[CalendarInfo]:
        """Validate credentials and return the available calendars."""
        ...

    async def fetch_busy(
        self,
        creds: CalendarCredentials,
        calendar_url: str,
        start: datetime,
        end: datetime,
        *,
        default_timezone: str = "UTC",
    ) -> list[BusyEvent]:
        """Busy events (UTC, with summaries) overlapping [start, end).

        ``default_timezone`` ancre ce que le calendrier ne date pas lui-même :
        une journée entière porte une date nue, sans fuseau, et minuit n'est
        pas minuit UTC. L'adaptateur préfère ce que dit le calendrier (TZID,
        X-WR-TIMEZONE) et ne retombe là-dessus qu'à défaut — mais une réponse
        CalDAV ne dit souvent rien, donc c'est le cas courant.
        """
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
        rrule: str | None = None,
    ) -> str:
        """Create an event and return its URL."""
        ...

    async def delete_event(
        self, creds: CalendarCredentials, calendar_url: str, uid: str
    ) -> None: ...
