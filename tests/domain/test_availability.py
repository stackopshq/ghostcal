"""Availability engine tests.

Example tests pin concrete behaviour (incl. the DST golden cases that motivate per-day
materialization); Hypothesis tests assert the invariants that must hold for every input.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ghostcal.domain.availability import (
    DateOverride,
    EventType,
    Schedule,
    WeeklyRule,
    compute_slots,
)
from ghostcal.domain.time import TimeRange

MON_9_17 = time(9, 0), time(17, 0)
DISTANT_PAST = datetime(2000, 1, 1, tzinfo=UTC)  # min_notice effectively disabled


def _schedule(day: date, tz: str = "UTC", window: tuple[time, time] = MON_9_17) -> Schedule:
    """Schedule whose single weekly rule covers ``day``'s weekday."""
    return Schedule(timezone=tz, rules=(WeeklyRule(day.weekday(), window[0], window[1]),))


def _event(**kw: object) -> EventType:
    base: dict[str, object] = {
        "duration": timedelta(minutes=60),
        "slot_interval": timedelta(minutes=30),
    }
    base.update(kw)
    return EventType(**base)  # type: ignore[arg-type]


# --- Basic slicing -------------------------------------------------------------------------


def test_full_day_no_busy() -> None:
    day = date(2026, 6, 1)
    slots = compute_slots(
        schedule=_schedule(day),
        event=_event(),
        busy=[],
        now=DISTANT_PAST,
        from_date=day,
        to_date=day,
    )
    starts = [s.start for s in slots]
    # 09:00 .. 16:00 every 30 min (16:00 + 60 = 17:00 fits; 16:30 would overflow).
    assert starts[0] == datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    assert starts[-1] == datetime(2026, 6, 1, 16, 0, tzinfo=UTC)
    assert len(slots) == 15
    assert all(s.end - s.start == timedelta(minutes=60) for s in slots)


def test_closed_on_non_matching_weekday() -> None:
    day = date(2026, 6, 1)  # rule is for this weekday
    other = date(2026, 6, 2)  # next day, different weekday, no rule
    slots = compute_slots(
        schedule=_schedule(day),
        event=_event(),
        busy=[],
        now=DISTANT_PAST,
        from_date=other,
        to_date=other,
    )
    assert slots == []


# --- Busy + buffers ------------------------------------------------------------------------


def test_busy_with_buffers_blocks_neighbourhood() -> None:
    day = date(2026, 6, 1)
    busy = [TimeRange(datetime(2026, 6, 1, 12, tzinfo=UTC), datetime(2026, 6, 1, 13, tzinfo=UTC))]
    slots = compute_slots(
        schedule=_schedule(day),
        event=_event(
            duration=timedelta(minutes=30),
            slot_interval=timedelta(minutes=30),
            buffer_before=timedelta(minutes=15),
            buffer_after=timedelta(minutes=15),
        ),
        busy=busy,
        now=DISTANT_PAST,
        from_date=day,
        to_date=day,
    )
    starts = {s.start.time() for s in slots}
    # Forbidden zone is [11:45, 13:15): 11:00 and 13:30 survive, 11:30 and 13:00 do not.
    assert time(11, 0) in starts
    assert time(13, 30) in starts
    assert time(11, 30) not in starts
    assert time(13, 0) not in starts
    forbidden = TimeRange(
        datetime(2026, 6, 1, 11, 45, tzinfo=UTC), datetime(2026, 6, 1, 13, 15, tzinfo=UTC)
    )
    assert all(not s.overlaps(forbidden) for s in slots)


# --- Notice and per-day cap ----------------------------------------------------------------


def test_min_notice_hides_imminent_slots() -> None:
    day = date(2026, 6, 1)
    now = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
    slots = compute_slots(
        schedule=_schedule(day),
        event=_event(min_notice=timedelta(hours=2)),
        busy=[],
        now=now,
        from_date=day,
        to_date=day,
    )
    assert all(s.start >= datetime(2026, 6, 1, 13, 0, tzinfo=UTC) for s in slots)


def test_max_per_day_caps_results() -> None:
    day = date(2026, 6, 1)
    slots = compute_slots(
        schedule=_schedule(day),
        event=_event(max_per_day=3),
        busy=[],
        now=DISTANT_PAST,
        from_date=day,
        to_date=day,
    )
    assert len(slots) == 3
    assert slots[0].start == datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


# --- Overrides -----------------------------------------------------------------------------


def test_override_closes_the_day() -> None:
    day = date(2026, 6, 1)
    schedule = Schedule(
        timezone="UTC",
        rules=(WeeklyRule(day.weekday(), *MON_9_17),),
        overrides=(DateOverride(day=day, is_available=False),),
    )
    slots = compute_slots(
        schedule=schedule, event=_event(), busy=[], now=DISTANT_PAST, from_date=day, to_date=day
    )
    assert slots == []


def test_override_replaces_hours() -> None:
    day = date(2026, 6, 1)
    schedule = Schedule(
        timezone="UTC",
        rules=(WeeklyRule(day.weekday(), *MON_9_17),),
        overrides=(DateOverride(day=day, is_available=True, start=time(14), end=time(16)),),
    )
    slots = compute_slots(
        schedule=schedule, event=_event(), busy=[], now=DISTANT_PAST, from_date=day, to_date=day
    )
    assert slots[0].start == datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    assert all(s.end <= datetime(2026, 6, 1, 16, 0, tzinfo=UTC) for s in slots)


