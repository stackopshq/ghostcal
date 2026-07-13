"""Authentication use cases (email/password).

Framework-free. Persistence is a port (``AuthRepository``); hashing, access-token encoding and
email sending are ports too. ``AuthService`` bundles them so routes and tests inject one object.

Tokens:
- access: short-lived JWT (bearer), encoded/decoded by the codec port.
- refresh: opaque random string returned to the client; only its SHA-256 hash is stored, and
  rotation revokes the previous one.
- email verification: opaque random string emailed as a link; only its hash is stored, single use.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from ghostcal.application.ports.clock import Clock
from ghostcal.application.ports.email import EmailSender
from ghostcal.application.ports.security import AccessTokenCodec, PasswordHasher


class AuthError(Exception):
    """Base class for authentication errors."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class EmailNotVerified(AuthError):
    pass


class InvalidToken(AuthError):
    pass


class ZkKeysAlreadySet(AuthError):
    """Refuse to overwrite existing zero-knowledge keys (would orphan encrypted data)."""


@dataclass(frozen=True, slots=True)
class AuthUserRecord:
    id: uuid.UUID
    email: str
    name: str
    timezone: str
    email_verified: bool
    password_hash: str | None
    avatar_url: str | None = None


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str
    name: str
    email_verified: bool


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


@dataclass(frozen=True, slots=True)
class AuthConfig:
    access_ttl: timedelta
    refresh_ttl: timedelta
    email_verification_ttl: timedelta
    frontend_base_url: str


@dataclass(frozen=True, slots=True)
class ZkKeyMaterial:
    """Zero-knowledge key material generated client-side at sign-up.

    All fields are base64 strings; the server stores them verbatim and can derive nothing from
    them (no private key, no password- or recovery-derived key). See ADR-0002.
    """

    public_key: str
    wrapped_private_key: str
    wrap_salt: str
    recovery_wrapped_private_key: str
    recovery_salt: str


@dataclass(frozen=True, slots=True)
class ZkKeyBundle:
    """One generation of one org key, as the browser needs it to unlock (ADR-0007).

    A user gets one of these per (org, generation), newest first. Exactly one route in is set:
    ``sealed_org_key`` (sealed to the user's own public key — generation >= 1), or the
    password-wrapped pair (generation 0). ``public_key`` is always the org's *current* one.
    """

    organization_id: uuid.UUID
    public_key: str
    generation: int
    # Generation >= 1: the org private key sealed to the user's own public key.
    sealed_org_key: str | None
    # Generation 0: wrapped under a key derived from the user's password.
    wrapped_private_key: str | None
    wrap_salt: str | None
    # NULL for keys received via a team grant (no recovery copy — re-grantable). See ADR-0003.
    recovery_wrapped_private_key: str | None
    recovery_salt: str | None


