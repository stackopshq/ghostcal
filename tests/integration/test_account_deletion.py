"""Account erasure against a live PostgreSQL. See ADR-0006.

Covers the two deletion paths (sole member → the organization goes; shared organization → the person
is anonymized out of it), the sole-owner refusal, and the exclusion-constraint trap that the whole
tombstone design turns on.
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

from ghostcal.application.account import (
    AccountService,
    ConfirmationMismatch,
    InvalidPassword,
    SoleOwner,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.account_repository import SqlAccountRepository
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher

pytestmark = pytest.mark.integration

NOW = datetime(2050, 1, 1, tzinfo=UTC)
PAST = datetime(2049, 6, 1, 10, 0, tzinfo=UTC)
FUTURE = datetime(2051, 6, 1, 10, 0, tzinfo=UTC)

PASSWORD = "s3cret-passw0rd"
_HASHER = Argon2PasswordHasher()


def _service(session: object) -> AccountService:
    return AccountService(
        SqlAccountRepository(session),  # type: ignore[arg-type]
        SqlAuthRepository(session),  # type: ignore[arg-type]
        _HASHER,
    )


@dataclass
class Fixture:
    org: uuid.UUID
    users: dict[str, uuid.UUID]
    emails: dict[str, str]
    event_type: uuid.UUID


def _user(suffix: str, tag: str) -> models.User:
    return models.User(
        email=f"{tag}-{suffix}@example.com",
        name=tag.capitalize(),
        timezone="UTC",
        email_verified_at=NOW,
    )


async def _cleanup(
    maker: async_sessionmaker[object], org: uuid.UUID, users: list[uuid.UUID]
) -> None:
    async with maker() as s:  # type: ignore[misc]
        # Bookings/event types first: they reference users with RESTRICT (the very reason the
        # tombstone exists). The tombstone row itself is seeded by migration and must survive.
        await s.execute(text("DELETE FROM bookings WHERE organization_id = :o"), {"o": org})
        await s.execute(text("DELETE FROM event_types WHERE organization_id = :o"), {"o": org})
        await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
        for user_id in users:
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await s.commit()


@pytest_asyncio.fixture
async def shared_org(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """An org with two owners and one plain member; the member hosts a past and a future booking."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"org-{suffix}")
        founder = _user(suffix, "founder")
        member = _user(suffix, "member")
        s.add_all([org, founder, member])
        await s.flush()
        s.add_all(
            [
                models.UserCredential(user_id=member.id, password_hash=_HASHER.hash(PASSWORD)),
                models.Membership(organization_id=org.id, user_id=founder.id, role="owner"),
                models.Membership(organization_id=org.id, user_id=member.id, role="member"),
            ]
        )
        event = models.EventType(
            organization_id=org.id,
            owner_id=member.id,
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
                    host_id=member.id,
                    invitee_email="invitee@example.com",
                    invitee_timezone="Europe/Zurich",
                    start_at=start,
                    end_at=start + timedelta(minutes=30),
                    status="confirmed",
                )
            )
        await s.commit()
        fixture = Fixture(
            org=org.id,
            users={"founder": founder.id, "member": member.id},
            emails={"founder": founder.email, "member": member.email},
            event_type=event.id,
        )
    try:
        yield fixture
    finally:
        await _cleanup(maker, fixture.org, list(fixture.users.values()))


async def test_member_is_anonymized_out_of_a_shared_org(
    shared_org: Fixture, admin_engine: AsyncEngine
) -> None:
    member = shared_org.users["member"]

    async with db_session() as s:
        cancelled = await _service(s).delete(
            member,
            email_confirmation=shared_org.emails["member"],
            password=PASSWORD,
            now=NOW,
        )

    # The future booking's invitee is told; the past one is history and needs no notice.
    assert len(cancelled) == 1
    assert cancelled[0].invitee_email == "invitee@example.com"
    assert cancelled[0].event_title == "Intro call"
    assert cancelled[0].start_at == FUTURE

    # Assertions go through the admin (RLS-bypassing) connection, like the seeding does: reading
    # tenant tables from an unbound session is exactly what RLS is there to prevent.
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        assert (
            await s.execute(text("SELECT 1 FROM users WHERE id = :u"), {"u": member})
        ).first() is None

        # The org survives, with its history — carried by the tombstone, not by the departed member.
        rows = (
            await s.execute(
                text(
                    "SELECT host_id, status, blocks_host, start_at FROM bookings "
                    "WHERE organization_id = :o ORDER BY start_at"
                ),
                {"o": shared_org.org},
            )
        ).all()
        assert len(rows) == 2
        assert all(r.host_id == models.TOMBSTONE_USER_ID for r in rows)
        assert all(r.blocks_host is False for r in rows)
        assert [r.status for r in rows] == ["confirmed", "cancelled"]  # past kept, future cancelled

        # The booking page stops taking bookings — there is no host behind it any more.
        event = (
            await s.execute(
                text("SELECT owner_id, active FROM event_types WHERE id = :e"),
                {"e": shared_org.event_type},
            )
        ).one()
        assert event.owner_id == models.TOMBSTONE_USER_ID
        assert event.active is False

        # The remaining owner is untouched.
        remaining = (
            await s.execute(
                text("SELECT user_id FROM memberships WHERE organization_id = :o"),
                {"o": shared_org.org},
            )
        ).all()
        assert [r.user_id for r in remaining] == [shared_org.users["founder"]]


