"""Publishing a calendar to CalDAV, against a live PostgreSQL.

The promise being tested is a negative one: the server relays cleartext and **stores none of it**.
Everything else here — the queue, the trigger, the deletes — exists to make that promise affordable,
because a server that cannot read an event cannot push one on a schedule either.
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

from ghostcal.application.calendar import EventInput, create_event, delete_event, update_event
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.push_repository import SqlPushRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

START = datetime(2050, 6, 1, 10, 0, tzinfo=UTC)
SEALED = "c2VhbGVkLWV2ZW50"


@dataclass
class Fixture:
    org: uuid.UUID
    user: uuid.UUID
    calendar: uuid.UUID
    other_calendar: uuid.UUID
    connection: uuid.UUID


@pytest_asyncio.fixture
async def org(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """A member with a connected CalDAV account and two calendars — one will publish, one won't."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        organization = models.Organization(name="Org", slug=f"ph-{suffix}")
        user = models.User(email=f"me-{suffix}@example.com", name="Me", timezone="UTC")
        s.add_all([organization, user])
        await s.flush()
        s.add(models.Membership(organization_id=organization.id, user_id=user.id, role="owner"))
        connection = models.CaldavConnection(
            organization_id=organization.id,
            user_id=user.id,
            server_url="https://dav.example.com",
            username="me",
            password_encrypted="enc",
            calendar_url="https://dav.example.com/cal",
            calendar_name="Phone",
        )
        published = models.Calendar(
            organization_id=organization.id, owner_id=user.id, name="Published"
        )
        private = models.Calendar(organization_id=organization.id, owner_id=user.id, name="Private")
        s.add_all([connection, published, private])
        await s.commit()
        fixture = Fixture(
            org=organization.id,
            user=user.id,
            calendar=published.id,
            other_calendar=private.id,
            connection=connection.id,
        )
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": fixture.org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": fixture.user})
            await s.commit()


def _input(calendar_id: uuid.UUID, content: str = SEALED) -> EventInput:
    return EventInput(
        calendar_id=calendar_id,
        start_at=START,
        end_at=START + timedelta(hours=1),
        timezone="UTC",
        content=content,
    )


async def _publish(fixture: Fixture, connection_id: uuid.UUID | None) -> int:
    async with org_session(fixture.org) as s:
        repo = SqlPushRepository(s, fixture.org)
        assert await repo.set_target(fixture.user, fixture.calendar, connection_id)
        return await repo.backfill(fixture.calendar) if connection_id else 0


async def _pending(fixture: Fixture) -> list:
    async with org_session(fixture.org) as s:
        return await SqlPushRepository(s, fixture.org).pending(fixture.user, limit=50)


async def test_a_calendar_that_publishes_nowhere_queues_nothing(org: Fixture) -> None:
    """The default. Nothing leaves the browser's reach unless it was asked to."""
    async with org_session(org.org) as s:
        await create_event(SqlCalendarRepository(s, org.org), org.user, _input(org.calendar))

    assert await _pending(org) == []


async def test_publishing_queues_what_is_already_there(org: Fixture) -> None:
    """A calendar that only publishes its future is not published."""
    async with org_session(org.org) as s:
        await create_event(SqlCalendarRepository(s, org.org), org.user, _input(org.calendar))
        await create_event(SqlCalendarRepository(s, org.org), org.user, _input(org.calendar))

    assert await _publish(org, org.connection) == 2

    pending = await _pending(org)
    assert len(pending) == 2
    assert {p.op for p in pending} == {"upsert"}
    # Still sealed. The server hands over ciphertext and lets the browser open it.
    assert {p.content for p in pending} == {SEALED}


async def test_a_write_queues_itself(org: Fixture) -> None:
    """The trigger, not the application: every write path gets it, including ones written later."""
    await _publish(org, org.connection)

    async with org_session(org.org) as s:
        event_id = await create_event(
            SqlCalendarRepository(s, org.org), org.user, _input(org.calendar)
        )
    pending = await _pending(org)
    assert [(p.op, p.content) for p in pending] == [("upsert", SEALED)]

    # An edit replaces the queued upsert rather than adding a second one.
    async with org_session(org.org) as s:
        await update_event(
            SqlCalendarRepository(s, org.org), org.user, event_id, _input(org.calendar, "changed")
        )
    pending = await _pending(org)
    assert [(p.op, p.content) for p in pending] == [("upsert", "changed")]


async def test_a_delete_survives_the_event_it_refers_to(org: Fixture) -> None:
    """The reason a queue exists at all: once the row is gone there is nothing left to mark, so the
    UID has to outlive it — otherwise the event stays on the phone forever."""
    await _publish(org, org.connection)

    async with org_session(org.org) as s:
        event_id = await create_event(
            SqlCalendarRepository(s, org.org), org.user, _input(org.calendar)
        )
    async with org_session(org.org) as s:
        await delete_event(SqlCalendarRepository(s, org.org), org.user, event_id)

    pending = await _pending(org)
    assert len(pending) == 1
    assert pending[0].op == "delete"
    assert pending[0].external_uid == f"ghostcal-evt-{event_id}"
    assert pending[0].content is None  # there is no event left to seal


async def test_an_unpublished_calendar_stays_out_of_the_queue(org: Fixture) -> None:
    await _publish(org, org.connection)

    async with org_session(org.org) as s:
        await create_event(SqlCalendarRepository(s, org.org), org.user, _input(org.other_calendar))

    assert await _pending(org) == []


async def test_unpublishing_stops_it(org: Fixture) -> None:
    await _publish(org, org.connection)
    await _publish(org, None)

    async with org_session(org.org) as s:
        await create_event(SqlCalendarRepository(s, org.org), org.user, _input(org.calendar))

    assert await _pending(org) == []


async def test_the_queue_holds_no_cleartext(org: Fixture, admin_engine: AsyncEngine) -> None:
    """The whole promise, at the storage layer.

    The browser hands the server a summary and a location at push time; the server relays them and
    writes none of it. So nothing in the queue — and nothing anywhere else — should ever contain a
    readable title. What is stored is a sealed blob and a UID.
    """
    await _publish(org, org.connection)
    async with org_session(org.org) as s:
        await create_event(
            SqlCalendarRepository(s, org.org),
            org.user,
            _input(org.calendar, "c2VhbGVkLXNlY3JldA=="),
        )

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        columns = (
            (
                await s.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'calendar_push_queue'"
                    )
                )
            )
            .scalars()
            .all()
        )

    # No summary, no description, no location. The queue points at a sealed event; it does not
    # describe one.
    assert set(columns) == {
        "id",
        "organization_id",
        "calendar_id",
        "event_id",
        "external_uid",
        "op",
        "created_at",
    }


async def test_done_removes_the_row(org: Fixture) -> None:
    """And only the caller's. A queue row is dropped after its write lands, never before — a failed
    push has to stay queued, which is the entire point of having one."""
    await _publish(org, org.connection)
    async with org_session(org.org) as s:
        await create_event(SqlCalendarRepository(s, org.org), org.user, _input(org.calendar))

    pending = await _pending(org)
    assert len(pending) == 1

    async with org_session(org.org) as s:
        await SqlPushRepository(s, org.org).done(org.user, pending[0].id)

    assert await _pending(org) == []
