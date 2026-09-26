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

from ghostcal.application.passwords import NoBreachCheck, enforce_password_policy
from ghostcal.application.ports.clock import Clock
from ghostcal.application.ports.email import EmailSender
from ghostcal.application.ports.security import (
    AccessTokenCodec,
    BreachedPasswordChecker,
    PasswordHasher,
)
from ghostcal.application.two_factor import TwoFactorService


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


class OidcIdentityRefused(AuthError):
    """The OIDC login may not be bound to a local account.

    Either the provider did not vouch for the email, or an unverified local account already holds
    it. Deliberately one error for both: telling them apart at the edge would reveal whether an
    account exists on an address the caller has not proved they own.
    """


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
    # Quand l'avatar téléversé a changé. `None` veut dire « il n'y en a pas ».
    #
    # Le champ existait déjà en base pour l'`ETag` ; l'exposer coûte donc une colonne
    # déjà lue, et il sert deux fois côté client : savoir qu'un avatar existe, et casser
    # le cache de l'image après un envoi. Sans lui, le navigateur continuerait d'afficher
    # l'ancienne — un téléversement qui semble n'avoir rien fait.
    avatar_updated_at: datetime | None = None


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
    password_reset_ttl: timedelta = timedelta(hours=1)


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
        email_verified: bool,
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

    async def add_password_reset(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        raise NotImplementedError

    async def peek_password_reset(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        """The user a live token belongs to, WITHOUT spending it, else None.

        The reset page needs the key envelopes before it can offer to reset anything, and it must
        be able to fail on a wrong recovery phrase without burning the link.
        """
        raise NotImplementedError

    async def consume_password_reset(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        """Mark an unused, unexpired token used and return its user id, else None."""
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

    async def revoke_all_refresh_tokens(self, user_id: uuid.UUID, now: datetime) -> int:
        """Revoke every live session for a user. Returns how many were revoked."""
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


@dataclass(frozen=True)
class ZkRewrap:
    """One organization's key, re-wrapped under the new password by the browser."""

    organization_id: uuid.UUID
    wrapped_private_key: str
    wrap_salt: str


class AuthService:
    def __init__(
        self,
        repo: AuthRepository,
        hasher: PasswordHasher,
        codec: AccessTokenCodec,
        mailer: EmailSender,
        clock: Clock,
        config: AuthConfig,
        two_factor: TwoFactorService,
        breach_checker: BreachedPasswordChecker | None = None,
    ) -> None:
        self._repo = repo
        self._hasher = hasher
        self._codec = codec
        self._mailer = mailer
        self._clock = clock
        self._config = config
        # Exigé, et non optionnel avec un défaut : un `AuthService` construit
        # sans lui se connecterait sans second facteur, en silence et sans que
        # rien ne l'indique. Un oubli doit faire une TypeError bruyante au
        # montage, pas une porte ouverte en production.
        self._two_factor = two_factor
        self._breach_checker = breach_checker or NoBreachCheck()

    async def register(
        self, *, email: str, name: str, password: str, zk_keys: ZkKeyMaterial
    ) -> uuid.UUID:
        email = email.strip().lower()
        await enforce_password_policy(password, self._breach_checker)
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
        """Record the verification token and ask for the email that carries it.

        The two lines do different kinds of work and only one of them belongs to the caller's
        transaction. The insert does: a token nobody can present is worse than no token. The send
        does not, and must not be able to undo the insert -- that is the port's business, and the
        adapter the routes pass in buffers the message until the transaction has committed. Do not
        "simplify" this by making the sender reach the network from here: that is precisely what
        turned a Brevo 401 into a rolled-back sign-up on 2026-09-25.
        """
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

    async def request_password_reset(self, *, email: str) -> None:
        """Start a reset. Says nothing about whether the address is known.

        Always returns as if it worked: a route that answers differently for a known and an unknown
        address is an account-enumeration oracle, and the caller here is unauthenticated.

        Nothing is sent to an address that was never verified either. The link is proof of mailbox
        control, and an unverified address has never been shown to belong to the account holder.
        """
        user = await self._repo.get_by_email(email.strip().lower())
        if user is None or not user.email_verified:
            return
        plain = secrets.token_urlsafe(32)
        expires_at = self._clock.now() + self._config.password_reset_ttl
        await self._repo.add_password_reset(user.id, _hash_token(plain), expires_at)
        link = f"{self._config.frontend_base_url}/reset-password?token={plain}"
        await self._mailer.send(
            to=email,
            subject="Reset your GhostCal password",
            html=(
                "<p>Someone asked to reset the password on this GhostCal account. If that was not "
                "you, ignore this message and nothing changes.</p>"
                f'<p><a href="{link}">Reset my password</a></p>'
                "<p>You will need the recovery phrase shown when the account was created. Without "
                "it this link cannot open your calendar — we do not hold a copy.</p>"
            ),
        )

    async def zk_keys_for_reset(self, *, token: str) -> list[ZkKeyBundle]:
        """The key envelopes a reset needs, for the holder of a live token.

        Handing these to whoever has the emailed link is deliberate and safe: every one of them is
        sealed under the recovery phrase, 24 random bytes — 192 bits — behind Argon2id. Mailbox
        access alone yields ciphertext and nothing else.
        """
        user_id = await self._repo.peek_password_reset(_hash_token(token), self._clock.now())
        if user_id is None:
            raise InvalidToken("invalid or expired reset token")
        return await self._repo.get_zk_keys(user_id)

    async def reset_password(
        self, *, token: str, new_password: str, envelopes: list[ZkRewrap]
    ) -> None:
        """Set a new password from a reset link, together with the re-wrapped key envelopes.

        The envelopes are not optional and not a second step. The server cannot produce them — it
        never sees a private key — so if the browser does not send them here, the account ends up
        with a working password and a calendar nothing can open. That is the failure this whole
        feature exists to undo; doing it in two requests would reintroduce it in the gap.

        Every session is revoked, for the same reason a deliberate password change revokes them.
        """
        await enforce_password_policy(new_password, self._breach_checker)
        now = self._clock.now()
        user_id = await self._repo.consume_password_reset(_hash_token(token), now)
        if user_id is None:
            raise InvalidToken("invalid or expired reset token")
        await self._repo.set_password_hash(user_id, self._hasher.hash(new_password))
        for envelope in envelopes:
            await self._repo.rewrap_zk_key(
                user_id,
                envelope.organization_id,
                wrapped_private_key=envelope.wrapped_private_key,
                wrap_salt=envelope.wrap_salt,
            )
        await self._repo.revoke_all_refresh_tokens(user_id, now)

    async def verify_email(self, *, token: str) -> None:
        now = self._clock.now()
        user_id = await self._repo.consume_email_verification(_hash_token(token), now)
        if user_id is None:
            raise InvalidToken("invalid or expired verification token")
        await self._repo.mark_email_verified(user_id, now)

    async def login(self, *, email: str, password: str, totp_code: str | None = None) -> TokenPair:
        """Connexion par mot de passe, second facteur compris.

        L'ordre des contrôles n'est pas indifférent. Le second facteur se teste
        **après** le mot de passe : le demander plus tôt dirait à un inconnu
        quels comptes existent et lesquels sont protégés, ce qui est précisément
        ce que la vérification à temps constant au-dessus cherche à taire.

        Il ne se teste pas non plus sur `refresh` : le jeton de rafraîchissement
        n'a été émis qu'après un passage réussi ici. Et la réinitialisation de
        mot de passe ne le contourne pas — reprendre la main sur la boîte aux
        lettres ne doit pas suffire à franchir le facteur qui existe justement
        pour survivre à un mot de passe compromis.
        """
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
        await self._two_factor.enforce_at_login(user.id, code=totp_code)
        return await self._issue_pair(user.id)

    async def verify_password(self, user_id: uuid.UUID, password: str) -> bool:
        """Le mot de passe courant est-il celui-là ?

        Sert aux opérations sensibles qu'une session déjà ouverte ne doit pas
        suffire à faire — retirer le second facteur, par exemple. Rend False
        pour un compte sans mot de passe (SSO) plutôt que de lever : l'appelant
        traduit ça en refus, et un compte SSO n'a rien à revérifier ici.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None or user.password_hash is None:
            return False
        return self._hasher.verify(user.password_hash, password)

    async def authenticate_oidc(
        self,
        *,
        provider: str,
        issuer: str,
        subject: str,
        email: str,
        name: str,
        email_verified: bool,
    ) -> TokenPair:
        """Log a user in from a validated OIDC identity, provisioning on first login. No password
        is involved; the zero-knowledge content is unlocked later by the encryption passphrase.

        Volontairement **sans** second facteur maison. Sur ce chemin c'est le
        fournisseur d'identité qui authentifie, et c'est lui qui porte le second
        facteur s'il y en a un. En redemander un ici n'ajouterait rien à la
        sécurité — le mot de passe qu'il protégerait n'existe pas de ce
        côté-ci — et donnerait une seconde façon de se retrouver enfermé dehors.
        """
        email = email.strip().lower()
        user_id = await self._repo.upsert_oidc_identity(
            provider=provider,
            issuer=issuer,
            subject=subject,
            email=email,
            name=name or email,
            org_name=name or email,
            org_slug=_org_slug(email),
            email_verified=email_verified,
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