async def test_sole_owner_of_a_shared_org_is_refused(
    shared_org: Fixture, admin_engine: AsyncEngine
) -> None:
    founder = shared_org.users["founder"]  # the only owner, and the org has another member

    with pytest.raises(SoleOwner):
        async with db_session() as s:
            await _service(s).delete(
                founder, email_confirmation=shared_org.emails["founder"], password=None, now=NOW
            )

    # The refusal left everything alone — the checks run before anything is touched.
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        assert (
            await s.execute(text("SELECT 1 FROM users WHERE id = :u"), {"u": founder})
        ).first() is not None


async def test_confirmation_and_password_are_enforced(shared_org: Fixture) -> None:
    member = shared_org.users["member"]

    with pytest.raises(ConfirmationMismatch):
        async with db_session() as s:
            await _service(s).delete(
                member, email_confirmation="someone-else@example.com", password=PASSWORD, now=NOW
            )

    with pytest.raises(InvalidPassword):
        async with db_session() as s:
            await _service(s).delete(
                member,
                email_confirmation=shared_org.emails["member"],
                password="not-the-password",
                now=NOW,
            )


async def test_sole_member_deletion_takes_the_org_with_it(admin_engine: AsyncEngine) -> None:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Solo", slug=f"solo-{suffix}")
        owner = _user(suffix, "solo")
        s.add_all([org, owner])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=owner.id, role="owner"))
        event = models.EventType(
            organization_id=org.id,
            owner_id=owner.id,
            slug=f"solo-{suffix}",
            title="Solo call",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event)
        await s.flush()
        s.add(
            models.Booking(
                organization_id=org.id,
                event_type_id=event.id,
                host_id=owner.id,
                invitee_email="invitee@example.com",
                invitee_timezone="UTC",
                start_at=PAST,
                end_at=PAST + timedelta(minutes=30),
                status="confirmed",
            )
        )
        await s.commit()
        org_id, owner_id, owner_email = org.id, owner.id, owner.email

    async with db_session() as s:
        await _service(s).delete(owner_id, email_confirmation=owner_email, password=None, now=NOW)

    # Nobody else had an interest in it: the organization and everything under it is gone.
    async with maker() as s:
        for table, column, value in (
            ("users", "id", owner_id),
            ("organizations", "id", org_id),
            ("event_types", "organization_id", org_id),
            ("bookings", "organization_id", org_id),
        ):
            found = (
                await s.execute(
                    text(f"SELECT 1 FROM {table} WHERE {column} = :v"),
                    {"v": value},
                )
            ).first()
            assert found is None, f"{table} still has rows"


async def test_overlapping_bookings_of_two_deleted_hosts_do_not_collide(
    admin_engine: AsyncEngine,
) -> None:
    """The exclusion-constraint trap that the tombstone design exists to survive (ADR-0006 §3).

    ``no_overlap_per_host`` is EXCLUDE (host_id =, period &&) WHERE (status = 'confirmed' AND
    blocks_host). Two hosts' meetings may legitimately overlap; funnelling both onto the single
    tombstone host would make them collide — unless the rows are first taken out of that WHERE.
    """
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Team", slug=f"team-{suffix}")
        keeper = _user(suffix, "keeper")  # stays behind, so the org is never sole-membered
        alice = _user(suffix, "alice")
        bob = _user(suffix, "bob")
        s.add_all([org, keeper, alice, bob])
        await s.flush()
        s.add_all(
            [
                models.Membership(organization_id=org.id, user_id=keeper.id, role="owner"),
                models.Membership(organization_id=org.id, user_id=alice.id, role="owner"),
                models.Membership(organization_id=org.id, user_id=bob.id, role="owner"),
            ]
        )
        event = models.EventType(
            organization_id=org.id,
            owner_id=keeper.id,
            slug=f"sync-{suffix}",
            title="Sync",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event)
        await s.flush()
        # Same slot, two different hosts: perfectly legal today.
        for host in (alice, bob):
            s.add(
                models.Booking(
                    organization_id=org.id,
                    event_type_id=event.id,
                    host_id=host.id,
                    invitee_email="invitee@example.com",
                    invitee_timezone="UTC",
                    start_at=PAST,
                    end_at=PAST + timedelta(minutes=30),
                    status="confirmed",
                )
            )
        await s.commit()
        org_id = org.id
        ids = [keeper.id, alice.id, bob.id]
        alice_id, alice_email = alice.id, alice.email
        bob_id, bob_email = bob.id, bob.email

    try:
        # Both deletions must succeed — the second is the one that would blow up on the constraint.
        async with db_session() as s:
            await _service(s).delete(
                alice_id, email_confirmation=alice_email, password=None, now=NOW
            )
        async with db_session() as s:
            await _service(s).delete(bob_id, email_confirmation=bob_email, password=None, now=NOW)

        async with maker() as s:
            rows = (
                await s.execute(
                    text("SELECT host_id, blocks_host FROM bookings WHERE organization_id = :o"),
                    {"o": org_id},
                )
            ).all()
        assert len(rows) == 2
        assert all(r.host_id == models.TOMBSTONE_USER_ID for r in rows)
        assert all(r.blocks_host is False for r in rows)
    finally:
        await _cleanup(maker, org_id, ids)
