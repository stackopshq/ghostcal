"""Booking analytics use case: aggregate stats for the host dashboard (org-wide)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EventTypeCount:
    title: str
    count: int


@dataclass(frozen=True, slots=True)
class DayCount:
    day: str  # ISO date (YYYY-MM-DD)
    count: int


@dataclass(frozen=True, slots=True)
class AnalyticsSummary:
    total_bookings: int
    upcoming_bookings: int
    bookings_last_30_days: int
    cancellations_last_30_days: int
    by_event_type: list[EventTypeCount] = field(default_factory=list)
    daily: list[DayCount] = field(default_factory=list)


class AnalyticsRepository:
    async def summary(self, now: datetime) -> AnalyticsSummary:
        raise NotImplementedError


async def get_analytics(repo: AnalyticsRepository, now: datetime) -> AnalyticsSummary:
    return await repo.summary(now)
