"""Backlog re-sealing against a live PostgreSQL. See ADR-0007.

This pass walks an organization's entire encrypted history, so the tests are mostly about the ways
that could go wrong rather than the happy path: it must be resumable, idempotent, and it must refuse
to write anything if the org rotated again while it was running.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.reseal import ResealedRecord, ResealService, RotatedUnderneath
from ghostcal.application.rotation import RotationService, SealedMemberKey
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.reseal_repository import SqlResealRepository
from ghostcal.infrastructure.db.rotation_repository import SqlRotationRepository
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration

START = datetime(2050, 6, 1, 10, 0, tzinfo=UTC)

SEALED_GEN0 = "c2VhbGVkLXVuZGVyLWdlbi0w"
RESEALED = "cmUtc2VhbGVkLXVuZGVyLWdlbi0x"


def _reseal(session: object) -> ResealService:
    return ResealService(SqlResealRepository(session))  # type: ignore[arg-type]


def _rotation(session: object) -> RotationService:
    return RotationService(SqlRotationRepository(session))  # type: ignore[arg-type]


@dataclass
class Fixture:
    org: uuid.UUID
    owner: uuid.UUID
    booking: uuid.UUID
    event: uuid.UUID
    task: uuid.UUID
    unsealed_event: uuid.UUID


@pytest_asyncio.fixture
async def org_with_sealed_history(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """One org, one owner, one of each sealed thing, and an event with nothing sealed in it."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        organization = models.Organization(
            name="Org", slug=f"rs-{suffix}", zk_public_key="old-public"
        )
        owner = models.User(
            email=f"owner-{suffix}@example.com",
            name="Owner",
            timezone="UTC",
            zk_public_key="pk-owner",
            zk_wrapped_private_key="wrapped-owner",
            zk_wrap_salt="salt-owner",
        )
        s.add_all([organization, owner])
        await s.flush()
        s.add_all(
            [
                models.Membership(organization_id=organization.id, user_id=owner.id, role="owner"),
                models.OrgMemberKey(
                    organization_id=organization.id,
                    user_id=owner.id,
                    generation=0,
                    wrapped_private_key="gen0-wrapped",
                    wrap_salt="gen0-salt",
                ),
            ]
        )
        event_type = models.EventType(
            organization_id=organization.id,
            owner_id=owner.id,
            slug=f"intro-{suffix}",
            title="Intro",
            duration_min=30,
            slot_interval_min=30,
        )
        calendar = models.Calendar(
            organization_id=organization.id, owner_id=owner.id, name="Personal"
        )
        s.add_all([event_type, calendar])
        await s.flush()

        booking = models.Booking(
            organization_id=organization.id,
            event_type_id=event_type.id,
            host_id=owner.id,
            invitee_email="invitee@example.com",
            invitee_timezone="UTC",
            start_at=START,
            end_at=START + timedelta(minutes=30),
            status="confirmed",
            invitee_private=SEALED_GEN0,
        )
        event = models.CalendarEvent(
            organization_id=organization.id,
            owner_id=owner.id,
            calendar_id=calendar.id,
            start_at=START,
            end_at=START + timedelta(hours=1),
            timezone="UTC",
            content=SEALED_GEN0,
        )
        # Nothing sealed in it: it must never turn up in the backlog.
        unsealed = models.CalendarEvent(
            organization_id=organization.id,
            owner_id=owner.id,
            calendar_id=calendar.id,
            start_at=START,
            end_at=START + timedelta(hours=1),
            timezone="UTC",
            content=None,
        )
        task = models.Task(organization_id=organization.id, owner_id=owner.id, content=SEALED_GEN0)
        s.add_all([booking, event, unsealed, task])
        await s.commit()
        fixture = Fixture(
            org=organization.id,
            owner=owner.id,
            booking=booking.id,
            event=event.id,
            task=task.id,
            unsealed_event=unsealed.id,
        )
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(
                text("DELETE FROM bookings WHERE organization_id = :o"), {"o": fixture.org}
            )
            await s.execute(
                text("DELETE FROM event_types WHERE organization_id = :o"), {"o": fixture.org}
            )
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": fixture.org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": fixture.owner})
            await s.commit()


async def _rotate(fixture: Fixture) -> int:
    async with db_session() as s:
        return await _rotation(s).rotate(
            fixture.org,
            fixture.owner,
            public_key="new-public",
            member_keys=[SealedMemberKey(user_id=fixture.owner, sealed_org_key="sealed-owner")],
        )


async def test_nothing_is_pending_before_a_rotation(org_with_sealed_history: Fixture) -> None:
    """Everything is sealed under the key currently in force. There is no backlog to speak of."""
    async with db_session() as s:
        backlog = await _reseal(s).backlog(org_with_sealed_history.org)
    assert backlog == type(backlog)(generation=0, remaining=0)


