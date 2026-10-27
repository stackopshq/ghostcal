"""A calendar can be deleted, and what goes with it is decided here rather than discovered.

Until now nothing in GhostCal could delete a calendar — not the mobile app, not the web app, not
the API. `update_calendar`'s own docstring said the only fix for a wrong colour "was to delete the
calendar — which takes its events with it", describing a route that did not exist.

Deletion is not the mirror of creation, and these tests pin the four answers rather than leave them
to whoever writes the client:

  * **the events go with it.** Not moved to the default calendar: the server cannot read them —
    the content is sealed — so it cannot tell a years-old appointment from tomorrow's, and a silent
    flood into the one calendar someone actually looks at is worse than the deletion they asked
    for;
  * **the default calendar is refused**, and refused *by name*. `ensure_default_calendar` would
    make another one on the next read, so allowing it would destroy a year of events to produce an
    empty calendar with the same job;
  * **a shared calendar disappears for the people it was shared with.** A share is a view onto the
    owner's row, not a copy of it;
  * **someone else's calendar is not deletable**, and the refusal is the same one as for a
    calendar that does not exist — telling them apart would say whether a stranger's identifier is
    real.

Proved by putting each defect back. Dropping the `is_default` guard fails the second test; the
other three fail on their own terms. One mutation **passes**, and saying which is the point of
having run them: removing `owner_id` from the DELETE's WHERE clause changes nothing here, because
the SELECT above it already filters on the owner and returns before the delete is reached.

That clause is defence in depth against the window between the two statements, not something these
tests cover — a race needs two concurrent transactions to show itself, and none of this is written
to produce one. It stays because the rest of this repository puts ownership in the write's own
WHERE for exactly that reason; what is not claimed is that a test would notice if it went.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.calendar import (
    CalendarNotFound,
    DefaultCalendarUndeletable,
    EventInput,
    create_event,
    delete_calendar,
    list_calendars,
    share_calendar,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.two_factor import TwoFactorService
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.db.two_factor_repository import SqlTwoFactorRepository
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec
from ghostcal.infrastructure.security.totp import PyotpEngine
from tests.integration.conftest import ZK_PLACEHOLDER

pytestmark = pytest.mark.integration

PASSWORD = "s3cret-passw0rd"
_HASHER = Argon2PasswordHasher()
_CODEC = JwtAccessTokenCodec("test-secret-of-at-least-32-characters!", timedelta(minutes=15))
_CLOCK = SystemClock()
_CONFIG = AuthConfig(
    access_ttl=timedelta(minutes=15),
    refresh_ttl=timedelta(days=30),
    email_verification_ttl=timedelta(hours=24),
    frontend_base_url="http://localhost:3001",
)


class CapturingMailer:
    def __init__(self) -> None:
        self.last_html: str | None = None

    async def send(self, *, to: str, subject: str, html: str) -> None:
        self.last_html = html

    def token(self) -> str:
        assert self.last_html is not None
        m = re.search(r"token=([^\"]+)", self.last_html)
        assert m is not None
        return m.group(1)


def _two_factor(session: object) -> TwoFactorService:
    """Le vrai service : ces tests doivent voir le second facteur tel qu'il tourne."""
    return TwoFactorService(
        SqlTwoFactorRepository(session),  # type: ignore[arg-type]
        PyotpEngine(),
        _CLOCK,
    )


def _auth(session: object, mailer: CapturingMailer) -> AuthService:
    return AuthService(
        SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG, _two_factor(session)
    )  # type: ignore[arg-type]


