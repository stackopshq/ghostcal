"""Who may write to a calendar, against a live PostgreSQL. Extends ADR-0005.

Sharing was read-only, and `calendar_shares.can_edit` existed in the schema but was written by
nothing and read by nothing. Making it real forces the access model to be stated properly, and the
statement is: **access is a property of the calendar, not of who created an event on it.** That is
the only rule that stays coherent once a shared calendar can be written to — an event an editor adds
to someone else's calendar has to be visible to its owner, and an owner-keyed rule hides it.

The first test here is not about the feature. It pins an authorization hole the feature exposed:
nothing ever checked that the calendar an event is created on belongs to the caller.
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

from ghostcal.application.calendar import (
    CalendarForbidden,
    EventInput,
    EventNotFound,
    create_event,
    delete_event,
    get_agenda,
    list_calendars,
    list_shares,
    share_calendar,
    update_event,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration

START = datetime(2050, 6, 1, 10, 0, tzinfo=UTC)


@dataclass
class Fixture:
    org: uuid.UUID
    owner: uuid.UUID
    editor: uuid.UUID
    reader: uuid.UUID
    calendar: uuid.UUID


@pytest_asyncio.fixture
async def org(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """One calendar, owned by `owner`; `editor` and `reader` are colleagues in the same org."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        organization = models.Organization(name="Org", slug=f"rw-{suffix}")
        owner = models.User(email=f"owner-{suffix}@example.com", name="Owner", timezone="UTC")
        editor = models.User(email=f"editor-{suffix}@example.com", name="Editor", timezone="UTC")
        reader = models.User(email=f"reader-{suffix}@example.com", name="Reader", timezone="UTC")
        s.add_all([organization, owner, editor, reader])
        await s.flush()
        s.add_all(
            [
                models.Membership(organization_id=organization.id, user_id=u.id, role="member")
                for u in (owner, editor, reader)
            ]
        )
        calendar = models.Calendar(
            organization_id=organization.id, owner_id=owner.id, name="Owner's calendar"
        )
        s.add(calendar)
        await s.commit()
        fixture = Fixture(
            org=organization.id,
            owner=owner.id,
            editor=editor.id,
            reader=reader.id,
            calendar=calendar.id,
        )
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": fixture.org})
            await s.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": [fixture.owner, fixture.editor, fixture.reader]},
            )
            await s.commit()


def _input(calendar_id: uuid.UUID, content: str = "sealed") -> EventInput:
    return EventInput(
        calendar_id=calendar_id,
        start_at=START,
        end_at=START + timedelta(hours=1),
        timezone="UTC",
        content=content,
    )


async def _share(fixture: Fixture, user: uuid.UUID, *, can_edit: bool) -> None:
    async with org_session(fixture.org) as s:
        await share_calendar(
            SqlCalendarRepository(s, fixture.org),
            fixture.owner,
            fixture.calendar,
            user,
            can_edit=can_edit,
        )


async def test_a_colleague_cannot_drop_an_event_onto_your_calendar(org: Fixture) -> None:
    """The hole this work exposed: nothing checked that the target calendar was the caller's.

    RLS scopes writes to the organization and stops there — inside one, the calendar id came
    straight off the request. A colleague could put an event on your calendar, and you would not
    even see it: visibility was keyed on who *created* an event, not on which calendar it sits on.
    """
    with pytest.raises(CalendarForbidden):
        async with org_session(org.org) as s:
            await create_event(SqlCalendarRepository(s, org.org), org.reader, _input(org.calendar))


async def test_a_read_only_share_can_see_and_cannot_touch(org: Fixture) -> None:
    await _share(org, org.reader, can_edit=False)

    async with org_session(org.org) as s:
        event_id = await create_event(
            SqlCalendarRepository(s, org.org), org.owner, _input(org.calendar)
        )

    # They see it, marked read-only.
    async with org_session(org.org) as s:
        items = await get_agenda(
            SqlCalendarRepository(s, org.org), org.reader, START, START + timedelta(days=1)
        )
    assert [i.read_only for i in items if i.source == "event"] == [True]

    # And they cannot change it, or remove it.
    with pytest.raises(CalendarForbidden):
        async with org_session(org.org) as s:
            await update_event(
                SqlCalendarRepository(s, org.org), org.reader, event_id, _input(org.calendar)
            )
    with pytest.raises(EventNotFound):
        async with org_session(org.org) as s:
            await delete_event(SqlCalendarRepository(s, org.org), org.reader, event_id)


