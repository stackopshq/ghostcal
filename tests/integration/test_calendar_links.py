"""Public calendar links, against a live PostgreSQL. See ADR-0009.

ADR-0005 parked cross-org sharing with "grant them the org key". These tests exist partly to make
sure nobody ever does: the org key opens every calendar, every task and every invitee's answers in
the organization. A link must open **one calendar** and nothing else, and that is what is checked
here — including the negative, which is the part that matters.
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

from ghostcal.application.calendar import EventInput, create_event, update_event
from ghostcal.application.links import SealedCopy, hash_token, new_token
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.links_repository import SqlLinkRepository
from ghostcal.infrastructure.db.session import db_session, org_session

pytestmark = pytest.mark.integration

START = datetime(2050, 6, 1, 10, 0, tzinfo=UTC)

ORG_SEALED = "c2VhbGVkLXRvLXRoZS1vcmc="
LINK_SEALED = "c2VhbGVkLXRvLXRoZS1saW5r"
LINK_PUBLIC = "bGluay1wdWJsaWMta2V5"


@dataclass
class Fixture:
    org: uuid.UUID
    owner: uuid.UUID
    calendar: uuid.UUID
    private_calendar: uuid.UUID


@pytest_asyncio.fixture
async def org(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """An owner with two calendars: one they will share by link, one they will not."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        organization = models.Organization(name="Org", slug=f"lk-{suffix}")
        owner = models.User(email=f"me-{suffix}@example.com", name="Kevin", timezone="UTC")
        s.add_all([organization, owner])
        await s.flush()
        s.add(models.Membership(organization_id=organization.id, user_id=owner.id, role="owner"))
        shared = models.Calendar(organization_id=organization.id, owner_id=owner.id, name="Shared")
        private = models.Calendar(
            organization_id=organization.id, owner_id=owner.id, name="Private"
        )
        s.add_all([shared, private])
        await s.commit()
        fixture = Fixture(
            org=organization.id,
            owner=owner.id,
            calendar=shared.id,
            private_calendar=private.id,
        )
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": fixture.org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": fixture.owner})
            await s.commit()


def _input(calendar_id: uuid.UUID, content: str = ORG_SEALED) -> EventInput:
    return EventInput(
        calendar_id=calendar_id,
        start_at=START,
        end_at=START + timedelta(hours=1),
        timezone="UTC",
        content=content,
    )


async def _make_link(fixture: Fixture) -> tuple[uuid.UUID, str]:
    token = new_token()
    async with org_session(fixture.org) as s:
        link_id = await SqlLinkRepository(s, fixture.org).create(
            fixture.owner,
            fixture.calendar,
            token_hash=hash_token(token),
            public_key=LINK_PUBLIC,
            name="For Sam",
        )
    assert link_id is not None
    return link_id, token


async def _visit(token: str):
    # No org session: a visitor has no organization. This is exactly how the endpoint reaches it.
    async with db_session() as s:
        return await SqlLinkRepository(s, uuid.UUID(int=0)).public_calendar(hash_token(token))


async def test_a_fresh_link_shows_an_empty_calendar(org: Fixture) -> None:
    """Minting a link shares nothing on its own — the sealed copies do not exist yet, and only the
    owner's browser can make them. The pending count is what says so."""
    async with org_session(org.org) as s:
        await create_event(SqlCalendarRepository(s, org.org), org.owner, _input(org.calendar))

    link_id, token = await _make_link(org)

    async with org_session(org.org) as s:
        links = await SqlLinkRepository(s, org.org).list_for_calendar(org.owner, org.calendar)
    assert [(link.id, link.pending) for link in links] == [(link_id, 1)]

    visited = await _visit(token)
    assert visited is not None
    assert visited.calendar_name == "Shared"
    assert visited.owner_name == "Kevin"
    assert visited.events == []


async def test_the_owner_seals_copies_and_the_visitor_reads_them(org: Fixture) -> None:
    async with org_session(org.org) as s:
        event_id = await create_event(
            SqlCalendarRepository(s, org.org), org.owner, _input(org.calendar)
        )
    link_id, token = await _make_link(org)

    # What the owner's browser is handed: the ORG-sealed content, to open and re-seal.
    async with org_session(org.org) as s:
        pending = await SqlLinkRepository(s, org.org).pending_seals(org.owner, link_id, limit=50)
    assert [(p.event_id, p.content) for p in pending] == [(event_id, ORG_SEALED)]

    async with org_session(org.org) as s:
        await SqlLinkRepository(s, org.org).store_copies(
            org.owner, link_id, [SealedCopy(event_id=event_id, content_sealed=LINK_SEALED)]
        )

    visited = await _visit(token)
    assert visited is not None
    assert len(visited.events) == 1
    # The visitor gets the copy sealed to the LINK key — never the one sealed to the org key.
    assert visited.events[0].content_sealed == LINK_SEALED
    assert ORG_SEALED not in [e.content_sealed for e in visited.events]

    async with org_session(org.org) as s:
        links = await SqlLinkRepository(s, org.org).list_for_calendar(org.owner, org.calendar)
    assert links[0].pending == 0


