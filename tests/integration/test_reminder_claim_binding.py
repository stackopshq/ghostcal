"""A reminder claim must belong to the organization it names (live PostgreSQL).

Left unbound, each claim function is a cross-tenant denial-of-notification primitive: claim another
tenant's booking under your own org id, the unique constraint is taken, and the worker's `NOT
EXISTS` check then suppresses the real reminder. The invitee is simply never told.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.infrastructure.db import models

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def two_orgs(
    admin_engine: AsyncEngine,
) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """Victim org with a booking, plus an unrelated attacker org."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        victim = models.Organization(name="V", slug=f"vic-{suffix}")
        attacker = models.Organization(name="A", slug=f"att-{suffix}")
        host = models.User(email=f"h-{suffix}@example.test", name="H", timezone="UTC")
        s.add_all([victim, attacker, host])
        await s.flush()
        event_type = models.EventType(
            organization_id=victim.id,
            owner_id=host.id,
            slug=f"intro-{suffix}",
            title="Intro",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event_type)
        await s.flush()
        start_at = datetime.now(UTC) + timedelta(days=1)
        booking_row = models.Booking(
            organization_id=victim.id,
            event_type_id=event_type.id,
            host_id=host.id,
            invitee_email="i@example.test",
            invitee_timezone="UTC",
            start_at=start_at,
            end_at=start_at + timedelta(minutes=30),
            status="confirmed",
        )
        s.add(booking_row)
        await s.commit()
        victim_id, attacker_id, booking, host_id = (
            victim.id,
            attacker.id,
            booking_row.id,
            host.id,
        )
    try:
        yield victim_id, attacker_id, booking
    finally:
        async with maker() as s:
            for org in (victim_id, attacker_id):
                await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": host_id})
            await s.commit()


async def test_a_foreign_org_cannot_claim_a_booking_reminder(
    admin_engine: AsyncEngine, two_orgs: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    victim, attacker, booking = two_orgs
    maker = async_sessionmaker(admin_engine)

    async with maker() as s:
        claimed = (
            await s.execute(
                text("SELECT claim_booking_reminder(:b, :o, 60)"),
                {"b": booking, "o": attacker},
            )
        ).scalar_one()
        await s.commit()
    assert claimed is False  # the pair does not belong together

    # And crucially the slot is still free, so the real reminder is not suppressed.
    async with maker() as s:
        genuine = (
            await s.execute(
                text("SELECT claim_booking_reminder(:b, :o, 60)"),
                {"b": booking, "o": victim},
            )
        ).scalar_one()
        await s.commit()
    assert genuine is True


async def test_the_owning_org_can_still_claim_once(
    admin_engine: AsyncEngine, two_orgs: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    victim, _, booking = two_orgs
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        first = (
            await s.execute(
                text("SELECT claim_booking_reminder(:b, :o, 1440)"), {"b": booking, "o": victim}
            )
        ).scalar_one()
        second = (
            await s.execute(
                text("SELECT claim_booking_reminder(:b, :o, 1440)"), {"b": booking, "o": victim}
            )
        ).scalar_one()
        await s.commit()
    assert first is True
    assert second is False  # exactly-once still holds
