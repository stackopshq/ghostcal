"""Several CalDAV accounts per member, against a live PostgreSQL.

Dropping "one calendar per person" makes two things ambiguous, and these tests are mostly about
those, because they are where it would go wrong quietly:

- **which calendar bookings mirror onto.** Two mirror targets would write every meeting to two
  external calendars, and the host would find out from their own phone, not from us.
- **which account an external event came from.** Without that, three connected calendars collapse
  into one anonymous "External" chip and the feature is pointless.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.calendar import get_agenda
from ghostcal.application.calendars import (
    MAX_CONNECTIONS,
    NotConnected,
    TooManyConnections,
    choose_mirror_target,
    connect_calendar,
    disconnect_calendar,
    list_connections,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.caldav_repository import SqlCaldavConnectionRepository
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

NOW = datetime(2050, 1, 1, tzinfo=UTC)


class FakeCipher:
    """The application encrypts before the repository sees it; that is all this needs to do."""

    def encrypt(self, plaintext: str) -> str:
        return f"enc:{plaintext}"

    def decrypt(self, token: str) -> str:
        return token.removeprefix("enc:")


@dataclass
class Fixture:
    org: uuid.UUID
    user: uuid.UUID
    other: uuid.UUID


@pytest_asyncio.fixture
async def org(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        organization = models.Organization(name="Org", slug=f"cd-{suffix}")
        user = models.User(email=f"me-{suffix}@example.com", name="Me", timezone="UTC")
        other = models.User(email=f"other-{suffix}@example.com", name="Other", timezone="UTC")
        s.add_all([organization, user, other])
        await s.flush()
        s.add_all(
            [
                models.Membership(organization_id=organization.id, user_id=user.id, role="owner"),
                models.Membership(organization_id=organization.id, user_id=other.id, role="member"),
            ]
        )
        await s.commit()
        fixture = Fixture(org=organization.id, user=user.id, other=other.id)
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": fixture.org})
            await s.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": [fixture.user, fixture.other]},
            )
            await s.commit()


async def _connect(fixture: Fixture, name: str, user_id: uuid.UUID | None = None) -> uuid.UUID:
    async with org_session(fixture.org) as s:
        repo = SqlCaldavConnectionRepository(s, fixture.org)
        return await connect_calendar(
            repo,
            FakeCipher(),
            user_id=user_id or fixture.user,
            server_url=f"https://{name}.example.com",
            username="me",
            password="secret",
            calendar_url=f"https://{name}.example.com/cal",
            calendar_name=name,
        )


async def _list(fixture: Fixture) -> list:
    async with org_session(fixture.org) as s:
        return await list_connections(SqlCaldavConnectionRepository(s, fixture.org), fixture.user)


async def test_several_calendars_connect_and_get_their_own_colour(org: Fixture) -> None:
    await _connect(org, "work")
    await _connect(org, "personal")
    await _connect(org, "family")

    connections = await _list(org)

    assert [c.calendar_name for c in connections] == ["work", "personal", "family"]
    # Distinct colours, or three overlays would be indistinguishable in the calendar.
    assert len({c.color for c in connections}) == 3


async def test_the_first_calendar_becomes_the_mirror_target_and_later_ones_do_not(
    org: Fixture,
) -> None:
    """Silently re-pointing where a host's meetings get written is not a thing to do for them."""
    await _connect(org, "work")
    await _connect(org, "personal")

    connections = await _list(org)
    assert [c.mirror_bookings for c in connections] == [True, False]


async def test_the_mirror_target_can_be_moved_and_only_one_ever_holds_it(org: Fixture) -> None:
    await _connect(org, "work")
    personal = await _connect(org, "personal")

    async with org_session(org.org) as s:
        await choose_mirror_target(SqlCaldavConnectionRepository(s, org.org), personal, org.user)

    connections = await _list(org)
    assert {c.calendar_name: c.mirror_bookings for c in connections} == {
        "work": False,
        "personal": True,
    }
    assert sum(c.mirror_bookings for c in connections) == 1


async def test_the_database_refuses_a_second_mirror_target(
    org: Fixture, admin_engine: AsyncEngine
) -> None:
    """The application clears the incumbent before setting the new one. If it ever forgot to, the
    host's meetings would be written to two external calendars — so the index, not the code, is what
    guarantees it. Written through the admin connection to exercise the index alone."""
    await _connect(org, "work")
    second = await _connect(org, "personal")

    maker = async_sessionmaker(admin_engine)
    with pytest.raises((IntegrityError, DBAPIError)):
        async with maker() as s:
            await s.execute(
                text("UPDATE caldav_connections SET mirror_bookings = true WHERE id = :c"),
                {"c": second},
            )
            await s.commit()


async def test_deleting_the_mirror_target_hands_the_job_to_another_calendar(org: Fixture) -> None:
    """Otherwise bookings would mirror nowhere, and nothing would say so."""
    work = await _connect(org, "work")
    await _connect(org, "personal")

    async with org_session(org.org) as s:
        await disconnect_calendar(SqlCaldavConnectionRepository(s, org.org), work, org.user)

    connections = await _list(org)
    assert [(c.calendar_name, c.mirror_bookings) for c in connections] == [("personal", True)]


async def test_a_member_cannot_touch_a_colleagues_calendar(org: Fixture) -> None:
    """RLS keeps other organizations out. Inside one, nothing else would stop this."""
    theirs = await _connect(org, "theirs", user_id=org.other)

    async with org_session(org.org) as s:
        repo = SqlCaldavConnectionRepository(s, org.org)
        assert await repo.get(theirs, org.user) is None

    with pytest.raises(NotConnected):
        async with org_session(org.org) as s:
            await disconnect_calendar(SqlCaldavConnectionRepository(s, org.org), theirs, org.user)


async def test_the_number_of_connected_calendars_is_capped(org: Fixture) -> None:
    """Each connection is a credential we hold and a server we poll on a schedule."""
    for i in range(MAX_CONNECTIONS):
        await _connect(org, f"cal-{i}")

    with pytest.raises(TooManyConnections):
        await _connect(org, "one-too-many")


async def test_the_agenda_says_which_account_an_external_event_came_from(
    org: Fixture, admin_engine: AsyncEngine
) -> None:
    """Without this, three connected calendars collapse into one anonymous chip."""
    work = await _connect(org, "work")
    personal = await _connect(org, "personal")

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        for connection, hour in ((work, 9), (personal, 14)):
            start = NOW.replace(hour=hour)
            await s.execute(
                # summary is encrypted at rest; NULL keeps this test about the connection id, which
                # is what actually matters here.
                text(
                    "INSERT INTO external_busy "
                    "(organization_id, connection_id, host_id, start_at, end_at, summary) "
                    "VALUES (:o, :c, :h, :s, :e, NULL)"
                ),
                {
                    "o": org.org,
                    "c": connection,
                    "h": org.user,
                    "s": start,
                    "e": start + timedelta(hours=1),
                },
            )
        await s.commit()

    async with org_session(org.org) as s:
        items = await get_agenda(
            SqlCalendarRepository(s, org.org),
            org.user,
            NOW,
            NOW + timedelta(days=1),
        )

    external = [i for i in items if i.source == "external"]
    assert len(external) == 2
    # calendar_id carries the source id — the same convention subscriptions already use.
    assert {i.calendar_id for i in external} == {work, personal}
