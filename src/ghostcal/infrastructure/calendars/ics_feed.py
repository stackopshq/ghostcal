"""Fetch and parse a public iCalendar (ICS) feed. SSRF-guarded; redirects re-validated.

Returns simple event tuples; recurrence is intentionally NOT expanded here (public feeds are
usually explicit dated events — holidays, fixtures). Bounded in size to avoid a huge feed OOMing
the worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from icalendar import Calendar

from ghostcal.infrastructure.security.egress import (
    assert_public_url,
    calendar_private_networks,
)

_MAX_BYTES = 8 * 1024 * 1024  # 8 MiB
_MAX_EVENTS = 5000


class IcsFeedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class FeedEvent:
    uid: str
    start_at: datetime
    end_at: datetime
    all_day: bool
    summary: str | None


def _to_dt(value: object) -> tuple[datetime, bool]:
    """Normalise an icalendar date/datetime to a tz-aware UTC datetime + all-day flag."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.astimezone(UTC), False
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC), True
    raise IcsFeedError("unsupported date value")


async def fetch_feed(url: str) -> list[FeedEvent]:
    """Fetch the ICS at ``url`` and return its VEVENTs. Raises ``IcsFeedError`` on any failure."""
    try:
        assert_public_url(url, allowed_private_networks=calendar_private_networks())
    except Exception as exc:
        raise IcsFeedError(f"blocked url: {exc}") from exc
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            resp = await client.get(url, headers={"accept": "text/calendar"})
    except httpx.HTTPError as exc:
        raise IcsFeedError(str(exc)) from exc
    if resp.status_code != 200:
        raise IcsFeedError(f"feed returned {resp.status_code}")
    body = resp.content[:_MAX_BYTES]

    try:
        cal = Calendar.from_ical(body)
    except Exception as exc:
        raise IcsFeedError(f"could not parse feed: {exc}") from exc

    events: list[FeedEvent] = []
    for comp in cal.walk("VEVENT"):
        dtstart = comp.get("dtstart")
        if dtstart is None:
            continue
        start_at, all_day = _to_dt(dtstart.dt)
        dtend = comp.get("dtend")
        if dtend is not None:
            end_at, _ = _to_dt(dtend.dt)
        else:
            end_at = start_at
        uid = str(comp.get("uid") or f"{start_at.isoformat()}-{comp.get('summary') or ''}")[:512]
        summary = comp.get("summary")
        events.append(
            FeedEvent(
                uid=uid,
                start_at=start_at,
                end_at=end_at,
                all_day=all_day,
                summary=str(summary) if summary else None,
            )
        )
        if len(events) >= _MAX_EVENTS:
            break
    return events
