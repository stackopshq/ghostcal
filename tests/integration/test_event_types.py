"""Event-type management against a live PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.event_types import (
    EventTypeInput,
    EventTypeInUse,
    EventTypeNotFound,
    create_event_type,
    delete_event_type,
    get_event_type,
    list_event_types,
    update_event_type,
)
from ghostcal.application.scheduling import get_booking_page
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.event_types_repository import SqlEventTypesRepository
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def org_owner(admin_engine: AsyncEngine) -> AsyncIterator[dict[str, uuid.UUID]]:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"org-{suffix}")
        owner = models.User(email=f"o-{suffix}@example.com", name="Owner", timezone="UTC")
        s.add_all([org, owner])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=owner.id, role="owner"))
        await s.commit()
        ids = {"org": org.id, "owner": owner.id}
    try:
        yield ids
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": ids["org"]})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids["owner"]})
            await s.commit()


def _input(title: str = "Intro call") -> EventTypeInput:
    return EventTypeInput(title=title, duration_min=30, slot_interval_min=30)


async def test_event_type_crud(org_owner: dict[str, uuid.UUID]) -> None:
    org, owner = org_owner["org"], org_owner["owner"]

    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        event_type_id = await create_event_type(repo, owner, _input())

    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        items = await list_event_types(repo, owner)
    assert len(items) == 1
    assert items[0].title == "Intro call"
    assert items[0].slug.startswith("intro-call-")
    assert items[0].organization_id == org

    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        await update_event_type(
            repo,
            event_type_id,
            owner,
            EventTypeInput(title="Deep dive", duration_min=60, slot_interval_min=15),
        )
        updated = await get_event_type(repo, event_type_id, owner)
    assert updated.title == "Deep dive"
    assert updated.duration_min == 60

    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        await delete_event_type(repo, event_type_id, owner)
        assert await list_event_types(repo, owner) == []


async def test_delete_blocked_when_booked(
    org_owner: dict[str, uuid.UUID], admin_engine: AsyncEngine
) -> None:
    org, owner = org_owner["org"], org_owner["owner"]

    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        event_type_id = await create_event_type(repo, owner, _input())

    # Seed a confirmed booking that references the event type (admin bypasses RLS).
    start = datetime(2027, 6, 7, 9, 0, tzinfo=UTC)
    async with async_sessionmaker(admin_engine)() as s:
        s.add(
            models.Booking(
                organization_id=org,
                event_type_id=event_type_id,
                host_id=owner,
                invitee_name="Inv",
                invitee_email="inv@example.com",
                invitee_timezone="UTC",
                start_at=start,
                end_at=start + timedelta(minutes=30),
                status="confirmed",
            )
        )
        await s.commit()

    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        with pytest.raises(EventTypeInUse):
            await delete_event_type(repo, event_type_id, owner)


async def test_owner_isolation(org_owner: dict[str, uuid.UUID]) -> None:
    org, owner = org_owner["org"], org_owner["owner"]
    stranger = uuid.uuid4()
    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        await create_event_type(repo, owner, _input())
        assert await list_event_types(repo, stranger) == []
        with pytest.raises(EventTypeNotFound):
            await get_event_type(repo, uuid.uuid4(), owner)


async def test_public_booking_page_lists_active(org_owner: dict[str, uuid.UUID]) -> None:
    org, owner = org_owner["org"], org_owner["owner"]
    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        await create_event_type(repo, owner, _input("Active one"))
        await create_event_type(
            repo, owner, EventTypeInput(title="Hidden", duration_min=30, active=False)
        )

    async with org_session(org) as session:
        page = await get_booking_page(SqlSchedulingRepository(session, org))

    assert page.organization_name == "Org"
    titles = [e.title for e in page.event_types]
    assert "Active one" in titles
    assert "Hidden" not in titles


async def test_event_type_id_by_slug(org_owner: dict[str, uuid.UUID]) -> None:
    org, owner = org_owner["org"], org_owner["owner"]
    async with org_session(org) as session:
        repo = SqlEventTypesRepository(session, org)
        event_type_id = await create_event_type(repo, owner, _input("By slug"))
        data = await get_event_type(repo, event_type_id, owner)

    async with org_session(org) as session:
        scheduling = SqlSchedulingRepository(session, org)
        assert await scheduling.get_event_type_id_by_slug(data.slug) == event_type_id
        assert await scheduling.get_event_type_id_by_slug("does-not-exist") is None
