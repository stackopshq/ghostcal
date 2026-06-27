"""Round-robin event type against a live PostgreSQL: union availability + load-balanced hosts."""

from __future__ import annotations

import uuid
from datetime import time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.scheduling import BookingRequest, create_booking, get_availability
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

_CLOCK = SystemClock()


def _repo(session: object, org_id: uuid.UUID) -> SqlSchedulingRepository:
    return SqlSchedulingRepository(session, org_id)  # type: ignore[arg-type]


async def _seed_host_with_schedule(db: object, org_id: uuid.UUID, label: str) -> uuid.UUID:
    user = models.User(
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.com", name=label, timezone="UTC"
    )
    db.add(user)  # type: ignore[attr-defined]
    await db.flush()  # type: ignore[attr-defined]
    db.add(models.Membership(organization_id=org_id, user_id=user.id, role="member"))  # type: ignore[attr-defined]
    schedule = models.AvailabilitySchedule(
        organization_id=org_id, owner_id=user.id, name="Work", timezone="UTC"
    )
    db.add(schedule)  # type: ignore[attr-defined]
    await db.flush()  # type: ignore[attr-defined]
    for weekday in range(7):
        db.add(  # type: ignore[attr-defined]
            models.AvailabilityRule(
                organization_id=org_id,
                schedule_id=schedule.id,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(17, 0),
            )
        )
    return user.id


async def test_round_robin_unions_and_balances(admin_engine: AsyncEngine) -> None:
    org_id = host_a = host_b = None
    try:
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            org = models.Organization(name="RR Org", slug=f"rr-{uuid.uuid4().hex[:8]}")
            db.add(org)
            await db.flush()
            org_id = org.id
            host_a = await _seed_host_with_schedule(db, org_id, "Alice")
            host_b = await _seed_host_with_schedule(db, org_id, "Bob")
            event = models.EventType(
                organization_id=org_id,
                owner_id=host_a,
                slug=f"rr-{uuid.uuid4().hex[:6]}",
                title="Team Call",
                duration_min=30,
                kind="round_robin",
            )
            db.add(event)
            await db.flush()
            event_id = event.id
            db.add_all(
                [
                    models.EventTypeHost(
                        organization_id=org_id, event_type_id=event_id, user_id=host_a
                    ),
                    models.EventTypeHost(
                        organization_id=org_id, event_type_id=event_id, user_id=host_b
                    ),
                ]
            )
            await db.commit()

        # Availability is the union of both hosts (identical schedules here → plenty of slots).
        target = _CLOCK.now().date() + timedelta(days=2)
        async with org_session(org_id) as session:
            slots = await get_availability(
                _repo(session, org_id),
                _CLOCK,
                event_type_id=event_id,
                from_date=target,
                to_date=target,
            )
        assert len(slots) >= 2

        # First booking: hosts tied at load 0 → primary (Alice). Second distinct slot: Alice now
        # has load 1 → Bob. So the two bookings land on different hosts (load balancing).
        async with org_session(org_id) as session:
            conf1 = await create_booking(
                _repo(session, org_id),
                _CLOCK,
                BookingRequest(
                    event_type_id=event_id,
                    start_at=slots[0].start,
                    invitee_name="One",
                    invitee_email="one@example.com",
                    invitee_timezone="UTC",
                ),
            )
        async with org_session(org_id) as session:
            conf2 = await create_booking(
                _repo(session, org_id),
                _CLOCK,
                BookingRequest(
                    event_type_id=event_id,
                    start_at=slots[1].start,
                    invitee_name="Two",
                    invitee_email="two@example.com",
                    invitee_timezone="UTC",
                ),
            )
        assert conf1.host_id == host_a
        assert conf2.host_id == host_b
    finally:
        if org_id is not None:
            async with async_sessionmaker(admin_engine)() as db:
                await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                for uid in (host_a, host_b):
                    if uid is not None:
                        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
                await db.commit()
