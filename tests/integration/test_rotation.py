"""Org key rotation against a live PostgreSQL. See ADR-0007.

The server cannot check the crypto — it never sees a private key. What it can check, and what these
tests are about, is that a rotation is **complete** (nobody left behind: a silent lockout is the
failure mode that actually hurts) and **closed** (no key handed to an outsider), that it is
all-or-nothing, and that members keep every past generation so records not yet re-sealed still open.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.rotation import (
    MembersLeftBehind,
    MembersWithoutKeypair,
    NotAMember,
    NotAuthorized,
    RotationService,
    SealedMemberKey,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.rotation_repository import SqlRotationRepository
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration

# Opaque base64 — the server never interprets key material.
OLD_PUBLIC = "b2xkLW9yZy1wdWJsaWM="
NEW_PUBLIC = "bmV3LW9yZy1wdWJsaWM="
NEWER_PUBLIC = "bmV3ZXItb3JnLXB1YmxpYw=="


def _service(session: object) -> RotationService:
    return RotationService(SqlRotationRepository(session))  # type: ignore[arg-type]


def _sealed(user_id: uuid.UUID, tag: str) -> SealedMemberKey:
    return SealedMemberKey(user_id=user_id, sealed_org_key=f"sealed-{tag}")


@dataclass
class Fixture:
    org: uuid.UUID
    owner: uuid.UUID
    admin: uuid.UUID
    member: uuid.UUID
    outsider: uuid.UUID


def _user(suffix: str, tag: str, *, with_keypair: bool = True) -> models.User:
    return models.User(
        email=f"{tag}-{suffix}@example.com",
        name=tag.capitalize(),
        timezone="UTC",
        zk_public_key=f"pk-{tag}" if with_keypair else None,
        zk_wrapped_private_key=f"wrapped-{tag}" if with_keypair else None,
        zk_wrap_salt=f"salt-{tag}" if with_keypair else None,
    )


@pytest_asyncio.fixture
async def org(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """An org with an owner, an admin and a plain member — all three with a keypair — plus an
    outsider who belongs to no org of ours."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        organization = models.Organization(
            name="Org", slug=f"rot-{suffix}", zk_public_key=OLD_PUBLIC
        )
        owner = _user(suffix, "owner")
        admin = _user(suffix, "admin")
        member = _user(suffix, "member")
        outsider = _user(suffix, "outsider")
        s.add_all([organization, owner, admin, member, outsider])
        await s.flush()
        s.add_all(
            [
                models.Membership(organization_id=organization.id, user_id=owner.id, role="owner"),
                models.Membership(organization_id=organization.id, user_id=admin.id, role="admin"),
                models.Membership(
                    organization_id=organization.id, user_id=member.id, role="member"
                ),
            ]
        )
        # Generation 0: the original password-wrapped key, as every org has today.
        for user in (owner, admin, member):
            s.add(
                models.OrgMemberKey(
                    organization_id=organization.id,
                    user_id=user.id,
                    generation=0,
                    wrapped_private_key=f"gen0-wrapped-{user.name}",
                    wrap_salt="gen0-salt",
                )
            )
        await s.commit()
        fixture = Fixture(
            org=organization.id,
            owner=owner.id,
            admin=admin.id,
            member=member.id,
            outsider=outsider.id,
        )
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": fixture.org})
            await s.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {
                    "ids": [
                        fixture.owner,
                        fixture.admin,
                        fixture.member,
                        fixture.outsider,
                    ]
                },
            )
            await s.commit()


async def _state(admin_engine: AsyncEngine, org_id: uuid.UUID) -> tuple[str, int, list[tuple]]:
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        o = (
            await s.execute(
                text("SELECT zk_public_key, zk_key_generation FROM organizations WHERE id = :o"),
                {"o": org_id},
            )
        ).one()
        keys = (
            await s.execute(
                text(
                    "SELECT user_id, generation, sealed_org_key FROM org_member_keys "
                    "WHERE organization_id = :o ORDER BY generation, user_id"
                ),
                {"o": org_id},
            )
        ).all()
    return o.zk_public_key, o.zk_key_generation, [tuple(k) for k in keys]


async def test_rotation_advances_the_key_and_keeps_the_old_generation(
    org: Fixture, admin_engine: AsyncEngine
) -> None:
    async with db_session() as s:
        generation = await _service(s).rotate(
            org.org,
            org.owner,
            public_key=NEW_PUBLIC,
            member_keys=[
                _sealed(org.owner, "owner"),
                _sealed(org.admin, "admin"),
                _sealed(org.member, "member"),
            ],
        )
    assert generation == 1

    public_key, gen, keys = await _state(admin_engine, org.org)

    # Everything created from now on is sealed to the new key — the urgent half of a rotation.
    assert public_key == NEW_PUBLIC
    assert gen == 1

    # Generation 0 survives. A departed member already kept it, so keeping it for the others costs
    # nothing — and it is what lets records not yet re-sealed still open.
    gen0 = {k[0] for k in keys if k[1] == 0}
    gen1 = {k[0]: k[2] for k in keys if k[1] == 1}
    assert gen0 == {org.owner, org.admin, org.member}
    assert set(gen1) == {org.owner, org.admin, org.member}
    assert gen1[org.member] == "sealed-member"


