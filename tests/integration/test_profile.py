"""Profile use cases against a live PostgreSQL: update name/timezone, change password."""

from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService, InvalidCredentials
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.profile import InvalidTimezone, ProfileService
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec

pytestmark = pytest.mark.integration

PASSWORD = "s3cret-passw0rd"
NEW_PASSWORD = "n3w-passw0rd-rotated"
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
        match = re.search(r"token=([^\"]+)", self.last_html)
        assert match is not None
        return match.group(1)


def _auth(session: object, mailer: CapturingMailer) -> AuthService:
    return AuthService(SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG)  # type: ignore[arg-type]


def _profile(session: object) -> ProfileService:
    return ProfileService(SqlAuthRepository(session), _HASHER)  # type: ignore[arg-type]


async def test_profile_update_and_password_change(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    email = f"prof-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            user_id = await _auth(s, mailer).register(
                email=email, name="Init Name", password=PASSWORD
            )
        async with db_session() as s:
            await _auth(s, mailer).verify_email(token=mailer.token())

        # Default profile.
        async with db_session() as s:
            me = await _profile(s).get(user_id)
        assert me.name == "Init Name"
        assert me.timezone == "UTC"

        # Update name + timezone.
        async with db_session() as s:
            updated = await _profile(s).update(user_id, name="New Name", timezone="Europe/Zurich")
        assert updated.name == "New Name"
        assert updated.timezone == "Europe/Zurich"

        # Unknown timezone is rejected.
        with pytest.raises(InvalidTimezone):
            async with db_session() as s:
                await _profile(s).update(user_id, name="x", timezone="Mars/Phobos")

        # Wrong current password is rejected.
        with pytest.raises(InvalidCredentials):
            async with db_session() as s:
                await _profile(s).change_password(
                    user_id, current_password="wrong", new_password=NEW_PASSWORD
                )

        # Correct current password rotates it; login works with the new one.
        async with db_session() as s:
            await _profile(s).change_password(
                user_id, current_password=PASSWORD, new_password=NEW_PASSWORD
            )
        async with db_session() as s:
            tokens = await _auth(s, mailer).login(email=email, password=NEW_PASSWORD)
        assert tokens.access_token
    finally:
        if user_id is not None:
            maker = async_sessionmaker(admin_engine)
            async with maker() as s:
                org_id = (
                    await s.execute(
                        text("SELECT organization_id FROM memberships WHERE user_id = :u"),
                        {"u": user_id},
                    )
                ).scalar()
                if org_id is not None:
                    await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
                await s.commit()