async def test_a_link_shows_that_calendar_and_no_other(org: Fixture) -> None:
    """The whole reason this is not "just hand them the org key". A link is one calendar."""
    async with org_session(org.org) as s:
        shared_event = await create_event(
            SqlCalendarRepository(s, org.org), org.owner, _input(org.calendar, "on-the-shared-one")
        )
        await create_event(
            SqlCalendarRepository(s, org.org),
            org.owner,
            _input(org.private_calendar, "on-the-private-one"),
        )
    link_id, token = await _make_link(org)

    # The link only ever offers events from its own calendar to be sealed.
    async with org_session(org.org) as s:
        pending = await SqlLinkRepository(s, org.org).pending_seals(org.owner, link_id, limit=50)
    assert [p.event_id for p in pending] == [shared_event]

    async with org_session(org.org) as s:
        await SqlLinkRepository(s, org.org).store_copies(
            org.owner, link_id, [SealedCopy(event_id=shared_event, content_sealed=LINK_SEALED)]
        )

    visited = await _visit(token)
    assert visited is not None
    assert len(visited.events) == 1
    assert "on-the-private-one" not in str(visited)


async def test_changing_an_event_invalidates_its_copies(org: Fixture) -> None:
    """A stale copy is a lie. The trigger deletes it, which is what makes it pending again."""
    async with org_session(org.org) as s:
        event_id = await create_event(
            SqlCalendarRepository(s, org.org), org.owner, _input(org.calendar)
        )
    link_id, token = await _make_link(org)
    async with org_session(org.org) as s:
        await SqlLinkRepository(s, org.org).store_copies(
            org.owner, link_id, [SealedCopy(event_id=event_id, content_sealed=LINK_SEALED)]
        )
    assert len((await _visit(token)).events) == 1  # type: ignore[union-attr]

    async with org_session(org.org) as s:
        await update_event(
            SqlCalendarRepository(s, org.org),
            org.owner,
            event_id,
            _input(org.calendar, "changed-org-sealed"),
        )

    # The copy is gone rather than stale: the visitor sees nothing until the owner re-seals it,
    # which is the honest state. Showing them the old title would be worse.
    assert (await _visit(token)).events == []  # type: ignore[union-attr]
    async with org_session(org.org) as s:
        pending = await SqlLinkRepository(s, org.org).pending_seals(org.owner, link_id, limit=50)
    assert [(p.event_id, p.content) for p in pending] == [(event_id, "changed-org-sealed")]


async def test_revoking_a_link_closes_the_door(org: Fixture) -> None:
    async with org_session(org.org) as s:
        event_id = await create_event(
            SqlCalendarRepository(s, org.org), org.owner, _input(org.calendar)
        )
    link_id, token = await _make_link(org)
    async with org_session(org.org) as s:
        await SqlLinkRepository(s, org.org).store_copies(
            org.owner, link_id, [SealedCopy(event_id=event_id, content_sealed=LINK_SEALED)]
        )
    assert await _visit(token) is not None

    async with org_session(org.org) as s:
        assert await SqlLinkRepository(s, org.org).delete(org.owner, link_id)

    assert await _visit(token) is None


async def test_an_unknown_token_opens_nothing(org: Fixture) -> None:
    assert await _visit(new_token()) is None


async def test_only_the_token_hash_is_stored(org: Fixture, admin_engine: AsyncEngine) -> None:
    """The token lives in the URL; the database keeps a hash. A dump does not hand out the links."""
    _, token = await _make_link(org)

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        stored = (await s.execute(text("SELECT token_hash, public_key FROM calendar_links"))).one()

    assert stored.token_hash == hash_token(token)
    assert token not in stored.token_hash
    # And the PUBLIC key is stored, because it is public. The private half never arrived.
    assert stored.public_key == LINK_PUBLIC


async def test_a_member_cannot_link_a_colleagues_calendar(
    org: Fixture, admin_engine: AsyncEngine
) -> None:
    """RLS keeps other organizations out. Inside one, nothing else would stop this."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        colleague = models.User(email=f"other-{suffix}@example.com", name="Other", timezone="UTC")
        s.add(colleague)
        await s.flush()
        s.add(models.Membership(organization_id=org.org, user_id=colleague.id, role="member"))
        await s.commit()
        colleague_id = colleague.id

    async with org_session(org.org) as s:
        created = await SqlLinkRepository(s, org.org).create(
            colleague_id,
            org.calendar,  # not theirs
            token_hash=hash_token(new_token()),
            public_key=LINK_PUBLIC,
            name="sneaky",
        )
    assert created is None