class AuthRepository:
    async def provision_account(
        self, *, email: str, name: str, password_hash: str, org_name: str, org_slug: str
    ) -> uuid.UUID:
        """Create user + credentials + org + owner membership atomically. Return the user id.
        Raise ``EmailAlreadyRegistered`` if the email is taken."""
        raise NotImplementedError

    async def upsert_oidc_identity(
        self,
        *,
        provider: str,
        issuer: str,
        subject: str,
        email: str,
        name: str,
        org_name: str,
        org_slug: str,
    ) -> uuid.UUID:
        """Resolve an OIDC login to a local user id: return the linked user, link to an existing
        account with the same email, or provision a fresh passwordless account. Return user id."""
        raise NotImplementedError

    async def store_zk_keys(self, user_id: uuid.UUID, material: ZkKeyMaterial) -> None:
        """Persist the wrapped zero-knowledge keys for the user's owner organization."""
        raise NotImplementedError

    async def get_zk_keys(self, user_id: uuid.UUID) -> list[ZkKeyBundle]:
        """All of the user's org keys (one per organization they can decrypt)."""
        raise NotImplementedError

    async def rewrap_zk_key(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        *,
        wrapped_private_key: str,
        wrap_salt: str,
    ) -> None:
        """Replace the password-wrapped private key for one org (after a password change)."""
        raise NotImplementedError

    async def get_by_email(self, email: str) -> AuthUserRecord | None:
        raise NotImplementedError

    async def get_by_id(self, user_id: uuid.UUID) -> AuthUserRecord | None:
        raise NotImplementedError

    async def update_profile(
        self, user_id: uuid.UUID, *, name: str, timezone: str, avatar_url: str | None
    ) -> None:
        raise NotImplementedError

    async def set_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        raise NotImplementedError

    async def add_email_verification(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        raise NotImplementedError

    async def consume_email_verification(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        """Mark an unused, unexpired token used and return its user id, else None."""
        raise NotImplementedError

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None:
        raise NotImplementedError

    async def add_refresh_token(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        raise NotImplementedError

    async def rotate_refresh_token(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        """Revoke a valid refresh token and return its user id, else None."""
        raise NotImplementedError

    async def revoke_refresh_token(self, token_hash: str, now: datetime) -> None:
        raise NotImplementedError


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


_dummy_hash_cache: str | None = None


def _dummy_hash(hasher: PasswordHasher) -> str:
    """A cached Argon2 hash used to equalize login timing for non-existent accounts."""
    global _dummy_hash_cache
    if _dummy_hash_cache is None:
        _dummy_hash_cache = hasher.hash("ghostcal-timing-equalizer")
    return _dummy_hash_cache


def _org_slug(email: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in email.split("@", 1)[0].lower())
    base = base.strip("-") or "team"
    return f"{base}-{secrets.token_hex(3)}"


class AuthService:
    def __init__(
        self,
        repo: AuthRepository,
        hasher: PasswordHasher,
        codec: AccessTokenCodec,
        mailer: EmailSender,
        clock: Clock,
        config: AuthConfig,
    ) -> None:
        self._repo = repo
        self._hasher = hasher
        self._codec = codec
        self._mailer = mailer
        self._clock = clock
        self._config = config

    async def register(
        self, *, email: str, name: str, password: str, zk_keys: ZkKeyMaterial
    ) -> uuid.UUID:
        email = email.strip().lower()
        password_hash = self._hasher.hash(password)
        user_id = await self._repo.provision_account(
            email=email,
            name=name,
            password_hash=password_hash,
            org_name=name or email,
            org_slug=_org_slug(email),
        )
        await self._repo.store_zk_keys(user_id, zk_keys)
        await self._send_verification(user_id, email)
        return user_id

    async def get_zk_keys(self, user_id: uuid.UUID) -> list[ZkKeyBundle]:
        return await self._repo.get_zk_keys(user_id)

    async def setup_zk_keys(self, user_id: uuid.UUID, material: ZkKeyMaterial) -> None:
        """First-time key setup (e.g. an SSO user choosing an encryption passphrase). Refuses to
        overwrite existing keys — that would orphan already-encrypted content."""
        if await self._repo.get_zk_keys(user_id):
            raise ZkKeysAlreadySet(str(user_id))
        await self._repo.store_zk_keys(user_id, material)

    async def rewrap_zk_key(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        *,
        wrapped_private_key: str,
        wrap_salt: str,
    ) -> None:
        await self._repo.rewrap_zk_key(
            user_id, org_id, wrapped_private_key=wrapped_private_key, wrap_salt=wrap_salt
        )

    async def _send_verification(self, user_id: uuid.UUID, email: str) -> None:
        plain = secrets.token_urlsafe(32)
        expires_at = self._clock.now() + self._config.email_verification_ttl
        await self._repo.add_email_verification(user_id, _hash_token(plain), expires_at)
        link = f"{self._config.frontend_base_url}/verify-email?token={plain}"
        await self._mailer.send(
            to=email,
            subject="Verify your GhostCal email",
            html=(
                f"<p>Welcome to GhostCal. Confirm your email to activate your account:</p>"
                f'<p><a href="{link}">Verify my email</a></p>'
            ),
        )

    async def verify_email(self, *, token: str) -> None:
        now = self._clock.now()
        user_id = await self._repo.consume_email_verification(_hash_token(token), now)
        if user_id is None:
            raise InvalidToken("invalid or expired verification token")
        await self._repo.mark_email_verified(user_id, now)

    async def login(self, *, email: str, password: str) -> TokenPair:
        user = await self._repo.get_by_email(email.strip().lower())
        if user is None or user.password_hash is None:
            # Spend the same Argon2 time as a real verify so a missing account isn't detectable by
            # timing (user enumeration).
            self._hasher.verify(_dummy_hash(self._hasher), password)
            raise InvalidCredentials("invalid email or password")
        if not self._hasher.verify(user.password_hash, password):
            raise InvalidCredentials("invalid email or password")
        if not user.email_verified:
            raise EmailNotVerified("email not verified")
        return await self._issue_pair(user.id)

    async def authenticate_oidc(
        self, *, provider: str, issuer: str, subject: str, email: str, name: str
    ) -> TokenPair:
        """Log a user in from a validated OIDC identity, provisioning on first login. No password
        is involved; the zero-knowledge content is unlocked later by the encryption passphrase."""
        email = email.strip().lower()
        user_id = await self._repo.upsert_oidc_identity(
            provider=provider,
            issuer=issuer,
            subject=subject,
            email=email,
            name=name or email,
            org_name=name or email,
            org_slug=_org_slug(email),
        )
        return await self._issue_pair(user_id)

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        now = self._clock.now()
        user_id = await self._repo.rotate_refresh_token(_hash_token(refresh_token), now)
        if user_id is None:
            raise InvalidToken("invalid or expired refresh token")
        return await self._issue_pair(user_id)

    async def logout(self, *, refresh_token: str) -> None:
        await self._repo.revoke_refresh_token(_hash_token(refresh_token), self._clock.now())

    async def current_user(self, *, access_token: str) -> AuthenticatedUser:
        try:
            user_id = self._codec.decode(access_token)
        except ValueError as exc:
            raise InvalidToken("invalid access token") from exc
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise InvalidToken("unknown user")
        return AuthenticatedUser(
            id=user.id, email=user.email, name=user.name, email_verified=user.email_verified
        )

    async def _issue_pair(self, user_id: uuid.UUID) -> TokenPair:
        access = self._codec.encode(user_id)
        refresh_plain = secrets.token_urlsafe(32)
        expires_at = self._clock.now() + self._config.refresh_ttl
        await self._repo.add_refresh_token(user_id, _hash_token(refresh_plain), expires_at)
        return TokenPair(
            access_token=access,
            refresh_token=refresh_plain,
            expires_in=int(self._config.access_ttl.total_seconds()),
        )
