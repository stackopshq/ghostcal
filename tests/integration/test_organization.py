"""Organization handle (slug) management against a live PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.organization import (
    HandleTaken,
    InvalidHandle,
    get_organization,
    update_organization,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.organization_repository import SqlOrganizationRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def org(admin_engine: AsyncEngine) -> AsyncIterator[dict[str, uuid.UUID]]:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    taken_slug = f"taken-{suffix}"
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"org-{suffix}")
        other = models.Organization(name="Other", slug=taken_slug)
        s.add_all([org, other])
        await s.commit()
        ids = {"org": org.id, "other": other.id}
    try:
        yield {**ids, "taken_slug": taken_slug}  # type: ignore[dict-item]
    finally:
        async with maker() as s:
            await s.execute(
                text("DELETE FROM organizations WHERE id = ANY(:ids)"),
                {"ids": [ids["org"], ids["other"]]},
            )
            await s.commit()


async def test_get_and_update(org: dict[str, uuid.UUID]) -> None:
    org_id = org["org"]
    async with org_session(org_id) as session:
        repo = SqlOrganizationRepository(session, org_id)
        current = await get_organization(repo)
        assert current.name == "Org"

        updated = await update_organization(repo, name="Kevin Allioli", slug="kevin")
    assert updated.name == "Kevin Allioli"
    assert updated.slug == "kevin"


async def test_invalid_handle_rejected(org: dict[str, uuid.UUID]) -> None:
    org_id = org["org"]
    async with org_session(org_id) as session:
        repo = SqlOrganizationRepository(session, org_id)
        for bad in ("Up", "with space", "Caps", "trailing-"):
            with pytest.raises(InvalidHandle):
                await update_organization(repo, name="X", slug=bad)


async def test_handle_taken(org: dict[str, uuid.UUID]) -> None:
    org_id = org["org"]
    async with org_session(org_id) as session:
        repo = SqlOrganizationRepository(session, org_id)
        with pytest.raises(HandleTaken):
            await update_organization(repo, name="X", slug=str(org["taken_slug"]))