async def test_a_member_left_behind_is_refused_by_name(
    org: Fixture, admin_engine: AsyncEngine
) -> None:
    """The failure mode that matters: rotating past someone locks them out of their own org's data,
    silently, and only they would ever find out."""
    with pytest.raises(MembersLeftBehind) as caught:
        async with db_session() as s:
            await _service(s).rotate(
                org.org,
                org.owner,
                public_key=NEW_PUBLIC,
                member_keys=[_sealed(org.owner, "owner"), _sealed(org.admin, "admin")],
            )

    assert any("member-" in email for email in caught.value.emails)

    # And nothing moved: a refusal is a clean no-op.
    public_key, gen, _ = await _state(admin_engine, org.org)
    assert (public_key, gen) == (OLD_PUBLIC, 0)


async def test_an_outsider_cannot_be_slipped_in(org: Fixture, admin_engine: AsyncEngine) -> None:
    """A key for a non-member is a key for an outsider."""
    with pytest.raises(NotAMember):
        async with db_session() as s:
            await _service(s).rotate(
                org.org,
                org.owner,
                public_key=NEW_PUBLIC,
                member_keys=[
                    _sealed(org.owner, "owner"),
                    _sealed(org.admin, "admin"),
                    _sealed(org.member, "member"),
                    _sealed(org.outsider, "outsider"),
                ],
            )

    public_key, gen, _ = await _state(admin_engine, org.org)
    assert (public_key, gen) == (OLD_PUBLIC, 0)


async def test_a_plain_member_cannot_rotate(org: Fixture, admin_engine: AsyncEngine) -> None:
    with pytest.raises(NotAuthorized):
        async with db_session() as s:
            await _service(s).rotate(
                org.org,
                org.member,  # a "member", not an owner or admin
                public_key=NEW_PUBLIC,
                member_keys=[
                    _sealed(org.owner, "owner"),
                    _sealed(org.admin, "admin"),
                    _sealed(org.member, "member"),
                ],
            )

    public_key, gen, _ = await _state(admin_engine, org.org)
    assert (public_key, gen) == (OLD_PUBLIC, 0)


async def test_an_admin_may_rotate(org: Fixture) -> None:
    async with db_session() as s:
        generation = await _service(s).rotate(
            org.org,
            org.admin,
            public_key=NEW_PUBLIC,
            member_keys=[
                _sealed(org.owner, "owner"),
                _sealed(org.admin, "admin"),
                _sealed(org.member, "member"),
            ],
        )
    assert generation == 1


async def test_rotation_is_refused_while_a_member_has_no_keypair(
    org: Fixture, admin_engine: AsyncEngine
) -> None:
    """There is nothing to seal the new key to. Refuse and name them, rather than lock them out."""
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        await s.execute(
            text(
                "UPDATE users SET zk_public_key = NULL, zk_wrapped_private_key = NULL, "
                "zk_wrap_salt = NULL WHERE id = :u"
            ),
            {"u": org.member},
        )
        await s.commit()

    with pytest.raises(MembersWithoutKeypair) as caught:
        async with db_session() as s:
            await _service(s).rotate(
                org.org,
                org.owner,
                public_key=NEW_PUBLIC,
                member_keys=[
                    _sealed(org.owner, "owner"),
                    _sealed(org.admin, "admin"),
                    _sealed(org.member, "member"),
                ],
            )

    assert any("member-" in email for email in caught.value.emails)
    public_key, gen, _ = await _state(admin_engine, org.org)
    assert (public_key, gen) == (OLD_PUBLIC, 0)


async def test_generations_accumulate_across_rotations(
    org: Fixture, admin_engine: AsyncEngine
) -> None:
    members = [_sealed(org.owner, "o"), _sealed(org.admin, "a"), _sealed(org.member, "m")]

    async with db_session() as s:
        assert (
            await _service(s).rotate(org.org, org.owner, public_key=NEW_PUBLIC, member_keys=members)
            == 1
        )
    async with db_session() as s:
        assert (
            await _service(s).rotate(
                org.org, org.owner, public_key=NEWER_PUBLIC, member_keys=members
            )
            == 2
        )

    public_key, gen, keys = await _state(admin_engine, org.org)
    assert (public_key, gen) == (NEWER_PUBLIC, 2)
    # Three members, three generations: every key the org has ever had, so nothing sealed under an
    # older one becomes unreadable while the backlog is still being re-sealed.
    assert sorted({k[1] for k in keys}) == [0, 1, 2]
    assert len(keys) == 9
