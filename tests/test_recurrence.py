"""Unit tests for the pure recurrence engine (no DB), including a DST-boundary golden case."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ghostcal.domain.calendar import Occurrence, RecurringEvent, expand

ZURICH = ZoneInfo("Europe/Zurich")


def _ev(**kw: object) -> RecurringEvent:
    base: dict[str, object] = {
        "id": "e1",
        "start_at": datetime(2026, 3, 23, 8, 0, tzinfo=UTC),  # 09:00 Europe/Zurich (UTC+1)
        "end_at": datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
        "timezone": "Europe/Zurich",
    }
    base.update(kw)
    return RecurringEvent(**base)  # type: ignore[arg-type]


def test_single_event_in_window() -> None:
    ev = _ev()
    occ = expand(ev, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC))
    assert occ == [
        Occurrence(
            event_id="e1",
            start=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),
            end=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            all_day=False,
        )
    ]


def test_single_event_outside_window() -> None:
    ev = _ev()
    assert expand(ev, datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC)) == []


def test_weekly_recurrence_is_dst_correct() -> None:
    # "Every Monday 09:00 Europe/Zurich" across the 2026-03-29 spring-forward (UTC+1 → UTC+2).
    ev = _ev(rrule="FREQ=WEEKLY;BYDAY=MO")
    occ = expand(ev, datetime(2026, 3, 20, tzinfo=UTC), datetime(2026, 4, 7, tzinfo=UTC))
    starts = [o.start for o in occ]
    assert starts == [
        datetime(2026, 3, 23, 8, 0, tzinfo=UTC),  # before DST: 09:00 local = 08:00 UTC
        datetime(2026, 3, 30, 7, 0, tzinfo=UTC),  # after DST:  09:00 local = 07:00 UTC
        datetime(2026, 4, 6, 7, 0, tzinfo=UTC),
    ]
    # Wall-clock time is a stable 09:00 local on every occurrence.
    assert {o.start.astimezone(ZURICH).hour for o in occ} == {9}


def test_exdate_excludes_occurrence() -> None:
    ev = _ev(
        rrule="FREQ=WEEKLY;BYDAY=MO",
        exdates=(datetime(2026, 3, 30, 7, 0, tzinfo=UTC),),
    )
    occ = expand(ev, datetime(2026, 3, 20, tzinfo=UTC), datetime(2026, 4, 7, tzinfo=UTC))
    starts = [o.start for o in occ]
    assert datetime(2026, 3, 30, 7, 0, tzinfo=UTC) not in starts
    assert len(starts) == 2


def test_count_limited_rule() -> None:
    ev = _ev(rrule="FREQ=DAILY;COUNT=3")
    occ = expand(ev, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC))
    assert len(occ) == 3


def test_occurrence_started_before_window_but_overlaps() -> None:
    # A 2-hour event at 23:30 UTC whose window starts at 00:00 the next day still overlaps.
    ev = _ev(
        start_at=datetime(2026, 3, 23, 23, 30, tzinfo=UTC),
        end_at=datetime(2026, 3, 24, 1, 30, tzinfo=UTC),
        rrule="FREQ=DAILY",
    )
    occ = expand(
        ev, datetime(2026, 3, 24, 0, 0, tzinfo=UTC), datetime(2026, 3, 24, 12, 0, tzinfo=UTC)
    )
    assert any(o.start == datetime(2026, 3, 23, 23, 30, tzinfo=UTC) for o in occ)
