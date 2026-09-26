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

from ghostcal.application.auth import (
    AuthConfig,
    AuthService,
    OidcIdentityRefused,
    ZkKeyMaterial,
    ZkKeysAlreadySet,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.two_factor import TwoFactorService
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.db.two_factor_repository import SqlTwoFactorRepository
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec
from ghostcal.infrastructure.security.totp import PyotpEngine
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
    return AuthService(
        SqlAuthRepository(session),  # type: ignore[arg-type]
        _HASHER,
        _CODEC,
        _NullMailer(),
        _CLOCK,
        _CONFIG,
        _two_factor(session),
    )


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
                provider="oidc",
                issuer=_ISSUER,
                subject=subject,
                email=email,
                name="Robin Vale",
                email_verified=True,
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
                provider="oidc",
                issuer=_ISSUER,
                subject=subject,
                email=email,
                name="Robin Vale",
                email_verified=True,
            )
        assert _CODEC.decode(pair2.access_token) == user_id
    finally:
        if user_id is not None:
            await _delete_user(admin_engine, user_id)


async def test_oidc_links_to_existing_email_account(admin_engine: AsyncEngine) -> None:
    email = f"link-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        # A pre-existing password account with this email, whose owner has *proved* they own it.
        # Verification is what makes adopting the account safe; see the squatting test below.
        async with db_session() as s:
            user_id = await _service(s).register(
                email=email, name="Pat", password="s3cret-passw0rd", zk_keys=ZK_PLACEHOLDER
            )
        await _verify(admin_engine, user_id)

        # OIDC login with the same (IdP-verified) email links to that account, not a new one.
        async with db_session() as s:
            pair = await _service(s).authenticate_oidc(
                provider="oidc",
                issuer=_ISSUER,
                subject=f"sub-{uuid.uuid4().hex[:10]}",
                email=email,
                name="Pat",
                email_verified=True,
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


async def _verify(admin_engine: AsyncEngine, user_id: uuid.UUID) -> None:
    """Mark an account's email verified, as clicking the verification link would."""
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        await s.execute(
            text("UPDATE users SET email_verified_at = now() WHERE id = :u"), {"u": user_id}
        )
        await s.commit()


async def test_an_unverified_idp_email_is_refused(admin_engine: AsyncEngine) -> None:
    """The email is what links an SSO login to an account and what proves ownership of an invited
    address. A provider that has not vouched for it has asserted nothing worth acting on."""
    email = f"unver-{uuid.uuid4().hex[:8]}@example.test"
    with pytest.raises(OidcIdentityRefused):
        async with db_session() as s:
            await _service(s).authenticate_oidc(
                provider="oidc",
                issuer=_ISSUER,
                subject=f"sub-{uuid.uuid4().hex[:10]}",
                email=email,
                name="Nobody",
                email_verified=False,
            )

    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        count = (
            await s.execute(text("SELECT count(*) FROM users WHERE email = :e"), {"e": email})
        ).scalar_one()
    assert count == 0  # and nothing was provisioned on the way to the refusal


async def test_a_squatted_unverified_account_is_not_adopted(admin_engine: AsyncEngine) -> None:
    """The other half of the takeover: an attacker registers the victim's address, never verifies
    it, and waits. Their registration wrapped that org's key under *their* passphrase, so adopting
    the row would seat the victim in the attacker's organization under a key the attacker holds.
    """
    email = f"squat-{uuid.uuid4().hex[:8]}@example.test"
    squatter_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            squatter_id = await _service(s).register(
                email=email, name="Mallory", password="s3cret-passw0rd", zk_keys=ZK_PLACEHOLDER
            )
        # Deliberately NOT verified — the victim never saw the mail.

        with pytest.raises(OidcIdentityRefused):
            async with db_session() as s:
                await _service(s).authenticate_oidc(
                    provider="oidc",
                    issuer=_ISSUER,
                    subject=f"sub-{uuid.uuid4().hex[:10]}",
                    email=email,
                    name="Victim",
                    email_verified=True,
                )

        maker = async_sessionmaker(admin_engine)
        async with maker() as s:
            linked = (
                await s.execute(
                    text("SELECT count(*) FROM identities WHERE user_id = :u"), {"u": squatter_id}
                )
            ).scalar_one()
        assert linked == 0
    finally:
        if squatter_id is not None:
            await _delete_user(admin_engine, squatter_id)


async def test_a_returning_identity_is_unaffected_by_the_email_checks(
    admin_engine: AsyncEngine,
) -> None:
    """Once the subject is bound, the email reasoning no longer applies — the binding was already
    established. A provider that stops sending the claim must not lock existing users out."""
    subject = f"sub-{uuid.uuid4().hex[:10]}"
    email = f"ret-{uuid.uuid4().hex[:8]}@example.test"
    user_id: uuid.UUID | None = None
    try:
        async with db_session() as s:
            first = await _service(s).authenticate_oidc(
                provider="oidc",
                issuer=_ISSUER,
                subject=subject,
                email=email,
                name="Ret",
                email_verified=True,
            )
        user_id = _CODEC.decode(first.access_token)

        async with db_session() as s:
            again = await _service(s).authenticate_oidc(
                provider="oidc",
                issuer=_ISSUER,
                subject=subject,
                email=email,
                name="Ret",
                email_verified=False,
            )
        assert _CODEC.decode(again.access_token) == user_id
    finally:
        if user_id is not None:
            await _delete_user(admin_engine, user_id)


def _two_factor(session: object) -> TwoFactorService:
    """Le vrai service : ces tests doivent voir le second facteur tel qu'il tourne."""
    return TwoFactorService(
        SqlTwoFactorRepository(session),  # type: ignore[arg-type]
        PyotpEngine(),
        _CLOCK,
    )
