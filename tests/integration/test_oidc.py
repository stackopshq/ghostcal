"""OIDC authentication against a live PostgreSQL: provisioning, idempotency, email-linking.

Exercises the application use case + the upsert_oidc_identity SECURITY DEFINER function (the Authlib
handshake itself is library code and not tested here). No password is ever involved.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.auth import AuthConfig, AuthService, ZkKeyMaterial, ZkKeysAlreadySet
from ghostcal.application.ports.clock import SystemClock
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec
from tests.integration.conftest import ZK_PLACEHOLDER

pytestmark = pytest.mark.integration

_HASHER = Argon2PasswordHasher()
_CODEC = JwtAccessTokenCodec("test-secret-of-at-least-32-characters!", timedelta(minutes=15))
_CLOCK = SystemClock()
_CONFIG = AuthConfig(
    access_ttl=timedelta(minutes=15),
    refresh_ttl=timedelta(days=30),
    email_verification_ttl=timedelta(hours=24),
    frontend_base_url="http://localhost:3001",
)
_ISSUER = "https://idp.example.test"


class _NullMailer:
    async def send(self, *, to: str, subject: str, html: str) -> None:  # pragma: no cover
        pass


def _service(session: object) -> AuthService:
    return AuthService(SqlAuthRepository(session), _HASHER, _CODEC, _NullMailer(), _CLOCK, _CONFIG)  # type: ignore[arg-type]


async def _delete_user(admin_engine: AsyncEngine, user_id: uuid.UUID) -> None:
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


async def test_oidc_provisions_once_and_is_idempotent(admin_engine: AsyncEngine) -> None:
    subject = f"sub-{uuid.uuid4().hex[:10]}"
    email = f"oidc-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            pair1 = await _service(s).authenticate_oidc(
                provider="oidc", issuer=_ISSUER, subject=subject, email=email, name="Robin Vale"
            )
        # The access token's subject is the provisioned user id.
        user_id = _CODEC.decode(pair1.access_token)

        maker = async_sessionmaker(admin_engine)
        async with maker() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT u.email_verified_at, u.email, "
                        "(SELECT count(*) FROM memberships m WHERE m.user_id = u.id) AS orgs, "
                        "(SELECT count(*) FROM identities i WHERE i.user_id = u.id) AS ids, "
                        "(SELECT count(*) FROM user_credentials c WHERE c.user_id = u.id) AS creds "
                        "FROM users u WHERE u.id = :u"
                    ),
                    {"u": user_id},
                )
            ).one()
        assert row.email == email
        assert row.email_verified_at is not None  # IdP-verified, no email round-trip
        assert row.orgs == 1
        assert row.ids == 1
        assert row.creds == 0  # passwordless account

        # A second login with the same identity returns the same user (no duplicate provisioning).
        async with db_session() as s:
            pair2 = await _service(s).authenticate_oidc(
                provider="oidc", issuer=_ISSUER, subject=subject, email=email, name="Robin Vale"
            )
        assert _CODEC.decode(pair2.access_token) == user_id
    finally:
        if user_id is not None:
            await _delete_user(admin_engine, user_id)


async def test_oidc_links_to_existing_email_account(admin_engine: AsyncEngine) -> None:
    email = f"link-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        # A pre-existing password account with this email.
        async with db_session() as s:
            user_id = await _service(s).register(
                email=email, name="Pat", password="s3cret-passw0rd", zk_keys=ZK_PLACEHOLDER
            )

        # OIDC login with the same (IdP-verified) email links to that account, not a new one.
        async with db_session() as s:
            pair = await _service(s).authenticate_oidc(
                provider="oidc",
                issuer=_ISSUER,
                subject=f"sub-{uuid.uuid4().hex[:10]}",
                email=email,
                name="Pat",
            )
        assert _CODEC.decode(pair.access_token) == user_id

        maker = async_sessionmaker(admin_engine)
        async with maker() as s:
            counts = (
                await s.execute(
                    text(
                        "SELECT (SELECT count(*) FROM users WHERE email = :e) AS users, "
                        "(SELECT count(*) FROM identities WHERE user_id = :u) AS ids"
                    ),
                    {"e": email, "u": user_id},
                )
            ).one()
        assert counts.users == 1  # linked, not duplicated
        assert counts.ids == 1
    finally:
        if user_id is not None:
            await _delete_user(admin_engine, user_id)


async def test_setup_zk_keys_refuses_to_overwrite(admin_engine: AsyncEngine) -> None:
    email = f"zk-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            user_id = await _service(s).register(
                email=email, name="Kim", password="s3cret-passw0rd", zk_keys=ZK_PLACEHOLDER
            )
        # register already stored keys, so a first-time setup must be rejected.
        material = ZkKeyMaterial(
            public_key="cHVi",
            wrapped_private_key="d3JhcA==",
            wrap_salt="c2FsdA==",
            recovery_wrapped_private_key="cmVj",
            recovery_salt="cnNhbHQ=",
        )
        async with db_session() as s:
            with pytest.raises(ZkKeysAlreadySet):
                await _service(s).setup_zk_keys(user_id, material)
    finally:
        if user_id is not None:
            await _delete_user(admin_engine, user_id)
