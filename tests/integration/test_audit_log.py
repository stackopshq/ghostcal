"""The audit log, against a live PostgreSQL.

The point of keeping one is that it survives the person who wants it gone. So the interesting
tests are not "does it write a row" but "can the application connection erase or rewrite one" —
the answer must be no, enforced by the database rather than by convention.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.audit import Action, AuditLog
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.audit_repository import SqlAuditSink
from ghostcal.infrastructure.db.session import db_session, org_session

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def org(admin_engine: AsyncEngine) -> AsyncIterator[uuid.UUID]:
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        organization = models.Organization(name="Org", slug=f"aud-{uuid.uuid4().hex[:8]}")
        s.add(organization)
        await s.commit()
        org_id = organization.id
    try:
        yield org_id
    finally:
        async with maker() as s:
            await s.execute(
                text("DELETE FROM audit_events WHERE organization_id = :o"), {"o": org_id}
            )
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
            await s.commit()


async def test_an_org_scoped_event_is_recorded_and_readable(org: uuid.UUID) -> None:
    async with org_session(org) as session:
        await AuditLog(SqlAuditSink(session)).record(
            Action.ORG_KEY_ROTATED, organization_id=org, target=str(org), generation=3
        )

    async with org_session(org) as session:
        row = (
            await session.execute(
                text("SELECT action, details FROM audit_events WHERE organization_id = :o"),
                {"o": org},
            )
        ).one()

    assert row.action == Action.ORG_KEY_ROTATED
    assert row.details["generation"] == 3


async def test_the_application_role_cannot_delete_history(org: uuid.UUID) -> None:
    """An attacker who reaches the app connection may add noise; they must not be able to remove
    the entry recording what they did. This is the property the whole table exists for."""
    async with org_session(org) as session:
        await AuditLog(SqlAuditSink(session)).record(Action.MEMBER_REMOVED, organization_id=org)

    with pytest.raises(ProgrammingError, match="permission denied"):
        async with org_session(org) as session:
            await session.execute(
                text("DELETE FROM audit_events WHERE organization_id = :o"), {"o": org}
            )


async def test_the_application_role_cannot_rewrite_history(org: uuid.UUID) -> None:
    async with org_session(org) as session:
        await AuditLog(SqlAuditSink(session)).record(Action.MEMBER_REMOVED, organization_id=org)

    with pytest.raises(ProgrammingError, match="permission denied"):
        async with org_session(org) as session:
            await session.execute(
                text("UPDATE audit_events SET action = 'x' WHERE organization_id = :o"),
                {"o": org},
            )


async def test_one_org_cannot_read_another_orgs_history(org: uuid.UUID) -> None:
    async with org_session(org) as session:
        await AuditLog(SqlAuditSink(session)).record(Action.ORG_KEY_ROTATED, organization_id=org)

    async with org_session(uuid.uuid4()) as session:
        visible = (await session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()

    assert visible == 0


async def test_an_account_level_event_needs_no_org_context(admin_engine: AsyncEngine) -> None:
    """A failed login belongs to no organization, so the tenant policy would reject it on a plain
    session — it goes through the SECURITY DEFINER writer instead."""
    marker = f"probe-{uuid.uuid4().hex[:8]}"
    async with db_session() as session:
        await AuditLog(SqlAuditSink(session)).record(Action.LOGIN_FAILED, target=marker)

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        row = (
            await s.execute(
                text("SELECT action, organization_id FROM audit_events WHERE target = :t"),
                {"t": marker},
            )
        ).one()
        await s.execute(text("DELETE FROM audit_events WHERE target = :t"), {"t": marker})
        await s.commit()

    assert row.action == Action.LOGIN_FAILED
    assert row.organization_id is None


async def test_a_pooled_connection_can_read_after_its_binding_reverted(org: uuid.UUID) -> None:
    """`set_config(..., is_local => true)` reverts the GUC to the empty string, not to unset, so a
    policy comparing `''::uuid` raises instead of matching nothing. Migration b2d8f30c17ae swept
    every policy for exactly this; a policy added afterwards has to get it right on its own."""
    async with org_session(org) as session:
        await AuditLog(SqlAuditSink(session)).record(Action.ORG_KEY_ROTATED, organization_id=org)

    # Bind and release, as a pooled connection does, then read with no binding at all.
    async with db_session() as session:
        await session.execute(
            text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org)}
        )
    async with db_session() as session:
        visible = (await session.execute(text("SELECT count(*) FROM audit_events"))).scalar_one()

    assert visible == 0  # empty, not an exception


async def test_the_rotation_route_actually_lands_an_audit_row(
    admin_engine: AsyncEngine, org: uuid.UUID
) -> None:
    """The bug this pins: the route opened an unbound `db_session`, so the org-scoped INSERT was
    refused by RLS — and `AuditLog.record` swallows failures by design, so the rotation succeeded
    while its audit entry silently vanished. Asserting through the *route's own* session shape is
    the point; the earlier tests used `org_session` and therefore proved nothing about production.
    """
    from ghostcal.application.audit import AuditLog as _AuditLog

    # Exactly what keypair_routes does now: org-bound session, org-scoped record.
    async with org_session(org) as session:
        await _AuditLog(SqlAuditSink(session)).record(
            Action.ORG_KEY_ROTATED, organization_id=org, generation=1, members_resealed_to=2
        )

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        count = (
            await s.execute(
                text(
                    "SELECT count(*) FROM audit_events WHERE organization_id = :o AND action = :a"
                ),
                {"o": org, "a": Action.ORG_KEY_ROTATED},
            )
        ).scalar_one()

    assert count == 1