# --- DST golden cases (the whole reason per-day materialization exists) ---------------------


def test_dst_offset_shifts_across_spring_forward() -> None:
    # US DST 2026 begins Sun 2026-03-08. America/New_York: EST (-5) before, EDT (-4) after.
    before = date(2026, 3, 2)  # Monday, still EST
    after = date(2026, 3, 9)  # Monday, now EDT
    schedule = Schedule(
        timezone="America/New_York",
        rules=(
            WeeklyRule(0, time(9, 0), time(17, 0)),  # Monday 09:00 local
        ),
    )
    event = _event(duration=timedelta(minutes=60), slot_interval=timedelta(minutes=60))

    s_before = compute_slots(
        schedule=schedule,
        event=event,
        busy=[],
        now=DISTANT_PAST,
        from_date=before,
        to_date=before,
    )
    s_after = compute_slots(
        schedule=schedule,
        event=event,
        busy=[],
        now=DISTANT_PAST,
        from_date=after,
        to_date=after,
    )
    # 09:00 local maps to 14:00 UTC under EST, 13:00 UTC under EDT.
    assert s_before[0].start == datetime(2026, 3, 2, 14, 0, tzinfo=UTC)
    assert s_after[0].start == datetime(2026, 3, 9, 13, 0, tzinfo=UTC)


def test_half_hour_offset_timezone() -> None:
    # Asia/Kolkata is UTC+5:30 year-round.
    day = date(2026, 6, 1)
    schedule = Schedule(
        timezone="Asia/Kolkata",
        rules=(WeeklyRule(day.weekday(), time(9, 0), time(17, 0)),),
    )
    slots = compute_slots(
        schedule=schedule,
        event=_event(slot_interval=timedelta(minutes=60)),
        busy=[],
        now=DISTANT_PAST,
        from_date=day,
        to_date=day,
    )
    # 09:00 +05:30 == 03:30 UTC.
    assert slots[0].start == datetime(2026, 6, 1, 3, 30, tzinfo=UTC)


# --- Validation guards ---------------------------------------------------------------------


def test_rejects_naive_now() -> None:
    day = date(2026, 6, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_slots(
            schedule=_schedule(day),
            event=_event(),
            busy=[],
            now=datetime(2026, 6, 1, 9, 0),  # intentionally naive
            from_date=day,
            to_date=day,
        )


def test_rejects_non_positive_duration_and_interval() -> None:
    day = date(2026, 6, 1)
    with pytest.raises(ValueError, match="duration"):
        compute_slots(
            schedule=_schedule(day),
            event=_event(duration=timedelta()),
            busy=[],
            now=DISTANT_PAST,
            from_date=day,
            to_date=day,
        )
    with pytest.raises(ValueError, match="slot_interval"):
        compute_slots(
            schedule=_schedule(day),
            event=_event(slot_interval=timedelta()),
            busy=[],
            now=DISTANT_PAST,
            from_date=day,
            to_date=day,
        )


def test_override_with_inverted_hours_yields_nothing() -> None:
    day = date(2026, 6, 1)
    schedule = Schedule(
        timezone="UTC",
        rules=(WeeklyRule(day.weekday(), *MON_9_17),),
        overrides=(DateOverride(day=day, is_available=True, start=time(16), end=time(14)),),
    )
    slots = compute_slots(
        schedule=schedule, event=_event(), busy=[], now=DISTANT_PAST, from_date=day, to_date=day
    )
    assert slots == []


# --- Invariants over arbitrary inputs ------------------------------------------------------

_TZS = ["UTC", "Europe/Zurich", "America/New_York", "Asia/Kolkata", "Pacific/Chatham"]


@settings(max_examples=200)
@given(
    tz=st.sampled_from(_TZS),
    start_h=st.integers(min_value=0, max_value=20),
    span_h=st.integers(min_value=1, max_value=4),
    dur_min=st.sampled_from([15, 30, 45, 60]),
    step_min=st.sampled_from([15, 30, 60]),
    day_offset=st.integers(min_value=0, max_value=300),
)
def test_invariants(
    tz: str, start_h: int, span_h: int, dur_min: int, step_min: int, day_offset: int
) -> None:
    day = date(2026, 1, 1) + timedelta(days=day_offset)
    window = (time(start_h, 0), time(min(start_h + span_h, 23), 30))
    schedule = _schedule(day, tz=tz, window=window)
    event = _event(duration=timedelta(minutes=dur_min), slot_interval=timedelta(minutes=step_min))
    busy = [
        TimeRange(
            datetime.combine(day, time(12, 0), tzinfo=UTC),
            datetime.combine(day, time(13, 0), tzinfo=UTC),
        )
    ]
    slots = compute_slots(
        schedule=schedule,
        event=event,
        busy=busy,
        now=DISTANT_PAST,
        from_date=day,
        to_date=day,
    )
    for slot in slots:
        # Correct duration, timezone-aware, and never overlapping busy.
        assert slot.end - slot.start == timedelta(minutes=dur_min)
        assert slot.start.tzinfo is not None
        assert not slot.overlaps(busy[0])
    # Slots are sorted and non-decreasing.
    assert slots == sorted(slots)
