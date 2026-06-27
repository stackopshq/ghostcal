"""Invitee self-service (view/cancel/reschedule) against a live PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.manage import (
    cancel_booking,
    get_booking,
    reschedule_booking,
)
from ghostcal.application.ports.clock import FixedClock
from ghostcal.application.scheduling import BookingRequest, create_booking, get_availability
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.manage_repository import SqlBookingManageRepository
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

DAY = date(2031, 6, 2)
FIRST = datetime.combine(DAY, time(9, 0), tzinfo=UTC)
SECOND = datetime.combine(DAY, time(9, 30), tzinfo=UTC)
CLOCK = FixedClock(datetime(2000, 1, 1, tzinfo=UTC))


@pytest_asyncio.fixture
async def booked(admin_engine: AsyncEngine) -> AsyncIterator[dict[str, uuid.UUID]]:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"org-{suffix}")
        host = models.User(email=f"h-{suffix}@example.com", name="Host", timezone="UTC")
        s.add_all([org, host])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=host.id, role="owner"))
        schedule = models.AvailabilitySchedule(
            organization_id=org.id, owner_id=host.id, name="Hours", timezone="UTC"
        )
        s.add(schedule)
        await s.flush()
        s.add_all(
            models.AvailabilityRule(
                organization_id=org.id,
                schedule_id=schedule.id,
                weekday=wd,
                start_time=time(9, 0),
                end_time=time(17, 0),
            )
            for wd in range(7)
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

    async with org_session(ids["org"]) as session:
        repo = SqlSchedulingRepository(session, ids["org"])
        confirmation = await create_booking(
            repo,
            CLOCK,
            BookingRequest(ids["event"], FIRST, "Alice", "alice@example.com", "UTC"),
        )
    ids["booking"] = confirmation.booking_id

    try:
        yield ids
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": ids["org"]})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids["host"]})
            await s.commit()


async def test_view_and_cancel(booked: dict[str, uuid.UUID]) -> None:
    org, booking = booked["org"], booked["booking"]
    async with org_session(org) as session:
        repo = SqlBookingManageRepository(session, org)
        detail = await get_booking(repo, booking)
        assert detail.status == "confirmed"
        assert detail.event_title == "Intro"
        assert detail.invitee_name == "Alice"

    async with org_session(org) as session:
        repo = SqlBookingManageRepository(session, org)
        cancelled = await cancel_booking(repo, booking)
        assert cancelled.status == "cancelled"

    async with org_session(org) as session:
        repo = SqlBookingManageRepository(session, org)
        assert (await get_booking(repo, booking)).status == "cancelled"


async def test_reschedule_frees_old_takes_new(booked: dict[str, uuid.UUID]) -> None:
    org, booking, event = booked["org"], booked["booking"], booked["event"]

    async with org_session(org) as session:
        manage_repo = SqlBookingManageRepository(session, org)
        scheduling_repo = SqlSchedulingRepository(session, org)
        _, confirmation = await reschedule_booking(
            manage_repo, scheduling_repo, CLOCK, booking_id=booking, new_start=SECOND
        )
    assert confirmation.start_at == SECOND

    async with org_session(org) as session:
        manage_repo = SqlBookingManageRepository(session, org)
        assert (await get_booking(manage_repo, booking)).status == "cancelled"

    async with org_session(org) as session:
        scheduling_repo = SqlSchedulingRepository(session, org)
        slots = await get_availability(
            scheduling_repo, CLOCK, event_type_id=event, from_date=DAY, to_date=DAY
        )
        starts = {s.start for s in slots}
    assert FIRST in starts  # the old slot is free again
    assert SECOND not in starts  # the new slot is taken
