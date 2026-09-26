"""Booking retention against a live PostgreSQL. See ADR-0006.

The purge is the only periodic job that destroys data, so the tests care as much about what it must
*not* touch (future bookings, organizations with no window) as about what it removes.

**These run under the real privileges or they run not at all.** The defect they cover is caused by
who owns the schema: a `SECURITY DEFINER` function owned by a superuser is exempt from row-level
security, so on such a stack the purge works and proves nothing. That is not hypothetical — the
first attempt at this fix was declared green on exactly such a stack, and it did not work. Every
purge test below therefore checks the owner first and refuses to report a result it cannot stand
behind.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.retention import (
    MIN_RETENTION_DAYS,
    InvalidRetentionWindow,
    RetentionService,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.retention_repository import SqlRetentionRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.tasks import _purge_every_organization

pytestmark = pytest.mark.integration


async def _require_plain_owner(admin_engine: AsyncEngine) -> None:
    """Refuse to measure the purge on a schema owned by a superuser.

    A superuser bypasses row-level security outright, FORCE or not. On such a schema the
    enumeration sees every organization whether or not the policy allows it, the purge deletes, and
    a green result says nothing about production. Asserted here rather than assumed in whatever
    script built the stack: a correct setup that nothing checks goes back to being wrong.
    """
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        superuser = (
            await s.execute(
                text(
                    "SELECT r.rolsuper FROM pg_class c "
                    "JOIN pg_roles r ON r.oid = c.relowner "
                    "WHERE c.relname = 'organizations'"
                )
            )
        ).scalar_one()
    if not superuser:
        return
    reason = (
        "the schema is owned by a superuser, which bypasses row-level security: this stack "
        "cannot observe the defect these tests cover"
    )
    # The same shape as GHOSTCAL_TESTS_REQUIRE_DB: a skip is convenient for a contributor and
    # dangerous where the property is supposed to hold, so CI turns it into a failure.
    if os.environ.get("GHOSTCAL_TESTS_REQUIRE_PLAIN_OWNER") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


NOW = datetime.now(UTC)
LONG_AGO = NOW - timedelta(days=400)
RECENT = NOW - timedelta(days=5)
FUTURE = NOW + timedelta(days=30)


@dataclass
class Fixture:
    org: uuid.UUID
    user: uuid.UUID
    bookings: dict[str, uuid.UUID]


def _service(session: object) -> RetentionService:
    return RetentionService(SqlRetentionRepository(session))  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def org_with_history(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """An org with an old, a recent and a future booking, and no retention window set."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"ret-{suffix}")
        user = models.User(email=f"ret-{suffix}@example.com", name="Host", timezone="UTC")
        s.add_all([org, user])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=user.id, role="owner"))
        # Seed the way the application writes: with the tenant declared. `stamp_zk_generation` is
        # a BEFORE INSERT trigger that reads `organizations`, and being SECURITY DEFINER changes the
        # role it runs as, not the session it runs in — so on a schema owned by a plain role it sees
        # nothing here and leaves `zk_generation` NULL, and the insert is refused. Superuser or not
        # makes no difference to the caller; what matters is that the tenant is bound.
        await s.execute(
            text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org.id)}
        )
        event = models.EventType(
            organization_id=org.id,
            owner_id=user.id,
            slug=f"intro-{suffix}",
            title="Intro call",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add(event)
        await s.flush()

        bookings: dict[str, uuid.UUID] = {}
        for label, start in (("old", LONG_AGO), ("recent", RECENT), ("future", FUTURE)):
            booking = models.Booking(
                organization_id=org.id,
                event_type_id=event.id,
                host_id=user.id,
                invitee_email="invitee@example.com",
                invitee_timezone="UTC",
                start_at=start,
                end_at=start + timedelta(minutes=30),
                status="confirmed",
            )
            s.add(booking)
            await s.flush()
            bookings[label] = booking.id
        await s.commit()
        fixture = Fixture(org=org.id, user=user.id, bookings=bookings)
    try:
        yield fixture
    finally:
        async with maker() as s:
            await s.execute(text("DELETE FROM bookings WHERE organization_id = :o"), {"o": org.id})
            await s.execute(
                text("DELETE FROM event_types WHERE organization_id = :o"), {"o": org.id}
            )
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org.id})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": fixture.user})
            await s.commit()


async def _surviving(admin_engine: AsyncEngine, org: uuid.UUID) -> set[uuid.UUID]:
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        rows = (
            await s.execute(text("SELECT id FROM bookings WHERE organization_id = :o"), {"o": org})
        ).all()
    return {r.id for r in rows}


