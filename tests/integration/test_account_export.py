"""Account export against a live PostgreSQL. See ADR-0006 §5.

Two things matter here. Sealed content must come out *sealed* (the server cannot open it, and must
not pretend to), and no credential may ride along — an export lands in a Downloads folder.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.export import ExportService, UnknownUser
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.export_repository import SqlExportRepository
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration

NOW = datetime(2050, 1, 1, tzinfo=UTC)
START = datetime(2050, 6, 1, 10, 0, tzinfo=UTC)

SEALED_EVENT = "c2VhbGVkLWV2ZW50LWNvbnRlbnQ="
SEALED_TASK = "c2VhbGVkLXRhc2stY29udGVudA=="
SEALED_INVITEE = "c2VhbGVkLWludml0ZWUtYW5zd2Vycw=="
CALDAV_PASSWORD = "sup3r-secret-caldav-password"


@dataclass
class Fixture:
    org: uuid.UUID
    user: uuid.UUID
    email: str


def _service(session: object) -> ExportService:
    return ExportService(SqlExportRepository(session))  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def account(admin_engine: AsyncEngine) -> AsyncIterator[Fixture]:
    """One user with a bit of every kind of data: sealed content and a CalDAV credential."""
    suffix = uuid.uuid4().hex[:8]
    maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with maker() as s:
        org = models.Organization(name="Org", slug=f"exp-{suffix}")
        user = models.User(
            email=f"exp-{suffix}@example.com", name="Exporter", timezone="Europe/Zurich"
        )
        s.add_all([org, user])
        await s.flush()
        s.add(models.Membership(organization_id=org.id, user_id=user.id, role="owner"))

        calendar = models.Calendar(organization_id=org.id, owner_id=user.id, name="Personal")
        schedule = models.AvailabilitySchedule(
            organization_id=org.id, owner_id=user.id, name="Work", timezone="Europe/Zurich"
        )
        event_type = models.EventType(
            organization_id=org.id,
            owner_id=user.id,
            slug=f"intro-{suffix}",
            title="Intro call",
            duration_min=30,
            slot_interval_min=30,
        )
        s.add_all([calendar, schedule, event_type])
        await s.flush()

        s.add_all(
            [
                models.CalendarEvent(
                    organization_id=org.id,
                    owner_id=user.id,
                    calendar_id=calendar.id,
                    start_at=START,
                    end_at=START + timedelta(hours=1),
                    timezone="Europe/Zurich",
                    content=SEALED_EVENT,
                ),
                models.Task(organization_id=org.id, owner_id=user.id, content=SEALED_TASK),
                models.AvailabilityRule(
                    organization_id=org.id,
                    schedule_id=schedule.id,
                    weekday=0,
                    start_time=time(9, 0),
                    end_time=time(18, 0),
                ),
                models.Booking(
                    organization_id=org.id,
                    event_type_id=event_type.id,
                    host_id=user.id,
                    invitee_email="invitee@example.com",
                    invitee_timezone="UTC",
                    start_at=START,
                    end_at=START + timedelta(minutes=30),
                    status="confirmed",
                    invitee_private=SEALED_INVITEE,
                ),
                models.CaldavConnection(
                    organization_id=org.id,
                    user_id=user.id,
                    server_url="https://caldav.example.com",
                    username="exporter",
                    password_encrypted=CALDAV_PASSWORD,
                    calendar_url="https://caldav.example.com/cal",
                    calendar_name="Work",
                ),
                models.CalendarSubscription(
                    organization_id=org.id,
                    owner_id=user.id,
                    name="Holidays",
                    url="https://example.com/holidays.ics",
                ),
            ]
        )
        await s.commit()
        fixture = Fixture(org=org.id, user=user.id, email=user.email)
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


async def test_export_carries_every_kind_of_record(account: Fixture) -> None:
    async with db_session() as s:
        export = await _service(s).export(account.user)

    assert export.profile.email == account.email
    assert export.profile.timezone == "Europe/Zurich"
    assert [o.id for o in export.organizations] == [account.org]

    assert len(export.calendars) == 1
    assert export.calendars[0].name == "Personal"
    assert len(export.calendars[0].events) == 1

    assert len(export.tasks) == 1
    assert len(export.bookings) == 1
    assert export.bookings[0].event_type_title == "Intro call"
    assert export.bookings[0].invitee_email == "invitee@example.com"  # decrypted at rest, as always

    assert len(export.event_types) == 1
    assert len(export.schedules) == 1
    assert [r.weekday for r in export.schedules[0].rules] == [0]
    assert len(export.subscriptions) == 1
    assert len(export.caldav_connections) == 1


async def test_sealed_content_stays_sealed(account: Fixture) -> None:
    """The server holds ciphertext and hands it over as such. Opening it is the browser's job."""
    async with db_session() as s:
        export = await _service(s).export(account.user)

    assert export.calendars[0].events[0].content_sealed == SEALED_EVENT
    assert export.tasks[0].content_sealed == SEALED_TASK
    assert export.bookings[0].invitee_private_sealed == SEALED_INVITEE


async def test_every_sealed_record_says_which_organization_seals_it(account: Fixture) -> None:
    """Sealing is per-organization, so a sealed record must carry its org or it cannot be opened.

    A user may belong to several organizations, each with its own keypair. Without this, the browser
    would hold a pile of ciphertext and no way to tell which key opens which blob — the export would
    be undecryptable exactly where it matters most.
    """
    async with db_session() as s:
        export = await _service(s).export(account.user)

    assert export.calendars[0].organization_id == account.org
    assert export.tasks[0].organization_id == account.org
    assert export.bookings[0].organization_id == account.org


async def test_export_carries_no_credential(account: Fixture) -> None:
    """An export ends up in a Downloads folder. Nothing secret may ride along."""
    async with db_session() as s:
        export = await _service(s).export(account.user)

    connection = export.caldav_connections[0]
    assert connection.username == "exporter"
    assert not hasattr(connection, "password_encrypted")

    # Belt and braces: the CalDAV password must not appear anywhere in the serialized payload.
    assert CALDAV_PASSWORD not in repr(export)


async def test_unknown_user_is_rejected(admin_engine: AsyncEngine) -> None:
    # admin_engine is not used, but depending on it is what skips this test when no database is
    # reachable (CI without infra) — every other test here gets that for free through a fixture.
    with pytest.raises(UnknownUser):
        async with db_session() as s:
            await _service(s).export(uuid.uuid4())
