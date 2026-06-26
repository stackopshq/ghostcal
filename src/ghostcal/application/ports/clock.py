"""The clock port.

The domain never calls ``datetime.now()``. "Now" enters the system as data, through this
port, so availability computations are deterministic and trivially testable (a fixed clock in
tests, the system clock in production).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...


class SystemClock:
    """Production adapter: reads the real wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Test adapter: always returns the same instant."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._instant = instant

    def now(self) -> datetime:
        return self._instant
