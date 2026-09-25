"""A calendar's colour can be changed after it exists.

It could be chosen at creation and never again, on all three things that carry one: a calendar of
your own, a subscribed feed, and a connected CalDAV calendar. So the only ways to fix a colour were
to delete the calendar — taking its events with it — or, for a connection, to disconnect and retype
the server password.

The gap was already known and written down. `set_subscription_blocking` exists precisely because
"un utilisateur qui a déjà ses abonnements devrait les supprimer et les recréer — donc perdre leur
couleur, leur place, et leur cache", and the colour was the one setting that argument never got
applied to.

These tests also pin the part that is easy to leave out of a PATCH: that it changes the row it was
given and refuses the one it was not.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.calendar import (
    CalendarNotFound,
    list_calendars,
    set_calendar_color,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.subscriptions import (
    SubscriptionInput,
    SubscriptionNotFound,
    list_subscriptions,
    set_subscription_color,
)
from ghostcal.application.two_factor import TwoFactorService
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.db.subscriptions_repository import SqlSubscriptionRepository
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


def _auth(session: object, mailer: CapturingMailer) -> AuthService:
    return AuthService(
        SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG, _two_factor(session)
    )  # type: ignore[arg-type]


async def _account(mailer: CapturingMailer, label: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Register, verify, and return (user_id, organization_id)."""
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.test"
    async with db_session() as s:
        user_id = await _auth(s, mailer).register(
            email=email, name="Colour User", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
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


async def test_a_calendar_can_be_recoloured_after_it_exists(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    user_id, org_id = await _account(mailer, "colour")
    try:
        async with org_session(org_id) as s:
            repo = SqlCalendarRepository(s, org_id)
            calendars = await list_calendars(repo, user_id)
            cal_id = calendars[0].id
            before = calendars[0].color

        async with org_session(org_id) as s:
            await set_calendar_color(SqlCalendarRepository(s, org_id), user_id, cal_id, "#ff2d95")

        async with org_session(org_id) as s:
            after = await list_calendars(SqlCalendarRepository(s, org_id), user_id)
        assert before != "#ff2d95", "pick a colour the calendar does not already have"
        assert next(c.color for c in after if c.id == cal_id) == "#ff2d95"
        # The rest of the calendar is untouched: a recolour is not a rewrite.
        assert next(c.name for c in after if c.id == cal_id) == calendars[0].name
    finally:
        await _cleanup(admin_engine, user_id)


async def test_recolouring_someone_elses_calendar_is_a_miss(admin_engine: AsyncEngine) -> None:
    """Ownership lives in the UPDATE's WHERE clause, so this must come back as "not found"."""
    mailer = CapturingMailer()
    mine, my_org = await _account(mailer, "owner")
    theirs, their_org = await _account(mailer, "other")
    try:
        async with org_session(their_org) as s:
            their_calendars = await list_calendars(SqlCalendarRepository(s, their_org), theirs)
            target = their_calendars[0].id
            was = their_calendars[0].color

        with pytest.raises(CalendarNotFound):
            async with org_session(my_org) as s:
                await set_calendar_color(SqlCalendarRepository(s, my_org), mine, target, "#ff2d95")

        async with org_session(their_org) as s:
            still = await list_calendars(SqlCalendarRepository(s, their_org), theirs)
        assert next(c.color for c in still if c.id == target) == was
    finally:
        await _cleanup(admin_engine, mine, theirs)


async def test_a_subscription_can_be_recoloured(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    user_id, org_id = await _account(mailer, "feed")
    try:
        # Straight to the repository rather than through `add_subscription`, which fetches the
        # feed on the way in. This test is about recolouring a row that exists; making it depend on
        # an outbound HTTP call would make it fail for a reason that has nothing to do with colour.
        async with org_session(org_id) as s:
            sub_id = await SqlSubscriptionRepository(s, org_id).add(
                user_id,
                SubscriptionInput(
                    name="Holidays",
                    url="https://example.test/holidays.ics",
                    color="#00d68f",
                    blocks_availability=False,
                ),
            )

        async with org_session(org_id) as s:
            await set_subscription_color(
                SqlSubscriptionRepository(s, org_id), sub_id, user_id, "#ffb020"
            )

        async with org_session(org_id) as s:
            subs = await list_subscriptions(SqlSubscriptionRepository(s, org_id), user_id)
        found = next(x for x in subs if x.id == sub_id)
        assert found.color == "#ffb020"
        # Recolouring must not disturb the setting the same PATCH route also carries.
        assert found.blocks_availability is False

        with pytest.raises(SubscriptionNotFound):
            async with org_session(org_id) as s:
                await set_subscription_color(
                    SqlSubscriptionRepository(s, org_id), uuid.uuid4(), user_id, "#ffb020"
                )
    finally:
        await _cleanup(admin_engine, user_id)


def _two_factor(session: object) -> TwoFactorService:
    """Le vrai service : ces tests doivent voir le second facteur tel qu'il tourne."""
    return TwoFactorService(
        SqlTwoFactorRepository(session),  # type: ignore[arg-type]
        PyotpEngine(),
        _CLOCK,
    )
