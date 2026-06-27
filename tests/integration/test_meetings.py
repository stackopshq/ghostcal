"""Host meetings (bookings) listing against a live PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.meetings import cancel_meeting, list_meetings
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.meetings_repository import SqlMeetingsRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

NOW = datetime(2050, 1, 1, tzinfo=UTC)
PAST = datetime(2049, 6, 1, 10, 0, tzinfo=UTC)
FUTURE = datetime(2051, 6, 1, 10, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def org_with_bookings(admin_engine: AsyncEngine) -> AsyncIterator[dict[str, uuid.UUID]]:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"org-{suffix}")
        host = models.User(email=f"h-{suffix}@example.com", name="Host", timezone="UTC")
        s.add_all([org, host])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=host.id, role="owner"))
        event = models.EventType(
            organization_id=org.id,
            owner_id=host.id,
            slug=f"intro-{suffix}",
            title="Intro call",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event)
        await s.flush()
        for start in (PAST, FUTURE):
            s.add(
                models.Booking(
                    organization_id=org.id,
                    event_type_id=event.id,
                    host_id=host.id,
                    invitee_name="Inv",
                    invitee_email="inv@example.com",
                    invitee_timezone="UTC",
                    start_at=start,
                    end_at=start + timedelta(minutes=30),
                    status="confirmed",
                )
            )
        await s.commit()
        ids = {"org": org.id, "host": host.id}
    try:
        yield ids
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": ids["org"]})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids["host"]})
            await s.commit()


async def test_upcoming_and_past(org_with_bookings: dict[str, uuid.UUID]) -> None:
    org, host = org_with_bookings["org"], org_with_bookings["host"]

    async with org_session(org) as session:
        repo = SqlMeetingsRepository(session, org)
        upcoming = await list_meetings(repo, host, upcoming=True, now=NOW)
        past = await list_meetings(repo, host, upcoming=False, now=NOW)

    assert [m.start_at for m in upcoming] == [FUTURE]
    assert [m.start_at for m in past] == [PAST]
    assert upcoming[0].event_title == "Intro call"
    assert upcoming[0].invitee_name == "Inv"


async def test_cancel_frees_the_meeting(org_with_bookings: dict[str, uuid.UUID]) -> None:
    org, host = org_with_bookings["org"], org_with_bookings["host"]
    async with org_session(org) as session:
        repo = SqlMeetingsRepository(session, org)
        upcoming = await list_meetings(repo, host, upcoming=True, now=NOW)
        await cancel_meeting(repo, upcoming[0].id, host)
        assert await list_meetings(repo, host, upcoming=True, now=NOW) == []
