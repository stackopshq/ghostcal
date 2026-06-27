"""Collective event type against a live PostgreSQL: intersection availability + linked rows."""

from __future__ import annotations

import uuid
from datetime import time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.scheduling import BookingRequest, create_booking, get_availability
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.manage_repository import SqlBookingManageRepository
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

_CLOCK = SystemClock()


def _repo(session: object, org_id: uuid.UUID) -> SqlSchedulingRepository:
    return SqlSchedulingRepository(session, org_id)  # type: ignore[arg-type]


async def _seed_host(db: object, org_id: uuid.UUID, label: str) -> uuid.UUID:
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


async def test_collective_books_all_hosts_and_cancels_together(admin_engine: AsyncEngine) -> None:
    org_id = host_a = host_b = None
    try:
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            org = models.Organization(name="Co Org", slug=f"co-{uuid.uuid4().hex[:8]}")
            db.add(org)
            await db.flush()
            org_id = org.id
            host_a = await _seed_host(db, org_id, "Alice")
            host_b = await _seed_host(db, org_id, "Bob")
            event = models.EventType(
                organization_id=org_id,
                owner_id=host_a,
                slug=f"co-{uuid.uuid4().hex[:6]}",
                title="Demo + SE",
                duration_min=30,
                slot_interval_min=30,  # non-overlapping slots
                kind="collective",
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

        # Booking creates one row per host, linked by collective_group_id, plus a co-host email.
        async with org_session(org_id) as session:
            conf = await create_booking(
                _repo(session, org_id),
                _CLOCK,
                BookingRequest(
                    event_type_id=event_id,
                    start_at=slots[0].start,
                    invitee_name="Lead",
                    invitee_email="lead@example.com",
                    invitee_timezone="UTC",
                ),
            )
        assert conf.host_id == host_a
        assert len(conf.additional_host_emails) == 1

        async with async_sessionmaker(admin_engine)() as db:
            group_rows = (
                await db.execute(
                    text(
                        "SELECT host_id, collective_group_id FROM bookings "
                        "WHERE event_type_id = :e AND status = 'confirmed'"
                    ),
                    {"e": event_id},
                )
            ).all()
        assert len(group_rows) == 2
        assert {r.host_id for r in group_rows} == {host_a, host_b}
        assert len({r.collective_group_id for r in group_rows}) == 1

        # If one host is busy, the shared slot is no longer offered (intersection).
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            db.add(
                models.Booking(
                    organization_id=org_id,
                    event_type_id=event_id,
                    host_id=host_b,
                    invitee_name="Other",
                    invitee_email="other@example.com",
                    invitee_timezone="UTC",
                    start_at=slots[1].start,
                    end_at=slots[1].end,
                    status="confirmed",
                )
            )
            await db.commit()
        async with org_session(org_id) as session:
            slots2 = await get_availability(
                _repo(session, org_id),
                _CLOCK,
                event_type_id=event_id,
                from_date=target,
                to_date=target,
            )
        assert all(s.start != slots[1].start for s in slots2)

        # Cancelling the collective booking cancels every linked row.
        async with org_session(org_id) as session:
            await SqlBookingManageRepository(session, org_id).cancel(conf.booking_id)
        async with async_sessionmaker(admin_engine)() as db:
            remaining = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM bookings WHERE collective_group_id = :g "
                        "AND status = 'confirmed'"
                    ),
                    {"g": group_rows[0].collective_group_id},
                )
            ).scalar()
        assert remaining == 0
    finally:
        if org_id is not None:
            async with async_sessionmaker(admin_engine)() as db:
                await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                for uid in (host_a, host_b):
                    if uid is not None:
                        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
                await db.commit()