async def test_no_window_purges_nothing(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """The default is keep-forever. Nothing may be destroyed until someone asks for it."""
    await _require_plain_owner(admin_engine)
    results = await _purge_every_organization()

    assert all(r.organization_id != org_with_history.org for r in results)
    assert await _surviving(admin_engine, org_with_history.org) == set(
        org_with_history.bookings.values()
    )


async def test_purge_removes_only_bookings_past_the_window(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    await _require_plain_owner(admin_engine)
    async with org_session(org_with_history.org) as s:
        await _service(s).set(org_with_history.org, 90)

    # The worker's own path, loop included: the defect was in the enumeration, so a test that
    # called only the per-organization step would have passed against the broken version.
    results = await _purge_every_organization()

    purged = {r.organization_id: r.purged for r in results}
    assert purged[org_with_history.org] == 1  # the 400-day-old one, and nothing else

    surviving = await _surviving(admin_engine, org_with_history.org)
    assert org_with_history.bookings["old"] not in surviving
    assert org_with_history.bookings["recent"] in surviving
    assert org_with_history.bookings["future"] in surviving  # a future meeting is never "expired"


async def test_window_can_be_read_back_and_cleared(org_with_history: Fixture) -> None:
    async with org_session(org_with_history.org) as s:
        assert await _service(s).get(org_with_history.org) is None

    async with org_session(org_with_history.org) as s:
        assert await _service(s).set(org_with_history.org, 365) == 365
    async with org_session(org_with_history.org) as s:
        assert await _service(s).get(org_with_history.org) == 365

    async with org_session(org_with_history.org) as s:
        assert await _service(s).set(org_with_history.org, None) is None
    async with org_session(org_with_history.org) as s:
        assert await _service(s).get(org_with_history.org) is None


async def test_service_refuses_a_window_below_the_floor(org_with_history: Fixture) -> None:
    with pytest.raises(InvalidRetentionWindow):
        async with org_session(org_with_history.org) as s:
            await _service(s).set(org_with_history.org, MIN_RETENTION_DAYS - 1)


async def test_the_database_enforces_the_floor_too(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """The application guard is not the only one. A purge is irreversible; belt and braces.

    Written through the admin connection, which bypasses RLS and the service entirely — so what is
    exercised here is the check constraint alone.
    """
    maker = async_sessionmaker(admin_engine)
    with pytest.raises((IntegrityError, DBAPIError)):
        async with maker() as s:
            await s.execute(
                text("UPDATE organizations SET booking_retention_days = 1 WHERE id = :o"),
                {"o": org_with_history.org},
            )
            await s.commit()


async def test_the_scan_sees_nothing_until_it_declares_itself(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """Without the declaration, the enumeration is empty — and the purge deletes nothing.

    This is the failure mode the previous version shipped: an enumeration that returned an empty
    set and a purge that reported success having destroyed nothing. Both directions are pinned
    here, because only one of them was ever observed.
    """
    await _require_plain_owner(admin_engine)
    async with org_session(org_with_history.org) as s:
        await _service(s).set(org_with_history.org, 90)

    # No `bind_retention_scan`: exactly what a caller that forgot the declaration would do.
    async with db_session() as s:
        undeclared = (await s.execute(text("SELECT * FROM organizations_with_retention()"))).all()
    assert undeclared == []

    # And with the declaration, the same query in the same shape of session finds it.
    async with db_session() as s:
        declared = await SqlRetentionRepository(s).retention_windows()
    assert org_with_history.org in {w.organization_id for w in declared}

    # The bookings are all still there: nothing was destroyed while the scan was blind.
    assert await _surviving(admin_engine, org_with_history.org) == set(
        org_with_history.bookings.values()
    )


async def test_an_organization_without_a_window_stays_invisible_under_scan(
    org_with_history: Fixture, admin_engine: AsyncEngine
) -> None:
    """The scan widens sight to organizations that asked for a window, and to no others.

    Without this, the policy would be broader than its stated intention and nothing would say so:
    every organization would become enumerable the moment a background job declared a scan.
    """
    await _require_plain_owner(admin_engine)
    # The fixture leaves the window unset, which is the default: keep forever.
    async with db_session() as s:
        windows = await SqlRetentionRepository(s).retention_windows()
    assert org_with_history.org not in {w.organization_id for w in windows}

    # Set one, and it appears — so the absence above is the policy at work, not an empty database.
    async with org_session(org_with_history.org) as s:
        await _service(s).set(org_with_history.org, 90)
    async with db_session() as s:
        windows = await SqlRetentionRepository(s).retention_windows()
    assert org_with_history.org in {w.organization_id for w in windows}
