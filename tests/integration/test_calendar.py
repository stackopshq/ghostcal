"""Calendar agenda against a live PostgreSQL: create a recurring event, read the expanded agenda."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.calendar import EventInput, create_event, get_agenda, list_calendars
from ghostcal.application.ports.clock import SystemClock
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.session import db_session, org_session
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


async def test_calendar_agenda_expands_recurring_event(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    email = f"cal-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            user_id = await _auth(s, mailer).register(
                email=email, name="Cal User", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
            )
        async with db_session() as s:
            await _auth(s, mailer).verify_email(token=mailer.token())
        async with db_session() as s:
            membership = await primary_membership(s, user_id)
        assert membership is not None
        org_id, _ = membership

        # A default calendar is created on first listing; a weekly event is then expanded.
        async with org_session(org_id) as s:
            repo = SqlCalendarRepository(s, org_id)
            calendars = await list_calendars(repo, user_id)
            cal_id = calendars[0].id
            await create_event(
                repo,
                user_id,
                EventInput(
                    calendar_id=cal_id,
                    start_at=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),  # Mon 09:00 Europe/Zurich
                    end_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                    timezone="Europe/Zurich",
                    rrule="FREQ=WEEKLY;BYDAY=MO",
                    content="SEALED-CONTENT-BLOB",
                ),
            )

        async with org_session(org_id) as s:
            agenda = await get_agenda(
                SqlCalendarRepository(s, org_id),
                user_id,
                datetime(2026, 3, 20, tzinfo=UTC),
                datetime(2026, 4, 7, tzinfo=UTC),
            )

        events = [i for i in agenda if i.source == "event"]
        assert len(events) == 3  # three Mondays in the window
        assert all(i.content == "SEALED-CONTENT-BLOB" for i in events)
        # DST-correct: 09:00 Europe/Zurich is 08:00 UTC before, 07:00 UTC after 2026-03-29.
        starts = sorted(i.start for i in events)
        assert starts[0] == datetime(2026, 3, 23, 8, 0, tzinfo=UTC)
        assert starts[1] == datetime(2026, 3, 30, 7, 0, tzinfo=UTC)
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
