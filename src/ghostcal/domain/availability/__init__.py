"""Availability engine: turn schedules + busy time into bookable slots."""

from ghostcal.domain.availability.engine import (
    DateOverride,
    EventType,
    Schedule,
    WeeklyRule,
    compute_slots,
)

__all__ = [
    "DateOverride",
    "EventType",
    "Schedule",
    "WeeklyRule",
    "compute_slots",
]
