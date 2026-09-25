"""A forgotten password can be recovered, and the calendar survives it.

The recovery phrase shown at sign-up had nothing to spend itself on: its envelope was stored,
`unlockWithRecovery` was written, and no code path ever reached either. Someone who forgot their
password was locked out permanently, with the means to get back in sitting unused in the database.

What these tests pin is the part that makes a reset worth having. A reset that only set a new
password would leave a working login in front of a calendar nothing can open -- the same failure as
a password change that forgets the envelopes. So the new envelopes travel with the new password, in
one request, and the test checks the org key still opens afterwards.
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
    InvalidToken,
    ZkRewrap,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec
from tests.integration.conftest import ZK_PLACEHOLDER

pytestmark = pytest.mark.integration

OLD_PASSWORD = "s3cret-passw0rd"
NEW_PASSWORD = "an0ther-s3cret-passw0rd"
_HASHER = Argon2PasswordHasher()
_CODEC = JwtAccessTokenCodec("test-secret-of-at-least-32-characters!", timedelta(minutes=15))
_CLOCK = SystemClock()
_CONFIG = AuthConfig(
    access_ttl=timedelta(minutes=15),
    refresh_ttl=timedelta(days=30),
    email_verification_ttl=timedelta(hours=24),
    frontend_base_url="http://localhost:3001",
    password_reset_ttl=timedelta(hours=1),
)


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, *, to: str, subject: str, html: str) -> None:
        self.sent.append(html)

    def token(self) -> str:
        assert self.sent, "no mail was sent, so there is no token to read"
        m = re.search(r"token=([^\"]+)", self.sent[-1])
        assert m is not None
        return m.group(1)


def _svc(session: object, mailer: CapturingMailer) -> AuthService:
    return AuthService(SqlAuthRepository(session), _HASHER, _CODEC, mailer, _CLOCK, _CONFIG)  # type: ignore[arg-type]


async def _verified_account(mailer: CapturingMailer) -> tuple[uuid.UUID, str]:
    email = f"reset-{uuid.uuid4().hex[:8]}@example.test"
    async with db_session() as s:
        user_id = await _svc(s, mailer).register(
            email=email, name="Reset User", password=OLD_PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
    async with db_session() as s:
        await _svc(s, mailer).verify_email(token=mailer.token())
    return user_id, email


async def _cleanup(admin_engine: AsyncEngine, user_id: uuid.UUID) -> None:
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        org = (
            await s.execute(
                text("SELECT organization_id FROM memberships WHERE user_id = :u"), {"u": user_id}
            )
        ).scalar()
        if org is not None:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
        await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await s.commit()


async def test_a_reset_replaces_the_password_and_the_key_envelopes(
    admin_engine: AsyncEngine,
) -> None:
    mailer = CapturingMailer()
    user_id, email = await _verified_account(mailer)
    try:
        async with db_session() as s:
            await _svc(s, mailer).request_password_reset(email=email)
        token = mailer.token()

        # The browser reads the envelopes with the link alone — it cannot log in yet. They are
        # sealed under the recovery phrase, so this hands out ciphertext and nothing else.
        async with db_session() as s:
            bundles = await _svc(s, mailer).zk_keys_for_reset(token=token)
        assert bundles, "the reset page has nothing to open without these"
        org_id = bundles[0].organization_id
        assert bundles[0].recovery_wrapped_private_key

        # Reading them must NOT spend the link: a wrong recovery phrase cannot burn it.
        async with db_session() as s:
            assert await _svc(s, mailer).zk_keys_for_reset(token=token)

        async with db_session() as s:
            await _svc(s, mailer).reset_password(
                token=token,
                new_password=NEW_PASSWORD,
                envelopes=[
                    ZkRewrap(
                        organization_id=org_id,
                        wrapped_private_key="cmUtd3JhcHBlZC1ieS10aGUtYnJvd3Nlcg==",
                        wrap_salt="bmV3LXNhbHQ=",
                    )
                ],
            )

        # The new password works...
        async with db_session() as s:
            assert await _svc(s, mailer).login(email=email, password=NEW_PASSWORD)
        # ...the old one does not...
        from ghostcal.application.auth import InvalidCredentials

        with pytest.raises(InvalidCredentials):
            async with db_session() as s:
                await _svc(s, mailer).login(email=email, password=OLD_PASSWORD)

        # ...and the envelope the browser sent is the one now on file. Without this the account
        # would log in fine and open nothing, which is the whole failure being undone here.
        async with db_session() as s:
            after = await _svc(s, mailer).get_zk_keys(user_id)
        assert after[0].wrapped_private_key == "cmUtd3JhcHBlZC1ieS10aGUtYnJvd3Nlcg=="
        assert after[0].wrap_salt == "bmV3LXNhbHQ="
    finally:
        await _cleanup(admin_engine, user_id)


async def test_a_reset_token_is_single_use(admin_engine: AsyncEngine) -> None:
    mailer = CapturingMailer()
    user_id, email = await _verified_account(mailer)
    try:
        async with db_session() as s:
            await _svc(s, mailer).request_password_reset(email=email)
        token = mailer.token()

        async with db_session() as s:
            await _svc(s, mailer).reset_password(
                token=token, new_password=NEW_PASSWORD, envelopes=[]
            )

        with pytest.raises(InvalidToken):
            async with db_session() as s:
                await _svc(s, mailer).reset_password(
                    token=token, new_password="a-third-passw0rd!", envelopes=[]
                )
        # And a spent link stops opening the envelopes too.
        with pytest.raises(InvalidToken):
            async with db_session() as s:
                await _svc(s, mailer).zk_keys_for_reset(token=token)
    finally:
        await _cleanup(admin_engine, user_id)


async def test_an_unknown_address_says_nothing(admin_engine: AsyncEngine) -> None:
    """No mail, no error: a route that answers differently is an enumeration oracle."""
    mailer = CapturingMailer()
    async with db_session() as s:
        await _svc(s, mailer).request_password_reset(email="nobody-here@example.test")
    assert mailer.sent == []


async def test_an_unverified_address_gets_no_reset_link(admin_engine: AsyncEngine) -> None:
    """The link is proof of mailbox control, and an unverified address has never shown that."""
    mailer = CapturingMailer()
    email = f"unverified-{uuid.uuid4().hex[:8]}@example.test"
    async with db_session() as s:
        user_id = await _svc(s, mailer).register(
            email=email, name="Unverified", password=OLD_PASSWORD, zk_keys=ZK_PLACEHOLDER
        )
    try:
        mailer.sent.clear()  # drop the verification mail
        async with db_session() as s:
            await _svc(s, mailer).request_password_reset(email=email)
        assert mailer.sent == []
    finally:
        await _cleanup(admin_engine, user_id)
