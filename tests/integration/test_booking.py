"""Booking flow against a live PostgreSQL: availability → book → slot disappears → no double book.

Seeding uses the admin connection (ORM, RLS-bypassing). The use cases run through ``org_session``
(the non-BYPASSRLS application role), exercising RLS, the advisory lock and the EXCLUDE constraint.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.ports.clock import FixedClock
from ghostcal.application.scheduling import (
    BookingRequest,
    SlotUnavailable,
    create_booking,
    get_availability,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

DAY = date(2027, 6, 7)
FIRST_SLOT = datetime.combine(DAY, time(9, 0), tzinfo=UTC)
CLOCK = FixedClock(datetime(2000, 1, 1, tzinfo=UTC))  # far in the past → nothing filtered


@pytest_asyncio.fixture
async def bookable(admin_engine: AsyncEngine) -> AsyncIterator[dict[str, uuid.UUID]]:
    """Seed one org with a host, a 09:00-17:00 schedule on DAY, and a 30-min event type."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"org-{suffix}")
        host = models.User(email=f"host-{suffix}@example.test", name="Host", timezone="UTC")
        s.add_all([org, host])
        await s.flush()
        schedule = models.AvailabilitySchedule(
            organization_id=org.id, owner_id=host.id, name="Default", timezone="UTC"
        )
        s.add(schedule)
        await s.flush()
        s.add(
            models.AvailabilityRule(
                organization_id=org.id,
                schedule_id=schedule.id,
                weekday=DAY.weekday(),
                start_time=time(9, 0),
                end_time=time(17, 0),
            )
        )
        event = models.EventType(
            organization_id=org.id,
            owner_id=host.id,
            schedule_id=schedule.id,
            slug=f"intro-{suffix}",
            title="Intro",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event)
        await s.commit()
        ids = {"org": org.id, "host": host.id, "event": event.id}

    try:
        yield ids
    finally:
        async with maker() as s:
            await s.delete(await s.get(models.Organization, ids["org"]))
            await s.delete(await s.get(models.User, ids["host"]))
            await s.commit()


def _repo(session: object, org: uuid.UUID) -> SqlSchedulingRepository:
    return SqlSchedulingRepository(session, org)  # type: ignore[arg-type]


async def test_availability_then_book_then_slot_gone(bookable: dict[str, uuid.UUID]) -> None:
    org, event = bookable["org"], bookable["event"]

    async with org_session(org) as session:
        slots = await get_availability(
            _repo(session, org), CLOCK, event_type_id=event, from_date=DAY, to_date=DAY
        )
    assert slots[0].start == FIRST_SLOT

    async with org_session(org) as session:
        confirmation = await create_booking(
            _repo(session, org),
            CLOCK,
            BookingRequest(event, FIRST_SLOT, "Invitee", "inv@example.test", "UTC"),
        )
    assert confirmation.start_at == FIRST_SLOT
    assert confirmation.end_at == FIRST_SLOT + timedelta(minutes=30)

    async with org_session(org) as session:
        after = await get_availability(
            _repo(session, org), CLOCK, event_type_id=event, from_date=DAY, to_date=DAY
        )
    assert all(slot.start != FIRST_SLOT for slot in after)


async def test_unoffered_start_is_rejected(bookable: dict[str, uuid.UUID]) -> None:
    org, event = bookable["org"], bookable["event"]
    off_grid = datetime.combine(DAY, time(9, 7), tzinfo=UTC)  # not on the 30-min grid
    with pytest.raises(SlotUnavailable):
        async with org_session(org) as session:
            await create_booking(
                _repo(session, org),
                CLOCK,
                BookingRequest(event, off_grid, "Invitee", "inv@example.test", "UTC"),
            )


async def test_double_booking_rejected_by_constraint(bookable: dict[str, uuid.UUID]) -> None:
    org, event = bookable["org"], bookable["event"]
    end = FIRST_SLOT + timedelta(minutes=30)

    async with org_session(org) as session:
        repo = _repo(session, org)
        context = await repo.get_event_context(event)
        assert context is not None
        await repo.insert_booking(
            context=context,
            start_at=FIRST_SLOT,
            end_at=end,
            invitee_name="First",
            invitee_email="first@example.test",
            invitee_timezone="UTC",
        )

    # A second confirmed booking for the same host/slot must hit the EXCLUDE constraint.
    with pytest.raises(SlotUnavailable):
        async with org_session(org) as session:
            repo = _repo(session, org)
            context = await repo.get_event_context(event)
            assert context is not None
            await repo.insert_booking(
                context=context,
                start_at=FIRST_SLOT,
                end_at=end,
                invitee_name="Second",
                invitee_email="second@example.test",
                invitee_timezone="UTC",
            )
