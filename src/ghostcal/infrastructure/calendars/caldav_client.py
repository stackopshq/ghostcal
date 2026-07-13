"""CalDAV adapter. The ``caldav`` library is synchronous, so every call runs in a worker thread.

Busy time is read by expanding events in a window; events marked transparent/cancelled are
ignored. Events are written/removed as minimal VEVENTs identified by our own UID.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import caldav
from caldav.lib.error import AuthorizationError

from ghostcal.application.ports.calendar import (
    BusyEvent,
    CalendarAuthError,
    CalendarCredentials,
    CalendarError,
    CalendarInfo,
)
from ghostcal.domain.time import TimeRange
from ghostcal.infrastructure.security.egress import assert_public_url


def _client(creds: CalendarCredentials) -> Any:
    # SSRF guard: never connect to a CalDAV server on an internal/loopback/metadata address.
    assert_public_url(creds.server_url)
    # The caldav library ships incomplete type info; treat its objects as Any at this boundary.
    return caldav.DAVClient(  # type: ignore[operator]
        url=creds.server_url, username=creds.username, password=creds.password
    )


def _ics_dt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ics_text(value: str) -> str:
    """Escape an iCalendar text value per RFC 5545 and strip CR/LF (anti property-injection)."""
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _as_utc_range(start_value: object, end_value: object) -> TimeRange | None:
    """Normalize an event's start/end (date or datetime, naive or aware) to a UTC TimeRange."""

    def to_dt(value: object, *, end: bool) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, date):
            # All-day: span the whole day (treated as busy).
            base = datetime.combine(value, time(0, 0), tzinfo=UTC)
            return base + timedelta(days=1) if end else base
        return None

    start = to_dt(start_value, end=False)
    end = to_dt(end_value, end=True)
    if start is None:
        return None
    if end is None or end <= start:
        end = start + timedelta(minutes=30)
    return TimeRange(start, end)


class CaldavCalendarClient:
    async def list_calendars(self, creds: CalendarCredentials) -> list[CalendarInfo]:
        return await asyncio.to_thread(self._list_calendars, creds)

    async def fetch_busy(
        self, creds: CalendarCredentials, calendar_url: str, start: datetime, end: datetime
    ) -> list[BusyEvent]:
        return await asyncio.to_thread(self._fetch_busy, creds, calendar_url, start, end)

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
        return await asyncio.to_thread(
            self._create_event,
            creds,
            calendar_url,
            uid,
            summary,
            description,
            location,
            start,
            end,
            rrule,
        )

    async def delete_event(self, creds: CalendarCredentials, calendar_url: str, uid: str) -> None:
        await asyncio.to_thread(self._delete_event, creds, calendar_url, uid)

    # --- sync implementations (run in a thread) ----------------------------------------------

    def _list_calendars(self, creds: CalendarCredentials) -> list[CalendarInfo]:
        try:
            principal = _client(creds).principal()
            calendars = principal.calendars()
        except AuthorizationError as exc:
            raise CalendarAuthError("invalid credentials") from exc
        except Exception as exc:  # network / server / parsing
            raise CalendarError(str(exc)) from exc
        result: list[CalendarInfo] = []
        for cal in calendars:
            name = getattr(cal, "name", None)
            if not name:
                try:
                    name = cal.get_display_name()
                except Exception:
                    name = None
            result.append(CalendarInfo(name=name or str(cal.url), url=str(cal.url)))
        return result

    def _fetch_busy(
        self, creds: CalendarCredentials, calendar_url: str, start: datetime, end: datetime
    ) -> list[BusyEvent]:
        try:
            assert_public_url(calendar_url)
            calendar = _client(creds).calendar(url=calendar_url)
            events = calendar.search(start=start, end=end, event=True, expand=True)
        except AuthorizationError as exc:
            raise CalendarAuthError("invalid credentials") from exc
        except Exception as exc:
            raise CalendarError(str(exc)) from exc

        busy: list[BusyEvent] = []
        for event in events:
            for comp in event.icalendar_instance.walk("VEVENT"):
                if str(comp.get("transp", "")).upper() == "TRANSPARENT":
                    continue
                if str(comp.get("status", "")).upper() == "CANCELLED":
                    continue
                dtstart = comp.get("dtstart")
                dtend = comp.get("dtend")
                tr = _as_utc_range(dtstart.dt if dtstart else None, dtend.dt if dtend else None)
                if tr is not None:
                    summary = comp.get("summary")
                    busy.append(
                        BusyEvent(
                            start=tr.start, end=tr.end, summary=str(summary) if summary else None
                        )
                    )
        return busy

    def _create_event(
        self,
        creds: CalendarCredentials,
        calendar_url: str,
        uid: str,
        summary: str,
        description: str,
        location: str,
        start: datetime,
        end: datetime,
        rrule: str | None = None,
    ) -> str:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//GhostCal//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_ics_dt(start)}",
            f"DTSTART:{_ics_dt(start)}",
            f"DTEND:{_ics_dt(end)}",
            f"SUMMARY:{_ics_text(summary)}",
            f"DESCRIPTION:{_ics_text(description)}",
            f"LOCATION:{_ics_text(location)}",
        ]
        # Without this a weekly event lands on the phone once and never again. Publishing a
        # recurrence as a single occurrence is worse than not publishing it: it looks right.
        if rrule:
            lines.append(f"RRULE:{rrule}")
        lines += ["END:VEVENT", "END:VCALENDAR"]
        ical = "\r\n".join(lines)
        try:
            assert_public_url(calendar_url)
            calendar = _client(creds).calendar(url=calendar_url)
            event = calendar.save_event(ical)
        except AuthorizationError as exc:
            raise CalendarAuthError("invalid credentials") from exc
        except Exception as exc:
            raise CalendarError(str(exc)) from exc
        return str(event.url)

    def _delete_event(self, creds: CalendarCredentials, calendar_url: str, uid: str) -> None:
        try:
            assert_public_url(calendar_url)
            calendar = _client(creds).calendar(url=calendar_url)
            event = calendar.event_by_uid(uid)
        except Exception:
            return  # already gone or not found — nothing to delete
        try:
            event.delete()
        except Exception as exc:
            raise CalendarError(str(exc)) from exc
