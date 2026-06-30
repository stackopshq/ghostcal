"""End-to-end auth flow against a live PostgreSQL, through the real adapters.

register → (login blocked) → verify → login → current_user → refresh (old revoked) → logout →
duplicate email rejected. Uses a capturing mailer to recover the verification token.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import (
    AuthConfig,
    AuthService,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidToken,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
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
        match = re.search(r"token=([^\"]+)", self.last_html)
        assert match is not None
        return match.group(1)


def _service(session: object, mailer: CapturingMailer) -> AuthService:
    return AuthService(SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG)  # type: ignore[arg-type]


async def test_full_auth_flow(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    email = f"user-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            user_id = await _service(s, mailer).register(
                email=email, name="Test User", password=PASSWORD, zk_keys=ZK_PLACEHOLDER
            )
        token = mailer.token()

        # Login is blocked until the email is verified.
        with pytest.raises(EmailNotVerified):
            async with db_session() as s:
                await _service(s, mailer).login(email=email, password=PASSWORD)

        async with db_session() as s:
            await _service(s, mailer).verify_email(token=token)

        async with db_session() as s:
            tokens = await _service(s, mailer).login(email=email, password=PASSWORD)

        async with db_session() as s:
            who = await _service(s, mailer).current_user(access_token=tokens.access_token)
        assert who.email == email
        assert who.email_verified is True

        # Refresh rotates: a new pair is issued and the old refresh token is now revoked.
        async with db_session() as s:
            rotated = await _service(s, mailer).refresh(refresh_token=tokens.refresh_token)
        with pytest.raises(InvalidToken):
            async with db_session() as s:
                await _service(s, mailer).refresh(refresh_token=tokens.refresh_token)

        # Logout revokes the current refresh token.
        async with db_session() as s:
            await _service(s, mailer).logout(refresh_token=rotated.refresh_token)
        with pytest.raises(InvalidToken):
            async with db_session() as s:
                await _service(s, mailer).refresh(refresh_token=rotated.refresh_token)

        # Wrong password is rejected.
        with pytest.raises(InvalidCredentials):
            async with db_session() as s:
                await _service(s, mailer).login(email=email, password="wrong-password")

        # Re-registering the same email is rejected.
        with pytest.raises(EmailAlreadyRegistered):
            async with db_session() as s:
                await _service(s, mailer).register(
                    email=email, name="Dup", password="another-password", zk_keys=ZK_PLACEHOLDER
                )
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
