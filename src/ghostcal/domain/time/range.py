"""Half-open, timezone-aware time intervals and interval arithmetic.

A ``TimeRange`` is the half-open interval ``[start, end)`` of two timezone-aware instants.
Half-open is deliberate: it makes back-to-back ranges (``a.end == b.start``) *not* overlap,
which is exactly the semantics we want for adjacent calendar slots.

This module is the arithmetic core of the availability engine: free time is computed by
subtracting busy ranges (bookings + external calendar blocks, already inflated by buffers)
from working ranges. It is pure and has no notion of "now".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, order=True)
class TimeRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("TimeRange requires timezone-aware datetimes")
        if self.start >= self.end:
            raise ValueError(f"TimeRange start must be < end (got {self.start!r}, {self.end!r})")

    def overlaps(self, other: TimeRange) -> bool:
        """True if the two half-open intervals share any instant."""
        return self.start < other.end and other.start < self.end

    def contains(self, other: TimeRange) -> bool:
        return self.start <= other.start and other.end <= self.end

    def difference(self, busy: Iterable[TimeRange]) -> list[TimeRange]:
        """Return the parts of this range not covered by any ``busy`` range.

        Produces zero, one, or many disjoint sub-ranges in chronological order.
        """
        free = [self]
        for b in sorted(busy):
            next_free: list[TimeRange] = []
            for r in free:
                if not r.overlaps(b):
                    next_free.append(r)
                    continue
                # Keep the slice before the busy block, if any.
                if r.start < b.start:
                    next_free.append(TimeRange(r.start, b.start))
                # Keep the slice after the busy block, if any.
                if b.end < r.end:
                    next_free.append(TimeRange(b.end, r.end))
            free = next_free
        return free


def merge(ranges: Iterable[TimeRange]) -> list[TimeRange]:
    """Collapse overlapping and touching ranges into the fewest disjoint ones that cover the same
    instants.

    Two reasons, and the second is the one that matters. It is tidier — and it is what a free-busy
    view must publish, because the *shape* of unmerged blocks is itself information: three meetings
    stacked on one hour say something about how in demand you are that a single "busy" does not.
    Merging discloses that you are occupied, and nothing beyond it.

    Touching ranges (``a.end == b.start``) are merged too. They do not overlap — half-open intervals
    are deliberate — but as busy time they are one uninterrupted stretch, and reporting them
    separately would say "there is a seam here", which is again more than "busy".
    """
    out: list[TimeRange] = []
    for r in sorted(ranges):
        if out and r.start <= out[-1].end:
            if r.end > out[-1].end:
                out[-1] = TimeRange(out[-1].start, r.end)
        else:
            out.append(r)
    return out


def subtract_all(working: Iterable[TimeRange], busy: Iterable[TimeRange]) -> list[TimeRange]:
    """Subtract every ``busy`` range from every ``working`` range.

    Returns the resulting free ranges in chronological order. This is the operation that turns
    "host is available 9-17" minus "meetings + external events" into bookable gaps.
    """
    busy_list = list(busy)
    result: list[TimeRange] = []
    for w in working:
        result.extend(w.difference(busy_list))
    result.sort()
    return result
