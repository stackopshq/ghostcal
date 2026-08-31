"""Per-user keypairs against a live PostgreSQL. See ADR-0007.

The two rules the server actually enforces — because they are the two ways a keypair store goes
wrong — are that a keypair is write-once, and that a public key is only visible to someone who
shares an organization with its owner.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.keypairs import (
    KeypairAlreadySet,
    KeypairNotRewrappable,
    KeypairService,
    UserKeypair,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.keypairs_repository import SqlKeypairRepository
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration

# Opaque base64 — the server never interprets key material, so any strings will do.
PUBLIC = "cHVibGljLWtleQ=="
OTHER_PUBLIC = "b3RoZXItcHVibGljLWtleQ=="
WRAPPED = "d3JhcHBlZC1zaw=="
SALT = "c2FsdA=="
REWRAPPED = "cmUtd3JhcHBlZC1zaw=="
NEW_SALT = "bmV3LXNhbHQ="


def _service(session: object) -> KeypairService:
    return KeypairService(SqlKeypairRepository(session))  # type: ignore[arg-type]


def _keypair(public: str = PUBLIC) -> UserKeypair:
    return UserKeypair(public_key=public, wrapped_private_key=WRAPPED, wrap_salt=SALT)


@dataclass
class Fixture:
    org: uuid.UUID
    members: dict[str, uuid.UUID]
    outsider: uuid.UUID
    other_org: uuid.UUID


@pytest_asyncio.fixture
async def two_orgs(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """One org with two members, and a separate org with an outsider in it."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"kp-{suffix}")
        other = models.Organization(name="Other", slug=f"kp-other-{suffix}")
        alice = models.User(email=f"alice-{suffix}@example.com", name="Alice", timezone="UTC")
        bob = models.User(email=f"bob-{suffix}@example.com", name="Bob", timezone="UTC")
        outsider = models.User(email=f"out-{suffix}@example.com", name="Outsider", timezone="UTC")
        s.add_all([org, other, alice, bob, outsider])
        await s.flush()
        s.add_all(
            [
                models.Membership(organization_id=org.id, user_id=alice.id, role="owner"),
                models.Membership(organization_id=org.id, user_id=bob.id, role="member"),
                models.Membership(organization_id=other.id, user_id=outsider.id, role="owner"),
            ]
        )
        await s.commit()
        fixture = Fixture(
            org=org.id,
            members={"alice": alice.id, "bob": bob.id},
            outsider=outsider.id,
            other_org=other.id,
        )
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(
                text("DELETE FROM organizations WHERE id = ANY(:ids)"),
                {"ids": [fixture.org, fixture.other_org]},
            )
            await s.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": [*fixture.members.values(), fixture.outsider]},
            )
            await s.commit()


async def test_a_new_account_has_no_keypair_and_can_publish_one(two_orgs: Fixture) -> None:
    alice = two_orgs.members["alice"]

    async with db_session() as s:
        assert await _service(s).get(alice) is None  # the browser reads this and makes one

    async with db_session() as s:
        await _service(s).set(alice, _keypair())

    async with db_session() as s:
        stored = await _service(s).get(alice)
    assert stored == _keypair()


async def test_a_keypair_is_write_once(two_orgs: Fixture) -> None:
    """Replacing a public key would strand everything ever sealed to it."""
    alice = two_orgs.members["alice"]

    async with db_session() as s:
        await _service(s).set(alice, _keypair())

    with pytest.raises(KeypairAlreadySet):
        async with db_session() as s:
            await _service(s).set(alice, _keypair(OTHER_PUBLIC))

    async with db_session() as s:
        assert (await _service(s).get(alice)).public_key == PUBLIC  # type: ignore[union-attr]