async def test_an_editor_can_add_change_and_remove(org: Fixture) -> None:
    await _share(org, org.editor, can_edit=True)

    async with org_session(org.org) as s:
        event_id = await create_event(
            SqlCalendarRepository(s, org.org), org.editor, _input(org.calendar, "sealed-by-editor")
        )

    # It is not read-only to them — the calendar is writable, so everything on it is.
    async with org_session(org.org) as s:
        items = await get_agenda(
            SqlCalendarRepository(s, org.org), org.editor, START, START + timedelta(days=1)
        )
    assert [i.read_only for i in items if i.source == "event"] == [False]

    async with org_session(org.org) as s:
        await update_event(
            SqlCalendarRepository(s, org.org), org.editor, event_id, _input(org.calendar, "changed")
        )
    async with org_session(org.org) as s:
        await delete_event(SqlCalendarRepository(s, org.org), org.editor, event_id)

    async with org_session(org.org) as s:
        items = await get_agenda(
            SqlCalendarRepository(s, org.org), org.owner, START, START + timedelta(days=1)
        )
    assert [i for i in items if i.source == "event"] == []


async def test_the_owner_sees_what_an_editor_added_to_their_calendar(org: Fixture) -> None:
    """The reason access had to become calendar-based rather than owner-based.

    Under the old rule — "events I created, plus calendars shared with me" — an event the editor
    put on the owner's calendar would have been invisible to the owner: not created by them, and
    their own calendar is not "shared with" them. It would sit there and they would never know.
    """
    await _share(org, org.editor, can_edit=True)

    async with org_session(org.org) as s:
        await create_event(
            SqlCalendarRepository(s, org.org), org.editor, _input(org.calendar, "sealed-by-editor")
        )

    async with org_session(org.org) as s:
        items = await get_agenda(
            SqlCalendarRepository(s, org.org), org.owner, START, START + timedelta(days=1)
        )

    events = [i for i in items if i.source == "event"]
    assert len(events) == 1
    assert events[0].content == "sealed-by-editor"
    assert events[0].read_only is False  # it is the owner's calendar, after all


async def test_a_share_can_be_upgraded_and_downgraded(org: Fixture) -> None:
    """Re-sharing is how the owner changes their mind. A silent no-op would leave them believing
    they had granted edit when they had not."""
    await _share(org, org.editor, can_edit=False)

    async with org_session(org.org) as s:
        shares = await list_shares(SqlCalendarRepository(s, org.org), org.owner, org.calendar)
    assert [(s.name, s.can_edit) for s in shares] == [("Editor", False)]

    await _share(org, org.editor, can_edit=True)
    async with org_session(org.org) as s:
        shares = await list_shares(SqlCalendarRepository(s, org.org), org.owner, org.calendar)
    assert [(s.name, s.can_edit) for s in shares] == [("Editor", True)]

    # And back down: the editor loses the ability to write.
    await _share(org, org.editor, can_edit=False)
    with pytest.raises(CalendarForbidden):
        async with org_session(org.org) as s:
            await create_event(SqlCalendarRepository(s, org.org), org.editor, _input(org.calendar))


async def test_the_calendar_list_says_what_the_viewer_may_do_with_it(org: Fixture) -> None:
    """The UI needs this: an editable shared calendar must not be shown as read-only, and a
    read-only one must not offer an edit affordance that will 403."""
    await _share(org, org.editor, can_edit=True)
    await _share(org, org.reader, can_edit=False)

    async with org_session(org.org) as s:
        for_editor = await list_calendars(SqlCalendarRepository(s, org.org), org.editor)
        for_reader = await list_calendars(SqlCalendarRepository(s, org.org), org.reader)
        for_owner = await list_calendars(SqlCalendarRepository(s, org.org), org.owner)

    shared_to_editor = next(c for c in for_editor if c.is_shared)
    shared_to_reader = next(c for c in for_reader if c.is_shared)
    own = next(c for c in for_owner if not c.is_shared)

    assert shared_to_editor.can_edit is True
    assert shared_to_reader.can_edit is False
    assert own.can_edit is True  # a calendar you own is always writable
