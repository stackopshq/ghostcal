"""Shared calendars against a live PostgreSQL: an owner shares a calendar; the member's agenda
includes its events (read-only), decryptable with the org key they already hold (ADR-0005)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.calendar import (
    EventInput,
    create_event,
    get_agenda,
    list_calendars,
    share_calendar,
)
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


async def _register(mailer: CapturingMailer, email: str) -> uuid.UUID:
    async with db_session() as s:
        uid = await _auth(s, mailer).register(
            email=email, name=email.split("@")[0], password=PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
    async with db_session() as s:
        await _auth(s, mailer).verify_email(token=mailer.token())
    return uid


async def test_shared_calendar_appears_in_members_agenda(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    suffix = uuid.uuid4().hex[:8]
    owner_id = member_id = None
    try:
        owner_id = await _register(mailer, f"calowner-{suffix}@example.test")
        member_id = await _register(mailer, f"calmember-{suffix}@example.test")

        async with db_session() as s:
            membership = await primary_membership(s, owner_id)
        assert membership is not None
        org_id, _ = membership

        # Put the member in the owner's organization (a team).
        async with async_sessionmaker(admin_engine)() as s:
            await s.execute(
                text(
                    "INSERT INTO memberships (organization_id, user_id, role) "
                    "VALUES (:o, :u, 'member')"
                ),
                {"o": org_id, "u": member_id},
            )
            await s.commit()

        window = (datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 2, tzinfo=UTC))
        async with org_session(org_id) as s:
            repo = SqlCalendarRepository(s, org_id)
            cal_id = (await list_calendars(repo, owner_id))[0].id
            await create_event(
                repo,
                owner_id,
                EventInput(
                    calendar_id=cal_id,
                    start_at=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
                    end_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                    timezone="UTC",
                    content="SEALED-SHARED-EVENT",
                ),
            )
            # Before sharing, the member sees nothing of the owner's calendar.
            assert await get_agenda(repo, member_id, *window) == []
            await share_calendar(repo, owner_id, cal_id, member_id)

        async with org_session(org_id) as s:
            member_agenda = await get_agenda(SqlCalendarRepository(s, org_id), member_id, *window)
            member_calendars = await list_calendars(SqlCalendarRepository(s, org_id), member_id)

        events = [i for i in member_agenda if i.source == "event"]
        assert len(events) == 1
        assert events[0].content == "SEALED-SHARED-EVENT"
        assert events[0].read_only is True  # the member may view but not edit it
        assert any(c.is_shared for c in member_calendars)
    finally:
        for uid in (member_id, owner_id):
            if uid is not None:
                async with async_sessionmaker(admin_engine)() as s:
                    org = (
                        await s.execute(
                            text("SELECT organization_id FROM memberships WHERE user_id = :u"),
                            {"u": uid},
                        )
                    ).scalar()
                    if org is not None:
                        await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
                    await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
                    await s.commit()