async def test_two_concurrent_logins_cannot_both_win(two_orgs: Fixture) -> None:
    """The write-once rule holds under a race, not just against a second sequential call.

    Two tabs logging in at once both find no keypair and both generate one. If both writes landed,
    the loser's public key would already have been handed out — and anything sealed to it lost. The
    guard is in the UPDATE's WHERE clause, not in a read-then-write, so exactly one can win.
    """
    alice = two_orgs.members["alice"]

    async def publish(public: str) -> bool:
        try:
            async with db_session() as s:
                await _service(s).set(alice, _keypair(public))
            return True
        except KeypairAlreadySet:
            return False

    results = await asyncio.gather(publish(PUBLIC), publish(OTHER_PUBLIC))

    assert sorted(results) == [False, True]  # exactly one won
    async with db_session() as s:
        stored = await _service(s).get(alice)
    assert stored is not None
    assert stored.public_key in (PUBLIC, OTHER_PUBLIC)


async def test_rewrapping_replaces_the_envelope_and_not_the_keypair(two_orgs: Fixture) -> None:
    """The move a password change makes, and the one the write-once rule must not block.

    Write-once exists so a public key cannot be replaced, because everything sealed to it would be
    stranded. A re-wrap strands nothing — the keypair is the same, only its envelope changes — so it
    gets its own path, which matches the public key rather than writing it.
    """
    alice = two_orgs.members["alice"]

    async with db_session() as s:
        await _service(s).set(alice, _keypair())

    async with db_session() as s:
        await _service(s).rewrap(
            alice, public_key=PUBLIC, wrapped_private_key=REWRAPPED, wrap_salt=NEW_SALT
        )

    async with db_session() as s:
        stored = await _service(s).get(alice)
    assert stored is not None
    assert stored.public_key == PUBLIC, "the public key must survive a re-wrap untouched"
    assert stored.wrapped_private_key == REWRAPPED
    assert stored.wrap_salt == NEW_SALT


async def test_rewrapping_a_keypair_the_account_does_not_hold_is_refused(
    two_orgs: Fixture,
) -> None:
    """A browser naming the wrong public key is re-wrapping something else. Refuse, never apply."""
    alice = two_orgs.members["alice"]

    async with db_session() as s:
        await _service(s).set(alice, _keypair())

    with pytest.raises(KeypairNotRewrappable):
        async with db_session() as s:
            await _service(s).rewrap(
                alice,
                public_key=OTHER_PUBLIC,
                wrapped_private_key=REWRAPPED,
                wrap_salt=NEW_SALT,
            )

    async with db_session() as s:
        stored = await _service(s).get(alice)
    assert stored == _keypair(), "a refused re-wrap must leave the envelope exactly as it was"


async def test_rewrapping_before_there_is_a_keypair_is_refused(two_orgs: Fixture) -> None:
    """It is not a back door to creation: with nothing stored, there is nothing to re-wrap."""
    alice = two_orgs.members["alice"]

    with pytest.raises(KeypairNotRewrappable):
        async with db_session() as s:
            await _service(s).rewrap(
                alice, public_key=PUBLIC, wrapped_private_key=REWRAPPED, wrap_salt=NEW_SALT
            )

    async with db_session() as s:
        assert await _service(s).get(alice) is None


async def test_member_keys_lists_the_org_and_flags_who_has_none(two_orgs: Fixture) -> None:
    """A rotation seals the new org key to these. A member with no key cannot be sealed to."""
    async with db_session() as s:
        await _service(s).set(two_orgs.members["alice"], _keypair())

    async with db_session() as s:
        keys = await _service(s).member_public_keys(two_orgs.org)

    by_name = {k.name: k for k in keys}
    assert set(by_name) == {"Alice", "Bob"}  # the outsider's org is not ours
    assert by_name["Alice"].public_key == PUBLIC
    assert by_name["Bob"].public_key is None  # never logged in since keypairs shipped


async def test_member_keys_never_leaks_another_org(two_orgs: Fixture) -> None:
    """Public keys are not secret, but a directory of every user in the system is not on offer."""
    async with db_session() as s:
        await _service(s).set(two_orgs.outsider, _keypair(OTHER_PUBLIC))

    async with db_session() as s:
        keys = await _service(s).member_public_keys(two_orgs.org)

    assert two_orgs.outsider not in {k.user_id for k in keys}
    assert OTHER_PUBLIC not in {k.public_key for k in keys}
