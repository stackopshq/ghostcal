"""Task reminders against a live PostgreSQL: due task emails once (content-less), idempotently."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.task_reminders import dispatch_task_reminders
from ghostcal.application.tasks import TaskInput, create_task, set_task_completed
from ghostcal.application.two_factor import TwoFactorService
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.db.task_reminders_repository import SqlTaskReminderGateway
from ghostcal.infrastructure.db.tasks_repository import SqlTaskRepository
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
        self.sent: list[tuple[str, str, str]] = []
        self.last_html: str | None = None

    async def send(self, *, to: str, subject: str, html: str) -> None:
        self.sent.append((to, subject, html))
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


async def _register(mailer: CapturingMailer) -> uuid.UUID:
    email = f"taskrem-{uuid.uuid4().hex[:8]}@example.test"
    async with db_session() as s:
        user_id = await _auth(s, mailer).register(
            email=email, name="Reminder User", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
    async with db_session() as s:
        await _auth(s, mailer).verify_email(token=mailer.token())
    return user_id


async def test_task_reminder_sends_once(admin_engine: AsyncEngine) -> None:
    reg = CapturingMailer()
    user_id = await _register(reg)
    try:
        async with db_session() as s:
            membership = await primary_membership(s, user_id)
        assert membership is not None
        org_id, _ = membership

        # Task due in 5 minutes with a 10-minute reminder → the reminder moment already passed.
        due = datetime.now(UTC) + timedelta(minutes=5)
        async with org_session(org_id) as s:
            task_id = await create_task(
                SqlTaskRepository(s, org_id),
                user_id,
                TaskInput(content="SEALED", due_at=due, reminder_minutes=10),
            )

        mailer = CapturingMailer()
        async with db_session() as s:
            sent = await dispatch_task_reminders(SqlTaskReminderGateway(s), mailer)
        assert sent == 1
        _to, subject, html = mailer.sent[0]
        assert "SEALED" not in html and "SEALED" not in subject  # content-less (zero-knowledge)
        assert "task" in subject.lower()

        # Idempotent: a second scan sends nothing (reminded_at is set).
        async with db_session() as s:
            assert await dispatch_task_reminders(SqlTaskReminderGateway(s), CapturingMailer()) == 0

        # Completing the task keeps it silent (and it was already claimed anyway).
        async with org_session(org_id) as s:
            await set_task_completed(
                SqlTaskRepository(s, org_id), _CLOCK, user_id, task_id, completed=True
            )
        async with db_session() as s:
            assert await dispatch_task_reminders(SqlTaskReminderGateway(s), CapturingMailer()) == 0
    finally:
        async with async_sessionmaker(admin_engine)() as s:
            org = (
                await s.execute(
                    text("SELECT organization_id FROM memberships WHERE user_id = :u"),
                    {"u": user_id},
                )
            ).scalar_one_or_none()
            if org is not None:
                await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            await s.commit()


async def test_no_reminder_before_the_moment(admin_engine: AsyncEngine) -> None:
    reg = CapturingMailer()
    user_id = await _register(reg)
    try:
        async with db_session() as s:
            membership = await primary_membership(s, user_id)
        assert membership is not None
        org_id, _ = membership

        # Due in 2 hours with a 10-minute reminder → the reminder moment has NOT arrived yet.
        due = datetime.now(UTC) + timedelta(hours=2)
        async with org_session(org_id) as s:
            await create_task(
                SqlTaskRepository(s, org_id),
                user_id,
                TaskInput(content="SEALED", due_at=due, reminder_minutes=10),
            )
        async with db_session() as s:
            assert await dispatch_task_reminders(SqlTaskReminderGateway(s), CapturingMailer()) == 0
    finally:
        async with async_sessionmaker(admin_engine)() as s:
            org = (
                await s.execute(
                    text("SELECT organization_id FROM memberships WHERE user_id = :u"),
                    {"u": user_id},
                )
            ).scalar_one_or_none()
            if org is not None:
                await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            await s.commit()


def _two_factor(session: object) -> TwoFactorService:
    """Le vrai service : ces tests doivent voir le second facteur tel qu'il tourne."""
    return TwoFactorService(
        SqlTwoFactorRepository(session),  # type: ignore[arg-type]
        PyotpEngine(),
        _CLOCK,
    )
