"""Group event type against a live PostgreSQL: many invitees per slot, up to capacity."""

from __future__ import annotations

import uuid
from datetime import time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.ports.clock import SystemClock
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

_CLOCK = SystemClock()


def _repo(session: object, org_id: uuid.UUID) -> SqlSchedulingRepository:
    return SqlSchedulingRepository(session, org_id)  # type: ignore[arg-type]


def _request(event_id: uuid.UUID, start: object, who: str) -> BookingRequest:
    return BookingRequest(
        event_type_id=event_id,
        start_at=start,  # type: ignore[arg-type]
        invitee_name=who,
        invitee_email=f"{who}@example.com",
        invitee_timezone="UTC",
    )


async def test_group_fills_to_capacity_then_closes(admin_engine: AsyncEngine) -> None:
    org_id = host = None
    try:
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            org = models.Organization(name="Grp Org", slug=f"grp-{uuid.uuid4().hex[:8]}")
            host_user = models.User(
                email=f"host-{uuid.uuid4().hex[:8]}@example.com", name="Host", timezone="UTC"
            )
            db.add_all([org, host_user])
            await db.flush()
            org_id, host = org.id, host_user.id
            db.add(models.Membership(organization_id=org_id, user_id=host, role="owner"))
            schedule = models.AvailabilitySchedule(
                organization_id=org_id, owner_id=host, name="Work", timezone="UTC"
            )
            db.add(schedule)
            await db.flush()
            for weekday in range(7):
                db.add(
                    models.AvailabilityRule(
                        organization_id=org_id,
                        schedule_id=schedule.id,
                        weekday=weekday,
                        start_time=time(9, 0),
                        end_time=time(17, 0),
                    )
                )
            event = models.EventType(
                organization_id=org_id,
                owner_id=host,
                slug=f"grp-{uuid.uuid4().hex[:6]}",
                title="Webinar",
                duration_min=30,
                slot_interval_min=30,
                kind="group",
                capacity=2,
            )
            db.add(event)
            await db.flush()
            event_id = event.id
            await db.commit()

        target = _CLOCK.now().date() + timedelta(days=2)
        async with org_session(org_id) as session:
            slots = await get_availability(
                _repo(session, org_id),
                _CLOCK,
                event_type_id=event_id,
                from_date=target,
                to_date=target,
            )
        assert slots
        slot = slots[0].start

        # Two invitees can take the same slot (capacity 2).
        async with org_session(org_id) as session:
            await create_booking(_repo(session, org_id), _CLOCK, _request(event_id, slot, "one"))
        async with org_session(org_id) as session:
            await create_booking(_repo(session, org_id), _CLOCK, _request(event_id, slot, "two"))

        # The third is rejected (slot full).
        with pytest.raises(SlotUnavailable):
            async with org_session(org_id) as session:
                await create_booking(
                    _repo(session, org_id), _CLOCK, _request(event_id, slot, "three")
                )

        # The full slot is no longer offered.
        async with org_session(org_id) as session:
            slots2 = await get_availability(
                _repo(session, org_id),
                _CLOCK,
                event_type_id=event_id,
                from_date=target,
                to_date=target,
            )
        assert all(s.start != slot for s in slots2)

        # Group bookings don't block the host (blocks_host = false).
        async with async_sessionmaker(admin_engine)() as db:
            blocking = (
                await db.execute(
                    text("SELECT count(*) FROM bookings WHERE event_type_id = :e AND blocks_host"),
                    {"e": event_id},
                )
            ).scalar()
        assert blocking == 0
    finally:
        if org_id is not None:
            async with async_sessionmaker(admin_engine)() as db:
                await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                if host is not None:
                    await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": host})
                await db.commit()
