"""Booking retention against a live PostgreSQL. See ADR-0006.

The purge is the only periodic job that destroys data, so the tests care as much about what it must
*not* touch (future bookings, organizations with no window) as about what it removes.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.retention import (
    MIN_RETENTION_DAYS,
    InvalidRetentionWindow,
    RetentionService,
    purge_expired_bookings,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.retention_repository import SqlRetentionRepository
from ghostcal.infrastructure.db.session import db_session, org_session

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
LONG_AGO = NOW - timedelta(days=400)
RECENT = NOW - timedelta(days=5)
FUTURE = NOW + timedelta(days=30)


@dataclass
class Fixture:
    org: uuid.UUID
    user: uuid.UUID
    bookings: dict[str, uuid.UUID]


def _service(session: object) -> RetentionService:
    return RetentionService(SqlRetentionRepository(session))  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def org_with_history(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """An org with an old, a recent and a future booking, and no retention window set."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"ret-{suffix}")
        user = models.User(email=f"ret-{suffix}@example.com", name="Host", timezone="UTC")
        s.add_all([org, user])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=user.id, role="owner"))
        event = models.EventType(
            organization_id=org.id,
            owner_id=user.id,
            slug=f"intro-{suffix}",
            title="Intro call",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event)
        await s.flush()

        bookings: dict[str, uuid.UUID] = {}
        for label, start in (("old", LONG_AGO), ("recent", RECENT), ("future", FUTURE)):
            booking = models.Booking(
                organization_id=org.id,
                event_type_id=event.id,
                host_id=user.id,
                invitee_email="invitee@example.com",
                invitee_timezone="UTC",
                start_at=start,
                end_at=start + timedelta(minutes=30),
                status="confirmed",
            )
            s.add(booking)
            await s.flush()
            bookings[label] = booking.id
        await s.commit()
        fixture = Fixture(org=org.id, user=user.id, bookings=bookings)
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM bookings WHERE organization_id = :o"), {"o": org.id})
            await s.execute(
                text("DELETE FROM event_types WHERE organization_id = :o"), {"o": org.id}
            )
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org.id})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": fixture.user})
            await s.commit()


async def _surviving(admin_engine: AsyncEngine, org: uuid.UUID) -> set[uuid.UUID]:
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        rows = (
            await s.execute(text("SELECT id FROM bookings WHERE organization_id = :o"), {"o": org})
        ).all()
    return {r.id for r in rows}


async def test_no_window_purges_nothing(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """The default is keep-forever. Nothing may be destroyed until someone asks for it."""
    async with db_session() as s:
        results = await purge_expired_bookings(SqlRetentionRepository(s))

    assert all(r.organization_id != org_with_history.org for r in results)
    assert await _surviving(admin_engine, org_with_history.org) == set(
        org_with_history.bookings.values()
    )


async def test_purge_removes_only_bookings_past_the_window(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    async with org_session(org_with_history.org) as s:
        await _service(s).set(org_with_history.org, 90)

    async with db_session() as s:
        results = await purge_expired_bookings(SqlRetentionRepository(s))

    purged = {r.organization_id: r.purged for r in results}
    assert purged[org_with_history.org] == 1  # the 400-day-old one, and nothing else

    surviving = await _surviving(admin_engine, org_with_history.org)
    assert org_with_history.bookings["old"] not in surviving
    assert org_with_history.bookings["recent"] in surviving
    assert org_with_history.bookings["future"] in surviving  # a future meeting is never "expired"


async def test_window_can_be_read_back_and_cleared(org_with_history: Fixture) -> None:
    async with org_session(org_with_history.org) as s:
        assert await _service(s).get(org_with_history.org) is None

    async with org_session(org_with_history.org) as s:
        assert await _service(s).set(org_with_history.org, 365) == 365
    async with org_session(org_with_history.org) as s:
        assert await _service(s).get(org_with_history.org) == 365

    async with org_session(org_with_history.org) as s:
        assert await _service(s).set(org_with_history.org, None) is None
    async with org_session(org_with_history.org) as s:
        assert await _service(s).get(org_with_history.org) is None


async def test_service_refuses_a_window_below_the_floor(org_with_history: Fixture) -> None:
    with pytest.raises(InvalidRetentionWindow):
        async with org_session(org_with_history.org) as s:
            await _service(s).set(org_with_history.org, MIN_RETENTION_DAYS - 1)


async def test_the_database_enforces_the_floor_too(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """The application guard is not the only one. A purge is irreversible; belt and braces.

    Written through the admin connection, which bypasses RLS and the service entirely — so what is
    exercised here is the check constraint alone.
    """
    maker = async_sessionmaker(admin_engine)
    with pytest.raises((IntegrityError, DBAPIError)):
        async with maker() as s:
            await s.execute(
                text("UPDATE organizations SET booking_retention_days = 1 WHERE id = :o"),
                {"o": org_with_history.org},
            )
            await s.commit()