async def _account(mailer: CapturingMailer, label: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Register, verify, and return (user_id, organization_id)."""
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.test"
    async with db_session() as s:
        user_id = await _auth(s, mailer).register(
            email=email, name="Delete User", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
    async with db_session() as s:
        await _auth(s, mailer).verify_email(token=mailer.token())
    async with db_session() as s:
        membership = await primary_membership(s, user_id)
    assert membership is not None
    return user_id, membership[0]


async def _cleanup(admin_engine: AsyncEngine, *user_ids: uuid.UUID) -> None:
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        for user_id in user_ids:
            org = (
                await s.execute(
                    text("SELECT organization_id FROM memberships WHERE user_id = :u"),
                    {"u": user_id},
                )
            ).scalar()
            if org is not None:
                await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await s.commit()


async def _second_calendar(org_id: uuid.UUID, user_id: uuid.UUID, name: str) -> uuid.UUID:
    """A calendar that is not the default one — the only kind that can be deleted."""
    async with org_session(org_id) as s:
        created = await SqlCalendarRepository(s, org_id).create_calendar(
            user_id, name=name, color="#ff2d95"
        )
    return created.id


async def _an_event(org_id: uuid.UUID, user_id: uuid.UUID, calendar_id: uuid.UUID) -> uuid.UUID:
    debut = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    async with org_session(org_id) as s:
        return await create_event(
            SqlCalendarRepository(s, org_id),
            user_id,
            EventInput(
                calendar_id=calendar_id,
                start_at=debut,
                end_at=debut + timedelta(hours=1),
                timezone="Europe/Zurich",
                content="scellé",
            ),
        )


async def _event_count(admin_engine: AsyncEngine, calendar_id: uuid.UUID) -> int:
    """Counted in the database, not through the API.

    The API would answer "no events" for a calendar it can no longer see, which is exactly what a
    calendar still full of rows would also look like. The question here is whether the rows are
    gone, and only the table can answer it.
    """
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM calendar_events WHERE calendar_id = :c"),
                {"c": calendar_id},
            )
        ).scalar_one()


async def test_a_calendar_is_deleted_with_its_events(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    user_id, org_id = await _account(mailer, "delete")
    try:
        cal_id = await _second_calendar(org_id, user_id, "Jetable")
        await _an_event(org_id, user_id, cal_id)
        assert await _event_count(admin_engine, cal_id) == 1, "l'événement doit exister d'abord"

        async with org_session(org_id) as s:
            await delete_calendar(SqlCalendarRepository(s, org_id), user_id, cal_id)

        async with org_session(org_id) as s:
            restants = await list_calendars(SqlCalendarRepository(s, org_id), user_id)
        assert cal_id not in {c.id for c in restants}
        assert await _event_count(admin_engine, cal_id) == 0, (
            "les événements doivent partir avec le calendrier, par la cascade de la base"
        )
    finally:
        await _cleanup(admin_engine, user_id)


async def test_the_default_calendar_is_refused_and_says_so(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    user_id, org_id = await _account(mailer, "defaut")
    try:
        async with org_session(org_id) as s:
            calendars = await list_calendars(SqlCalendarRepository(s, org_id), user_id)
        defaut = next(c for c in calendars if c.is_default)

        with pytest.raises(DefaultCalendarUndeletable):
            async with org_session(org_id) as s:
                await delete_calendar(SqlCalendarRepository(s, org_id), user_id, defaut.id)

        # **Le refus doit être distinct de « introuvable ».** Une suppression qui écarterait le
        # calendrier par défaut dans sa clause WHERE rendrait `CalendarNotFound`, et l'utilisateur
        # chercherait un calendrier qu'il a sous les yeux. Ce test échoue si les deux issues se
        # confondent, parce que `DefaultCalendarUndeletable` n'hérite pas de `CalendarNotFound`.
        async with org_session(org_id) as s:
            encore = await list_calendars(SqlCalendarRepository(s, org_id), user_id)
        assert defaut.id in {c.id for c in encore}, "le calendrier par défaut doit rester"
    finally:
        await _cleanup(admin_engine, user_id)


async def test_a_shared_calendar_goes_for_the_other_member_too(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    owner_id, org_id = await _account(mailer, "proprietaire")
    other_mailer = CapturingMailer()
    other_id, _ = await _account(other_mailer, "invite")
    try:
        cal_id = await _second_calendar(org_id, owner_id, "Partagé")
        async with org_session(org_id) as s:
            await share_calendar(SqlCalendarRepository(s, org_id), owner_id, cal_id, other_id)

        async with org_session(org_id) as s:
            vus = await list_calendars(SqlCalendarRepository(s, org_id), other_id)
        assert cal_id in {c.id for c in vus}, "le partage doit d'abord fonctionner"

        async with org_session(org_id) as s:
            await delete_calendar(SqlCalendarRepository(s, org_id), owner_id, cal_id)

        async with org_session(org_id) as s:
            apres = await list_calendars(SqlCalendarRepository(s, org_id), other_id)
        assert cal_id not in {c.id for c in apres}, (
            "un partage est une vue sur la ligne du propriétaire, pas une copie : il part avec elle"
        )
    finally:
        await _cleanup(admin_engine, owner_id, other_id)


async def test_someone_elses_calendar_is_not_deletable(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    owner_id, org_id = await _account(mailer, "cible")
    intruder_mailer = CapturingMailer()
    intruder_id, _ = await _account(intruder_mailer, "intrus")
    try:
        cal_id = await _second_calendar(org_id, owner_id, "Privé")

        # Même réponse que pour un calendrier inexistant, et c'est voulu : distinguer les deux
        # dirait si l'identifiant d'un inconnu existe.
        with pytest.raises(CalendarNotFound):
            async with org_session(org_id) as s:
                await delete_calendar(SqlCalendarRepository(s, org_id), intruder_id, cal_id)

        async with org_session(org_id) as s:
            encore = await list_calendars(SqlCalendarRepository(s, org_id), owner_id)
        assert cal_id in {c.id for c in encore}
    finally:
        await _cleanup(admin_engine, owner_id, intruder_id)


async def test_an_unknown_calendar_is_not_found(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    user_id, org_id = await _account(mailer, "inconnu")
    try:
        with pytest.raises(CalendarNotFound):
            async with org_session(org_id) as s:
                await delete_calendar(SqlCalendarRepository(s, org_id), user_id, uuid.uuid4())
    finally:
        await _cleanup(admin_engine, user_id)