async def test_a_rotation_turns_the_whole_history_into_backlog(
    org_with_sealed_history: Fixture,
) -> None:
    assert await _rotate(org_with_sealed_history) == 1

    async with db_session() as s:
        backlog = await _reseal(s).backlog(org_with_sealed_history.org)
        pending = await _reseal(s).pending(org_with_sealed_history.org, limit=50)

    # Three sealed records; the event with nothing sealed in it is not backlog.
    assert backlog.generation == 1
    assert backlog.remaining == 3
    assert {p.kind for p in pending} == {"booking", "event", "task"}
    assert org_with_sealed_history.unsealed_event not in {p.id for p in pending}
    assert all(p.sealed == SEALED_GEN0 for p in pending)


async def test_re_sealing_empties_the_backlog(
    org_with_sealed_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """The moment the backlog reaches zero, the retired key opens nothing at all."""
    await _rotate(org_with_sealed_history)

    async with db_session() as s:
        pending = await _reseal(s).pending(org_with_sealed_history.org, limit=50)
    async with db_session() as s:
        result = await _reseal(s).apply(
            org_with_sealed_history.org,
            generation=1,
            records=[ResealedRecord(kind=p.kind, id=p.id, sealed=RESEALED) for p in pending],
        )
    assert result == 3

    async with db_session() as s:
        backlog = await _reseal(s).backlog(org_with_sealed_history.org)
    assert backlog.remaining == 0

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        blobs = (
            await s.execute(
                text(
                    "SELECT invitee_private AS b, zk_generation AS g FROM bookings "
                    "WHERE organization_id = :o "
                    "UNION ALL SELECT content, zk_generation FROM calendar_events "
                    "WHERE organization_id = :o AND content IS NOT NULL "
                    "UNION ALL SELECT content, zk_generation FROM tasks WHERE organization_id = :o"
                ),
                {"o": org_with_sealed_history.org},
            )
        ).all()
    assert all(r.b == RESEALED and r.g == 1 for r in blobs)


async def test_applying_the_same_batch_twice_is_a_no_op(org_with_sealed_history: Fixture) -> None:
    """A retried batch must be a no-op, not a corruption: this walks the whole encrypted history."""
    await _rotate(org_with_sealed_history)

    async with db_session() as s:
        pending = await _reseal(s).pending(org_with_sealed_history.org, limit=50)
    records = [ResealedRecord(kind=p.kind, id=p.id, sealed=RESEALED) for p in pending]

    async with db_session() as s:
        assert (
            await _reseal(s).apply(org_with_sealed_history.org, generation=1, records=records) == 3
        )
    async with db_session() as s:
        # Nothing left behind the current generation, so nothing moves — and nothing is overwritten.
        assert (
            await _reseal(s).apply(org_with_sealed_history.org, generation=1, records=records) == 0
        )


async def test_a_rotation_underneath_the_pass_is_refused(
    org_with_sealed_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """Blobs sealed to the previous key must not be written: they would be stamped current and
    quietly stranded — readable only by the fallback, and invisible to every later re-seal pass."""
    await _rotate(org_with_sealed_history)

    async with db_session() as s:
        pending = await _reseal(s).pending(org_with_sealed_history.org, limit=50)

    # The org rotates again while our browser was busy sealing to generation 1.
    await _rotate(org_with_sealed_history)

    with pytest.raises(RotatedUnderneath):
        async with db_session() as s:
            await _reseal(s).apply(
                org_with_sealed_history.org,
                generation=1,
                records=[ResealedRecord(kind=p.kind, id=p.id, sealed=RESEALED) for p in pending],
            )

    # Nothing was written: the records are untouched, still waiting for a pass at generation 2.
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        stale = (
            await s.execute(
                text("SELECT content, zk_generation FROM tasks WHERE organization_id = :o"),
                {"o": org_with_sealed_history.org},
            )
        ).one()
    assert stale.content == SEALED_GEN0
    assert stale.zk_generation == 0

    async with db_session() as s:
        backlog = await _reseal(s).backlog(org_with_sealed_history.org)
    assert (backlog.generation, backlog.remaining) == (2, 3)


async def test_a_record_created_after_a_rotation_is_stamped_current(
    org_with_sealed_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """The trigger, not the application, stamps the generation — so every write path gets it,
    including ones written later by someone who never read the migration."""
    await _rotate(org_with_sealed_history)

    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        fresh = models.Task(
            organization_id=org_with_sealed_history.org,
            owner_id=org_with_sealed_history.owner,
            content="sealed-under-gen-1",
        )
        s.add(fresh)
        await s.commit()
        stamped = fresh.id

    async with maker() as s:
        row = (
            await s.execute(text("SELECT zk_generation FROM tasks WHERE id = :t"), {"t": stamped})
        ).one()
    assert row.zk_generation == 1  # not backlog: it was already sealed to the current key

    async with db_session() as s:
        pending = await _reseal(s).pending(org_with_sealed_history.org, limit=50)
    assert stamped not in {p.id for p in pending}
