"""Pure recurrence expansion: turn an event's RRULE into concrete UTC occurrences in a window.

No I/O. Like the availability engine, this is timezone- and DST-correct: a recurring event repeats
at the same **wall-clock** time in its IANA timezone, and each occurrence is then converted to UTC
(so "every Monday 09:00 in Europe/Zurich" lands on the right UTC instant on both sides of a DST
change). The recurrence is generated in naive local time precisely so dateutil does not carry a
fixed UTC offset across DST boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

# Safety cap: never materialize more than this many occurrences from one event in one window.
MAX_OCCURRENCES = 2000


@dataclass(frozen=True, slots=True)
class RecurringEvent:
    """The cleartext scheduling shape of a calendar event (no content — that stays sealed)."""

    id: str
    start_at: datetime  # timezone-aware (UTC)
    end_at: datetime  # timezone-aware (UTC)
    timezone: str  # IANA zone the wall-clock recurrence repeats in
    all_day: bool = False
    rrule: str | None = None
    exdates: tuple[datetime, ...] = field(default_factory=tuple)  # excluded occurrence starts (UTC)


@dataclass(frozen=True, slots=True)
class Occurrence:
    event_id: str
    start: datetime  # UTC
    end: datetime  # UTC
    all_day: bool


def expand(event: RecurringEvent, window_start: datetime, window_end: datetime) -> list[Occurrence]:
    """All occurrences of ``event`` that overlap ``[window_start, window_end)`` (both UTC-aware)."""
    duration = event.end_at - event.start_at
    exdates = {_to_utc(d) for d in event.exdates}

    if not event.rrule:
        starts = [event.start_at]
    else:
        starts = _recurring_starts(event, window_start, window_end, duration)

    occurrences: list[Occurrence] = []
    for start in starts:
        if start in exdates:
            continue
        end = start + duration
        # Overlap test against the window (half-open).
        if start < window_end and end > window_start:
            occurrences.append(
                Occurrence(event_id=event.id, start=start, end=end, all_day=event.all_day)
            )
    return occurrences


def _recurring_starts(
    event: RecurringEvent, window_start: datetime, window_end: datetime, duration: timedelta
) -> list[datetime]:
    zone = ZoneInfo(event.timezone)
    # dtstart as naive local wall-clock, so the rule repeats the local time (not a fixed offset).
    dtstart_local = event.start_at.astimezone(zone).replace(tzinfo=None)
    rule = rrulestr(event.rrule or "", dtstart=dtstart_local)

    # Bound generation to the window in local naive time. Start a duration early so an occurrence
    # that began before the window but still overlaps it is included.
    after_local = (window_start - duration).astimezone(zone).replace(tzinfo=None)
    before_local = window_end.astimezone(zone).replace(tzinfo=None)

    starts: list[datetime] = []
    for occ_local in rule.between(after_local, before_local, inc=True):
        # Reattach the zone (fold=0 by default; a nonexistent spring-forward local time is nudged
        # forward by zoneinfo's offset rules) and convert to the UTC instant.
        starts.append(occ_local.replace(tzinfo=zone).astimezone(UTC))
        if len(starts) >= MAX_OCCURRENCES:
            break
    return starts


def _to_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC) if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
