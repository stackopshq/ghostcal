"""The availability engine — pure, timezone-correct slot computation.

Pipeline, per candidate day:

1. **Materialize** the day's working windows. Availability rules are *local wall-clock* times in
   the schedule's IANA timezone; each day is converted to UTC independently because the UTC
   offset changes across DST boundaries. (9:00-17:00 local is a different UTC interval the week
   before and after a DST switch — computing per-day is what keeps that correct.)
2. **Subtract** busy time, inflated by the event's buffers, leaving free intervals.
3. **Slice** each working window into ``duration``-long slots on a stable ``slot_interval`` grid,
   keeping only slots fully inside a free interval.
4. **Filter** by minimum notice and per-day cap.

No I/O and no wall-clock reads: ``now`` is injected. Everything is a pure function of the inputs,
so the whole thing is property-testable in milliseconds across hundreds of timezones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ghostcal.domain.time import TimeRange, subtract_all


@dataclass(frozen=True, slots=True)
class WeeklyRule:
    """A recurring local-time window for one weekday (0 = Monday)."""

    weekday: int
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class DateOverride:
    """A one-off change for a specific date.

    - ``is_available=False``: the day is closed (overrides any weekly rule).
    - ``is_available=True`` with ``start``/``end``: those hours replace the weekly rules.
    - ``is_available=True`` without times: fall back to the weekly rules for that weekday.
    """

    day: date
    is_available: bool
    start: time | None = None
    end: time | None = None


@dataclass(frozen=True, slots=True)
class Schedule:
    timezone: str  # IANA name, e.g. "Europe/Zurich"
    rules: tuple[WeeklyRule, ...]
    overrides: tuple[DateOverride, ...] = ()


@dataclass(frozen=True, slots=True)
class EventType:
    duration: timedelta
    slot_interval: timedelta
    buffer_before: timedelta = field(default=timedelta())
    buffer_after: timedelta = field(default=timedelta())
    min_notice: timedelta = field(default=timedelta())
    max_per_day: int | None = None


def compute_slots(
    *,
    schedule: Schedule,
    event: EventType,
    busy: list[TimeRange],
    now: datetime,
    from_date: date,
    to_date: date,
) -> list[TimeRange]:
    """Return bookable slots (UTC) within ``[from_date, to_date]`` (inclusive).

    ``busy`` are UTC intervals already booked or blocked (without their own buffers); the event's
    buffers are applied here. ``now`` must be timezone-aware UTC.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if event.duration <= timedelta():
        raise ValueError("event.duration must be positive")
    if event.slot_interval <= timedelta():
        raise ValueError("event.slot_interval must be positive")

    tz = ZoneInfo(schedule.timezone)
    earliest_start = now + event.min_notice
    inflated_busy = [
        TimeRange(b.start - event.buffer_after, b.end + event.buffer_before) for b in busy
    ]

    slots: list[TimeRange] = []
    day = from_date
    while day <= to_date:
        working = _working_ranges(day, schedule, tz)
        if working:
            free = subtract_all(working, inflated_busy)
            day_slots = _slice_day(working, free, event, earliest_start)
            if event.max_per_day is not None:
                day_slots = day_slots[: event.max_per_day]
            slots.extend(day_slots)
        day += timedelta(days=1)

    slots.sort()
    return slots


def _working_ranges(day: date, schedule: Schedule, tz: ZoneInfo) -> list[TimeRange]:
    """Concrete UTC working intervals for a single day, after overrides."""
    windows = _local_windows(day, schedule)
    ranges: list[TimeRange] = []
    for start_t, end_t in windows:
        materialized = _materialize(day, start_t, end_t, tz)
        if materialized is not None:
            ranges.append(materialized)
    ranges.sort()
    return ranges


def _local_windows(day: date, schedule: Schedule) -> list[tuple[time, time]]:
    override = next((o for o in schedule.overrides if o.day == day), None)
    if override is not None:
        if not override.is_available:
            return []
        if override.start is not None and override.end is not None:
            return [(override.start, override.end)]
        # Available with no explicit times → use the weekly rules.
    return [(r.start, r.end) for r in schedule.rules if r.weekday == day.weekday()]


def _materialize(day: date, start_t: time, end_t: time, tz: ZoneInfo) -> TimeRange | None:
    """Convert a local wall-clock window on ``day`` to a UTC interval.

    Uses ``replace(tzinfo=tz)`` (correct for zoneinfo) so the offset is resolved for that exact
    date — this is where DST is handled. Ambiguous/nonexistent local times (the DST transition
    hour) resolve deterministically via ``fold=0``; business-hours windows never touch them.
    """
    start_local = datetime.combine(day, start_t).replace(tzinfo=tz)
    end_local = datetime.combine(day, end_t).replace(tzinfo=tz)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    if start_utc >= end_utc:
        return None
    return TimeRange(start_utc, end_utc)


def _slice_day(
    working: list[TimeRange],
    free: list[TimeRange],
    event: EventType,
    earliest_start: datetime,
) -> list[TimeRange]:
    """Slice working windows into duration slots on the slot_interval grid.

    The grid is anchored at each working window's start, so the slot times stay stable regardless
    of where busy blocks fall. A slot is kept only if it fits entirely within a free interval and
    starts no earlier than ``earliest_start``.
    """
    out: list[TimeRange] = []
    for window in working:
        start = window.start
        while start + event.duration <= window.end:
            slot = TimeRange(start, start + event.duration)
            if start >= earliest_start and any(f.contains(slot) for f in free):
                out.append(slot)
            start += event.slot_interval
    out.sort()
    return out
