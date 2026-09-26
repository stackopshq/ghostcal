"""To-do tasks against a live PostgreSQL: create, list ordering, complete, update, delete."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.tasks import (
    TaskInput,
    TaskNotFound,
    create_task,
    delete_task,
    list_tasks,
    set_task_completed,
    update_task,
)
from ghostcal.application.two_factor import TwoFactorService
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.session import db_session, org_session
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


async def _register(mailer: CapturingMailer) -> uuid.UUID:
    email = f"task-{uuid.uuid4().hex[:8]}@example.test"
    async with db_session() as s:
        user_id = await _auth(s, mailer).register(
            email=email, name="Task User", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
    async with db_session() as s:
        await _auth(s, mailer).verify_email(token=mailer.token())
    return user_id


async def test_task_lifecycle(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    user_id = await _register(mailer)
    try:
        async with db_session() as s:
            membership = await primary_membership(s, user_id)
        assert membership is not None
        org_id, _ = membership

        soon = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
        later = datetime(2026, 5, 3, 9, 0, tzinfo=UTC)

        # Create two dated tasks and one undated.
        async with org_session(org_id) as s:
            repo = SqlTaskRepository(s, org_id)
            t_later = await create_task(repo, user_id, TaskInput(content="SEALED-B", due_at=later))
            await create_task(repo, user_id, TaskInput(content="SEALED-A", due_at=soon))
            await create_task(repo, user_id, TaskInput(content="SEALED-C", due_at=None))

        # Listing: incomplete first, then by due date ascending (nulls last).
        async with org_session(org_id) as s:
            tasks = await list_tasks(SqlTaskRepository(s, org_id), user_id)
        assert [t.content for t in tasks] == ["SEALED-A", "SEALED-B", "SEALED-C"]
        assert all(not t.completed for t in tasks)

        # Complete the later task; it drops below the incomplete ones and gets a completed_at.
        async with org_session(org_id) as s:
            await set_task_completed(
                SqlTaskRepository(s, org_id), _CLOCK, user_id, t_later, completed=True
            )
        async with org_session(org_id) as s:
            tasks = await list_tasks(SqlTaskRepository(s, org_id), user_id)
        done = next(t for t in tasks if t.id == t_later)
        assert done.completed and done.completed_at is not None
        assert tasks[-1].id == t_later  # completed sinks to the bottom

        # Update content + due date.
        async with org_session(org_id) as s:
            await update_task(
                SqlTaskRepository(s, org_id),
                user_id,
                t_later,
                TaskInput(content="SEALED-B2", due_at=None),
            )
        async with org_session(org_id) as s:
            tasks = await list_tasks(SqlTaskRepository(s, org_id), user_id)
        assert next(t for t in tasks if t.id == t_later).content == "SEALED-B2"

        # Delete; a second delete raises TaskNotFound.
        async with org_session(org_id) as s:
            await delete_task(SqlTaskRepository(s, org_id), user_id, t_later)
        with pytest.raises(TaskNotFound):
            async with org_session(org_id) as s:
                await delete_task(SqlTaskRepository(s, org_id), user_id, t_later)
        async with org_session(org_id) as s:
            tasks = await list_tasks(SqlTaskRepository(s, org_id), user_id)
        assert len(tasks) == 2
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
