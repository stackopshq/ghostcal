"""Availability-schedule management against a live PostgreSQL.

Exercises the SQL repo + use cases under an org-scoped session, the owner filter, and the
``user_primary_organization`` resolver used to map a logged-in user to their org.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import time

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.schedules import (
    RuleData,
    ScheduleNotFound,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.membership import primary_organization
from ghostcal.infrastructure.db.schedules_repository import SqlSchedulesRepository
from ghostcal.infrastructure.db.session import db_session, org_session

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def org_with_users(admin_engine: AsyncEngine) -> AsyncIterator[dict[str, uuid.UUID]]:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"org-{suffix}")
        u1 = models.User(email=f"u1-{suffix}@example.com", name="User One", timezone="UTC")
        u2 = models.User(email=f"u2-{suffix}@example.com", name="User Two", timezone="UTC")
        s.add_all([org, u1, u2])
        await s.flush()
        s.add_all(
            [
                models.Membership(organization_id=org.id, user_id=u1.id, role="owner"),
                models.Membership(organization_id=org.id, user_id=u2.id, role="member"),
            ]
        )
        await s.commit()
        ids = {"org": org.id, "u1": u1.id, "u2": u2.id}
    try:
        yield ids
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": ids["org"]})
            await s.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": [ids["u1"], ids["u2"]]},
            )
            await s.commit()


async def test_primary_organization_resolves(org_with_users: dict[str, uuid.UUID]) -> None:
    async with db_session() as session:
        org_id = await primary_organization(session, org_with_users["u1"])
    assert org_id == org_with_users["org"]


async def test_schedule_crud(org_with_users: dict[str, uuid.UUID]) -> None:
    org, owner = org_with_users["org"], org_with_users["u1"]

    async with org_session(org) as session:
        repo = SqlSchedulesRepository(session, org)
        schedule_id = await create_schedule(
            repo,
            owner,
            name="Working hours",
            timezone="Europe/Zurich",
            rules=[RuleData(weekday=0, start=time(9), end=time(17))],
            overrides=[],
        )

    async with org_session(org) as session:
        repo = SqlSchedulesRepository(session, org)
        listed = await list_schedules(repo, owner)
    assert len(listed) == 1
    assert listed[0].name == "Working hours"
    assert listed[0].timezone == "Europe/Zurich"
    assert listed[0].rules == (RuleData(weekday=0, start=time(9), end=time(17)),)

    # Update replaces the rule set.
    async with org_session(org) as session:
        repo = SqlSchedulesRepository(session, org)
        await update_schedule(
            repo,
            schedule_id,
            owner,
            name="New hours",
            timezone="UTC",
            rules=[
                RuleData(weekday=1, start=time(10), end=time(12)),
                RuleData(weekday=3, start=time(14), end=time(18)),
            ],
            overrides=[],
        )
        updated = await get_schedule(repo, schedule_id, owner)
    assert updated.name == "New hours"
    assert {r.weekday for r in updated.rules} == {1, 3}

    # Delete.
    async with org_session(org) as session:
        repo = SqlSchedulesRepository(session, org)
        await delete_schedule(repo, schedule_id, owner)
        assert await list_schedules(repo, owner) == []


async def test_owner_isolation(org_with_users: dict[str, uuid.UUID]) -> None:
    org, u1, u2 = org_with_users["org"], org_with_users["u1"], org_with_users["u2"]

    async with org_session(org) as session:
        repo = SqlSchedulesRepository(session, org)
        u2_schedule = await create_schedule(
            repo, u2, name="U2", timezone="UTC", rules=[], overrides=[]
        )

    async with org_session(org) as session:
        repo = SqlSchedulesRepository(session, org)
        # u1 sees none of u2's schedules and cannot fetch one by id.
        assert await list_schedules(repo, u1) == []
        with pytest.raises(ScheduleNotFound):
            await get_schedule(repo, u2_schedule, u1)
