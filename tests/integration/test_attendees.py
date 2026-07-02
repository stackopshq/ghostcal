"""Event attendees + RSVP against a live PostgreSQL: add, list, respond via the public path."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.attendees import (
    EventNotOwned,
    add_attendee,
    list_attendees,
    preview_invitation,
    remove_attendee,
    respond_invitation,
)
from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.calendar import EventInput, create_event, list_calendars
from ghostcal.application.ports.clock import SystemClock
from ghostcal.infrastructure.db.attendees_repository import (
    SqlAttendeeRepository,
    SqlInvitationGateway,
)
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


class Mailer:
    last_html: str | None = None

    async def send(self, *, to: str, subject: str, html: str) -> None:
        self.last_html = html

    def token(self) -> str:
        assert self.last_html is not None
        m = re.search(r"token=([^\"]+)", self.last_html)
        assert m is not None
        return m.group(1)


def _auth(session: object, mailer: Mailer) -> AuthService:
    return AuthService(SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG)  # type: ignore[arg-type]


async def _user_with_event(mailer: Mailer) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    email = f"att-{uuid.uuid4().hex[:8]}@example.test"
    async with db_session() as s:
        user_id = await _auth(s, mailer).register(
            email=email, name="Host", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
    async with db_session() as s:
        await _auth(s, mailer).verify_email(token=mailer.token())
    async with db_session() as s:
        membership = await primary_membership(s, user_id)
    assert membership is not None
    org_id, _ = membership
    async with org_session(org_id) as s:
        repo = SqlCalendarRepository(s, org_id)
        cal_id = (await list_calendars(repo, user_id))[0].id
        event_id = await create_event(
            repo,
            user_id,
            EventInput(
                calendar_id=cal_id,
                start_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
                end_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
                timezone="UTC",
                content="SEALED",
            ),
        )
    return user_id, org_id, event_id


async def _cleanup(engine: AsyncEngine, user_id: uuid.UUID) -> None:
    async with async_sessionmaker(engine)() as s:
        org = (
            await s.execute(
                text("SELECT organization_id FROM memberships WHERE user_id = :u"), {"u": user_id}
            )
        ).scalar_one_or_none()
        if org is not None:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
        await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await s.commit()


async def test_attendee_add_list_rsvp(admin_engine: AsyncEngine) -> None:
    user_id, org_id, event_id = await _user_with_event(Mailer())
    try:
        # Add a guest → get a one-time token; list shows needs_action.
        async with org_session(org_id) as s:
            added = await add_attendee(
                SqlAttendeeRepository(s, org_id),
                user_id,
                event_id,
                email="Guest@Example.com",
                name="Guest",
            )
        assert added.email == "guest@example.com"
        async with org_session(org_id) as s:
            rows = await list_attendees(SqlAttendeeRepository(s, org_id), user_id, event_id)
        assert len(rows) == 1 and rows[0].status == "needs_action"

        # Public preview (no org context) shows the event time + status, never the sealed title.
        async with db_session() as s:
            preview = await preview_invitation(SqlInvitationGateway(s), token=added.token)
        assert preview is not None
        assert preview.start_at == datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
        assert preview.status == "needs_action"

        # Respond accepted; the status flips.
        async with db_session() as s:
            ok = await respond_invitation(
                SqlInvitationGateway(s), token=added.token, status="accepted"
            )
        assert ok
        async with org_session(org_id) as s:
            rows = await list_attendees(SqlAttendeeRepository(s, org_id), user_id, event_id)
        assert rows[0].status == "accepted"

        # A bad token does nothing.
        async with db_session() as s:
            assert (
                await respond_invitation(SqlInvitationGateway(s), token="nope", status="declined")
                is False
            )

        # Remove the guest.
        async with org_session(org_id) as s:
            await remove_attendee(SqlAttendeeRepository(s, org_id), user_id, event_id, rows[0].id)
        async with org_session(org_id) as s:
            assert await list_attendees(SqlAttendeeRepository(s, org_id), user_id, event_id) == []
    finally:
        await _cleanup(admin_engine, user_id)


async def test_cannot_touch_another_users_event(admin_engine: AsyncEngine) -> None:
    owner_id, org_id, event_id = await _user_with_event(Mailer())
    other_id = uuid.uuid4()
    try:
        # A different owner_id in the same org can't add attendees to an event they don't own.
        async with org_session(org_id) as s:
            with pytest.raises(EventNotOwned):
                await add_attendee(
                    SqlAttendeeRepository(s, org_id),
                    other_id,
                    event_id,
                    email="x@example.com",
                    name=None,
                )
    finally:
        await _cleanup(admin_engine, owner_id)
