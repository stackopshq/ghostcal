"""Row-Level Security isolation, verified against a live PostgreSQL.

Seeding uses the admin (superuser) connection, which bypasses RLS. Reads/writes under test use
the application connection (``org_session``), a non-BYPASSRLS role, so the policies are actually
exercised. Skipped automatically when no database is reachable (e.g. CI without infra).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def two_orgs(admin_engine: AsyncEngine) -> AsyncIterator[dict[str, uuid.UUID]]:
    """Seed two organizations, a user and an owner membership each. Cleaned up afterwards."""
    suffix = uuid.uuid4().hex[:8]
    ids: dict[str, uuid.UUID] = {}
    async with admin_engine.begin() as conn:
        for key in ("a", "b"):
            org = await conn.scalar(
                text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
                {"n": f"Org {key}", "s": f"org-{key}-{suffix}"},
            )
            user = await conn.scalar(
                text(
                    "INSERT INTO users (email, name, timezone) VALUES (:e, :n, 'UTC') RETURNING id"
                ),
                {"e": f"{key}-{suffix}@example.test", "n": f"User {key}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO memberships (organization_id, user_id, role) "
                    "VALUES (:o, :u, 'owner')"
                ),
                {"o": org, "u": user},
            )
            ids[f"org_{key}"] = org
            ids[f"user_{key}"] = user
    try:
        yield ids
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM organizations WHERE id = ANY(:ids)"),
                {"ids": [ids["org_a"], ids["org_b"]]},
            )
            await conn.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": [ids["user_a"], ids["user_b"]]},
            )


async def test_session_sees_only_its_own_org(two_orgs: dict[str, uuid.UUID]) -> None:
    async with org_session(two_orgs["org_a"]) as session:
        orgs = (await session.execute(text("SELECT id FROM organizations"))).scalars().all()
        members = (
            (await session.execute(text("SELECT organization_id FROM memberships"))).scalars().all()
        )

    assert orgs == [two_orgs["org_a"]]
    assert members == [two_orgs["org_a"]]


async def test_other_org_is_invisible(two_orgs: dict[str, uuid.UUID]) -> None:
    async with org_session(two_orgs["org_b"]) as session:
        seen = (await session.execute(text("SELECT id FROM organizations"))).scalars().all()
    assert two_orgs["org_a"] not in seen
    assert seen == [two_orgs["org_b"]]


async def test_cannot_write_into_another_org(two_orgs: dict[str, uuid.UUID]) -> None:
    # Bound to org A, attempt to create a membership in org B: the RLS WITH CHECK must reject it.
    with pytest.raises((ProgrammingError, DBAPIError)):
        async with org_session(two_orgs["org_a"]) as session:
            await session.execute(
                text(
                    "INSERT INTO memberships (organization_id, user_id, role) "
                    "VALUES (:o, :u, 'member')"
                ),
                {"o": two_orgs["org_b"], "u": two_orgs["user_b"]},
            )
