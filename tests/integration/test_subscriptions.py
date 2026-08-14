"""Public ICS subscriptions against a live PostgreSQL: add a feed, refresh it, read the agenda.

``fetch_feed`` is monkeypatched so the test never hits the network; it exercises the persistence
and agenda-integration path (events surface as ``source="subscription"`` carrying the feed's UID
as ``calendar_id`` so the frontend colours/toggles them like a calendar).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application import subscriptions as subs_module
from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.calendar import get_agenda
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.subscriptions import (
    SubscriptionInput,
    add_subscription,
    list_subscriptions,
    refresh_subscription,
)
from ghostcal.infrastructure.calendars.ics_feed import FeedEvent
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.db.subscriptions_repository import SqlSubscriptionRepository
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec
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
    return AuthService(SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG)  # type: ignore[arg-type]


_FEED = [
    FeedEvent(
        uid="holiday-1@example.test",
        start_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
        all_day=False,
        summary="Team offsite",
    ),
    FeedEvent(
        uid="holiday-2@example.test",
        start_at=datetime(2026, 3, 26, 0, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 27, 0, 0, tzinfo=UTC),
        all_day=True,
        summary="Public holiday",
    ),
]


async def test_subscription_events_surface_in_agenda(
    admin_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(url: str) -> list[FeedEvent]:
        return list(_FEED)

    # add_subscription (validation) and refresh_subscription both resolve fetch_feed here.
    monkeypatch.setattr(subs_module, "fetch_feed", fake_fetch)

    mailer = CapturingMailer()
    email = f"sub-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            user_id = await _auth(s, mailer).register(
                email=email, name="Sub User", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
            )
        async with db_session() as s:
            await _auth(s, mailer).verify_email(token=mailer.token())
        async with db_session() as s:
            membership = await primary_membership(s, user_id)
        assert membership is not None
        org_id, _ = membership

        async with org_session(org_id) as s:
            repo = SqlSubscriptionRepository(s, org_id)
            sub_id = await add_subscription(
                repo,
                user_id,
                SubscriptionInput(
                    name="Holidays", url="https://example.test/holidays.ics", color="#00d68f"
                ),
            )
            stored = await refresh_subscription(repo, sub_id)
        assert stored == 2

        # The subscription is listed with an active status after a successful refresh.
        async with org_session(org_id) as s:
            listed = await list_subscriptions(SqlSubscriptionRepository(s, org_id), user_id)
        assert len(listed) == 1
        assert listed[0].status == "active"
        assert listed[0].last_error is None
        assert listed[0].last_synced_at is not None

        async with org_session(org_id) as s:
            agenda = await get_agenda(
                SqlCalendarRepository(s, org_id),
                user_id,
                datetime(2026, 3, 20, tzinfo=UTC),
                datetime(2026, 3, 31, tzinfo=UTC),
            )

        items = [i for i in agenda if i.source == "subscription"]
        assert len(items) == 2
        assert all(i.read_only for i in items)
        assert all(i.calendar_id == sub_id for i in items)  # so the overlay colours/toggles them
        by_title = {i.title: i for i in items}
        assert by_title["Team offsite"].all_day is False
        assert by_title["Public holiday"].all_day is True
    finally:
        if user_id is not None:
            maker = async_sessionmaker(admin_engine)
            async with maker() as s:
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


def test_webcal_url_is_rewritten_to_https():
    """Ce que le bouton « partager » d'un agenda donne réellement.

    Apple, Google et Outlook ne proposent pas d'URL `https://` pour un
    calendrier partagé : ils produisent un lien `webcal://`, qui désigne la
    même ressource en HTTPS. Le champ refusait donc exactement la forme que
    tout fournisseur donne, et le message parlait de « flux injoignable »
    alors que le flux répond — seul le préfixe gênait.
    """
    from ghostcal.presentation.schemas import SubscriptionIn

    s = SubscriptionIn(name="Agenda", url="webcal://p50-caldav.icloud.com/published/2/AAA")
    assert s.url == "https://p50-caldav.icloud.com/published/2/AAA"


def test_pasted_url_keeps_no_surrounding_space():
    """Un copier-coller depuis une feuille de partage ramène souvent un espace
    final, invisible à l'œil et fatal à la requête."""
    from ghostcal.presentation.schemas import SubscriptionIn

    s = SubscriptionIn(name="Agenda", url="  https://example.com/cal.ics\n")
    assert s.url == "https://example.com/cal.ics"


def test_a_scheme_that_is_neither_is_still_refused():
    """La tolérance porte sur `webcal`, pas sur n'importe quoi : `file://` ou
    `gopher://` restent des refus, sinon le garde anti-SSRF perd son sens."""
    import pytest as _pytest
    from pydantic import ValidationError

    from ghostcal.presentation.schemas import SubscriptionIn

    with _pytest.raises(ValidationError):
        SubscriptionIn(name="Agenda", url="file:///etc/passwd")
