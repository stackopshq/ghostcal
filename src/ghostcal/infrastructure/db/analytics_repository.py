"""SQL implementation of the analytics repository (org-scoped via RLS / org_session)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.analytics import (
    AnalyticsRepository,
    AnalyticsSummary,
    DayCount,
    EventTypeCount,
)


class SqlAnalyticsRepository(AnalyticsRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def _scalar(self, sql: str, params: dict[str, object]) -> int:
        return int((await self._session.execute(text(sql), params)).scalar_one())

    async def summary(self, now: datetime) -> AnalyticsSummary:
        cutoff = now - timedelta(days=30)
        total = await self._scalar("SELECT count(*) FROM bookings WHERE status = 'confirmed'", {})
        upcoming = await self._scalar(
            "SELECT count(*) FROM bookings WHERE status = 'confirmed' AND start_at > :now",
            {"now": now},
        )
        last30 = await self._scalar(
            "SELECT count(*) FROM bookings WHERE status = 'confirmed' AND created_at >= :c",
            {"c": cutoff},
        )
        cancels = await self._scalar(
            "SELECT count(*) FROM bookings WHERE status = 'cancelled' AND start_at >= :c",
            {"c": cutoff},
        )

        by_event_rows = (
            await self._session.execute(
                text(
                    "SELECT et.title AS title, count(*) AS n "
                    "FROM bookings b JOIN event_types et ON et.id = b.event_type_id "
                    "WHERE b.status = 'confirmed' "
                    "GROUP BY et.title ORDER BY n DESC LIMIT 8"
                )
            )
        ).all()

        daily_rows = (
            await self._session.execute(
                text(
                    "SELECT (start_at AT TIME ZONE 'UTC')::date AS d, count(*) AS n "
                    "FROM bookings WHERE status = 'confirmed' "
                    "AND start_at >= :from_ AND start_at < :to_ "
                    "GROUP BY d ORDER BY d"
                ),
                {"from_": now - timedelta(days=7), "to_": now + timedelta(days=8)},
            )
        ).all()

        return AnalyticsSummary(
            total_bookings=total,
            upcoming_bookings=upcoming,
            bookings_last_30_days=last30,
            cancellations_last_30_days=cancels,
            by_event_type=[EventTypeCount(title=r.title, count=r.n) for r in by_event_rows],
            daily=[DayCount(day=r.d.isoformat(), count=r.n) for r in daily_rows],
        )
