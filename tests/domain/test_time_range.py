"""Tests for interval arithmetic — the seed of the availability-engine test suite.

The example tests pin concrete behaviour; the Hypothesis tests assert the *invariants* that
must hold for every input, which is where timezone/interval bugs actually hide.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ghostcal.domain.time import TimeRange, merge, subtract_all


def _utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


# --- Construction --------------------------------------------------------------------------


def test_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeRange(datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10))


def test_rejects_empty_or_inverted_range() -> None:
    with pytest.raises(ValueError, match="start must be"):
        TimeRange(_utc(2026, 1, 1, 10), _utc(2026, 1, 1, 10))


# --- Overlap semantics (half-open) ---------------------------------------------------------


def test_adjacent_ranges_do_not_overlap() -> None:
    a = TimeRange(_utc(2026, 1, 1, 9), _utc(2026, 1, 1, 10))
    b = TimeRange(_utc(2026, 1, 1, 10), _utc(2026, 1, 1, 11))
    assert not a.overlaps(b)


# --- difference / subtract_all -------------------------------------------------------------


def test_busy_block_punches_a_hole() -> None:
    work = TimeRange(_utc(2026, 1, 1, 9), _utc(2026, 1, 1, 17))
    lunch = TimeRange(_utc(2026, 1, 1, 12), _utc(2026, 1, 1, 13))
    assert work.difference([lunch]) == [
        TimeRange(_utc(2026, 1, 1, 9), _utc(2026, 1, 1, 12)),
        TimeRange(_utc(2026, 1, 1, 13), _utc(2026, 1, 1, 17)),
    ]


def test_fully_covered_range_yields_nothing() -> None:
    work = TimeRange(_utc(2026, 1, 1, 9), _utc(2026, 1, 1, 17))
    assert work.difference([TimeRange(_utc(2026, 1, 1, 8), _utc(2026, 1, 1, 18))]) == []


# --- Invariants over arbitrary inputs ------------------------------------------------------

_instants = st.integers(min_value=0, max_value=48).map(
    lambda h: _utc(2026, 1, 1) + timedelta(minutes=30 * h)
)


@st.composite
def _ranges(draw: st.DrawFn) -> TimeRange:
    a, b = sorted(draw(st.tuples(_instants, _instants)))
    if a == b:
        b = b + timedelta(minutes=30)
    return TimeRange(a, b)


@given(work=_ranges(), busy=st.lists(_ranges(), max_size=6))
def test_free_time_never_overlaps_busy(work: TimeRange, busy: list[TimeRange]) -> None:
    for free in work.difference(busy):
        assert work.contains(free)
        for b in busy:
            assert not free.overlaps(b)


@given(work=_ranges(), busy=st.lists(_ranges(), max_size=6))
def test_results_are_ordered_and_disjoint(work: TimeRange, busy: list[TimeRange]) -> None:
    free = subtract_all([work], busy)
    for earlier, later in pairwise(free):
        assert earlier.end <= later.start


def test_merge_collapses_overlapping_and_touching_ranges() -> None:
    """What a free-busy view publishes. The shape of unmerged blocks is itself information: three
    meetings stacked on one hour say how in demand you are; one "busy" block does not."""
    stacked = [
        TimeRange(_utc(2027, 6, 7, 9), _utc(2027, 6, 7, 10)),
        TimeRange(_utc(2027, 6, 7, 9, 30), _utc(2027, 6, 7, 11)),  # overlaps the first
        TimeRange(
            _utc(2027, 6, 7, 11), _utc(2027, 6, 7, 12)
        ),  # merely touches — but it is the same unbroken stretch
        TimeRange(_utc(2027, 6, 7, 14), _utc(2027, 6, 7, 15)),  # a real gap before this one
    ]
    assert merge(stacked) == [
        TimeRange(_utc(2027, 6, 7, 9), _utc(2027, 6, 7, 12)),
        TimeRange(_utc(2027, 6, 7, 14), _utc(2027, 6, 7, 15)),
    ]


def test_merge_swallows_a_range_contained_in_another() -> None:
    # A short meeting inside a long one must not reopen the long one's tail.
    assert merge(
        [
            TimeRange(_utc(2027, 6, 7, 9), _utc(2027, 6, 7, 17)),
            TimeRange(_utc(2027, 6, 7, 10), _utc(2027, 6, 7, 11)),
        ]
    ) == [TimeRange(_utc(2027, 6, 7, 9), _utc(2027, 6, 7, 17))]


def test_merge_of_nothing_is_nothing() -> None:
    assert merge([]) == []
