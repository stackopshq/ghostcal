"""Org-switcher resolvers against a live PostgreSQL: list a user's orgs and verify membership."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.membership import role_in_org, user_organizations
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration


async def test_user_organizations_and_role(admin_engine: AsyncEngine) -> None:
    user_id = org_a = org_b = None
    try:
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            user = models.User(
                email=f"u-{uuid.uuid4().hex[:8]}@example.com", name="Multi", timezone="UTC"
            )
            a = models.Organization(name="Own Org", slug=f"a-{uuid.uuid4().hex[:8]}")
            b = models.Organization(name="Team Org", slug=f"b-{uuid.uuid4().hex[:8]}")
            db.add_all([user, a, b])
            await db.flush()
            user_id, org_a, org_b = user.id, a.id, b.id
            db.add_all(
                [
                    models.Membership(organization_id=org_a, user_id=user_id, role="owner"),
                    models.Membership(organization_id=org_b, user_id=user_id, role="member"),
                ]
            )
            await db.commit()

        async with db_session() as session:
            orgs = await user_organizations(session, user_id)
            owner_role = await role_in_org(session, user_id, org_a)
            member_role = await role_in_org(session, user_id, org_b)
            stranger = await role_in_org(session, user_id, uuid.uuid4())

        assert {(o[0], o[3]) for o in orgs} == {(org_a, "owner"), (org_b, "member")}
        assert owner_role == "owner"
        assert member_role == "member"
        assert stranger is None
    finally:
        async with async_sessionmaker(admin_engine)() as db:
            for org in (org_a, org_b):
                if org is not None:
                    await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
            if user_id is not None:
                await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            await db.commit()
