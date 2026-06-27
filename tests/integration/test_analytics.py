"""Analytics aggregation against a live PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.analytics_repository import SqlAnalyticsRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration


def _booking(org, event, host, start, status):  # type: ignore[no-untyped-def]
    return models.Booking(
        organization_id=org,
        event_type_id=event,
        host_id=host,
        invitee_name="X",
        invitee_email="x@example.com",
        invitee_timezone="UTC",
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status=status,
    )


async def test_analytics_summary(admin_engine: AsyncEngine) -> None:
    org_id = host = None
    now = datetime.now(UTC)
    try:
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            org = models.Organization(name="An Org", slug=f"an-{uuid.uuid4().hex[:8]}")
            host_user = models.User(
                email=f"h-{uuid.uuid4().hex[:8]}@example.com", name="H", timezone="UTC"
            )
            db.add_all([org, host_user])
            await db.flush()
            org_id, host = org.id, host_user.id
            event = models.EventType(
                organization_id=org_id,
                owner_id=host,
                slug=f"e-{uuid.uuid4().hex[:6]}",
                title="Intro",
                duration_min=30,
            )
            db.add(event)
            await db.flush()
            db.add_all(
                [
                    _booking(org_id, event.id, host, now + timedelta(days=2), "confirmed"),
                    _booking(org_id, event.id, host, now + timedelta(days=5), "confirmed"),
                    _booking(org_id, event.id, host, now - timedelta(days=3), "confirmed"),
                    _booking(org_id, event.id, host, now + timedelta(days=4), "cancelled"),
                ]
            )
            await db.commit()

        async with org_session(org_id) as session:
            summary = await SqlAnalyticsRepository(session, org_id).summary(now)

        assert summary.total_bookings == 3
        assert summary.upcoming_bookings == 2
        assert summary.cancellations_last_30_days == 1
        assert summary.by_event_type[0].title == "Intro"
        assert summary.by_event_type[0].count == 3
        assert len(summary.daily) == 3  # the three confirmed, distinct days within the window
    finally:
        if org_id is not None:
            async with async_sessionmaker(admin_engine)() as db:
                await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                if host is not None:
                    await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": host})
                await db.commit()
