"""Re-wrapping an org key after a password change, against a live PostgreSQL.

This had no coverage at all, which is how it survived: the function predates ADR-0007 generations
and its UPDATE matched every generation, colliding with the `one_way_in` constraint the moment an
organization rotated. A member of a rotated org simply could not change their password.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def rotated_member(admin_engine: AsyncEngine) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """A member holding generation 0 (password-wrapped) and generation 1 (sealed) — the shape any
    organization has after one rotation."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = (
            await s.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('R', :slug) RETURNING id"),
                {"slug": f"rw-{suffix}"},
            )
        ).scalar_one()
        user = (
            await s.execute(
                text(
                    "INSERT INTO users (email, name, timezone) VALUES (:e, 'R', 'UTC') RETURNING id"
                ),
                {"e": f"rw-{suffix}@example.test"},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role) VALUES (:o, :u, 'owner')"
            ),
            {"o": org, "u": user},
        )
        await s.execute(
            text(
                "INSERT INTO org_member_keys "
                "(organization_id, user_id, generation, wrapped_private_key, wrap_salt) "
                "VALUES (:o, :u, 0, 'wrapped-v0', 'salt-v0')"
            ),
            {"o": org, "u": user},
        )
        await s.execute(
            text(
                "INSERT INTO org_member_keys "
                "(organization_id, user_id, generation, sealed_org_key) "
                "VALUES (:o, :u, 1, 'sealed-v1')"
            ),
            {"o": org, "u": user},
        )
        await s.commit()
    try:
        yield org, user
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
            await s.commit()


async def test_a_password_change_survives_a_rotated_organization(
    admin_engine: AsyncEngine, rotated_member: tuple[uuid.UUID, uuid.UUID]
) -> None:
    org, user = rotated_member

    async with db_session() as session:
        await SqlAuthRepository(session).rewrap_zk_key(
            user, org, wrapped_private_key="wrapped-v1-new", wrap_salt="salt-new"
        )

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT generation, wrapped_private_key, wrap_salt, sealed_org_key "
                    "FROM org_member_keys WHERE user_id = :u ORDER BY generation"
                ),
                {"u": user},
            )
        ).all()

    by_gen = {r.generation: r for r in rows}
    # The password-wrapped row is re-wrapped...
    assert by_gen[0].wrapped_private_key == "wrapped-v1-new"
    assert by_gen[0].wrap_salt == "salt-new"
    # ...and the sealed row is left exactly alone. It is opened with the member's own keypair,
    # which a password change does not touch — and writing to it violates `one_way_in`.
    assert by_gen[1].sealed_org_key == "sealed-v1"
    assert by_gen[1].wrapped_private_key is None
    assert by_gen[1].wrap_salt is None


async def test_re_wrapping_still_works_before_any_rotation(admin_engine: AsyncEngine) -> None:
    """The pre-ADR-0007 shape — one generation-0 row — must behave exactly as it always did."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = (
            await s.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('P', :s) RETURNING id"),
                {"s": f"pw-{suffix}"},
            )
        ).scalar_one()
        user = (
            await s.execute(
                text(
                    "INSERT INTO users (email, name, timezone) VALUES (:e,'P','UTC') RETURNING id"
                ),
                {"e": f"pw-{suffix}@example.test"},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO org_member_keys "
                "(organization_id, user_id, generation, wrapped_private_key, wrap_salt) "
                "VALUES (:o, :u, 0, 'old', 'old-salt')"
            ),
            {"o": org, "u": user},
        )
        await s.commit()
    try:
        async with db_session() as session:
            await SqlAuthRepository(session).rewrap_zk_key(
                user, org, wrapped_private_key="new", wrap_salt="new-salt"
            )
        async with maker() as s:
            row = (
                await s.execute(
                    text("SELECT wrapped_private_key FROM org_member_keys WHERE user_id = :u"),
                    {"u": user},
                )
            ).scalar_one()
        assert row == "new"
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
            await s.commit()
