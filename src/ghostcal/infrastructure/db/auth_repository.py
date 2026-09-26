"""SQL implementation of the auth repository port.

Operates on global (non-RLS) identity tables via a plain ``db_session``. Account provisioning goes
through a SECURITY DEFINER function so the org/membership inserts happen in a controlled way.

**SECURITY DEFINER does not, on its own, get past RLS here.** ``organizations`` and ``memberships``
carry FORCE ROW LEVEL SECURITY, which subjects even the table owner to the policy — that is what
FORCE is for. The provisioning function therefore sets ``app.current_org_id`` to the id it is about
to insert, and restores it afterwards. This docstring claimed the opposite until 2026-08-13, when
first-time SSO provisioning turned out never to have been able to work.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.auth import (
    AuthRepository,
    AuthUserRecord,
    EmailAlreadyRegistered,
    OidcIdentityRefused,
    ZkKeyBundle,
    ZkKeyMaterial,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_login_email, bind_org, bind_user

# The exact texts the provisioning function RAISEs when it decides not to link an identity.
# Anything else carrying 42501 is the database refusing *us*, not the function refusing a caller.
_REFUSAL_REASONS = (
    "oidc email not verified by the provider",
    "an unverified local account already holds this email",
)


class SqlAuthRepository(AuthRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def provision_account(
        self, *, email: str, name: str, password_hash: str, org_name: str, org_slug: str
    ) -> uuid.UUID:
        try:
            row = (
                await self._session.execute(
                    text(
                        "SELECT user_id FROM "
                        "provision_account(:email, :name, :pw, :org_name, :org_slug)"
                    ),
                    {
                        "email": email,
                        "name": name,
                        "pw": password_hash,
                        "org_name": org_name,
                        "org_slug": org_slug,
                    },
                )
            ).one()
        except IntegrityError as exc:
            raise EmailAlreadyRegistered(email) from exc
        return row.user_id  # type: ignore[no-any-return]

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
        # The function raises `insufficient_privilege` when it refuses to link. Translated here so
        # the application layer sees a domain error rather than a driver exception — and so a
        # refusal cannot surface as a 500.
        #
        # Matched on the MESSAGE, not on the SQLSTATE alone. 42501 is also what PostgreSQL raises
        # for a row-level-security violation, and on 2026-08-13 that cost a long diagnosis:
        # creating the first organization was structurally impossible under FORCE ROW LEVEL
        # SECURITY, and it surfaced as "identity refused" — a policy decision the operator was
        # invited to believe. An infrastructure failure must not get to wear the costume of a rule.
        try:
            row = (
                await self._session.execute(
                    text(
                        "SELECT upsert_oidc_identity("
                        ":provider, :issuer, :subject, :email, :name, :org_name, :org_slug, "
                        ":email_verified) AS user_id"
                    ),
                    {
                        "provider": provider,
                        "issuer": issuer,
                        "subject": subject,
                        "email": email,
                        "name": name,
                        "org_name": org_name,
                        "org_slug": org_slug,
                        "email_verified": email_verified,
                    },
                )
            ).one()
        except DBAPIError as exc:
            orig = getattr(exc, "orig", None)
            if getattr(orig, "sqlstate", None) == "42501" and any(
                reason in str(orig) for reason in _REFUSAL_REASONS
            ):
                raise OidcIdentityRefused(str(orig)) from exc
            raise
        return row.user_id  # type: ignore[no-any-return]

    async def _bind_user_and_org(self, user_id: uuid.UUID) -> None:
        """Declare the acting user, then bind their primary organization.

        The zk functions resolve the caller's organization from `memberships` and then write to
        `organizations` / `org_member_keys`. Under FORCE ROW LEVEL SECURITY the definer functions
        inherit no sight of their own, so both contexts must be declared by the caller: the user
        GUC opens the self-read policies for the resolution, the org GUC opens `tenant_isolation`
        for the writes — row by row, no bypass anywhere.
        """
        await bind_user(self._session, user_id)
        org_id = (
            await self._session.execute(
                text("SELECT user_primary_organization(:uid) AS org"), {"uid": str(user_id)}
            )
        ).scalar_one()
        if org_id is not None:
            await bind_org(self._session, org_id)

    async def store_zk_keys(self, user_id: uuid.UUID, material: ZkKeyMaterial) -> None:
        await self._bind_user_and_org(user_id)
        await self._session.execute(
            text("SELECT store_zk_keys(:uid, :pub, :wsk, :wsalt, :rsk, :rsalt)"),
            {
                "uid": user_id,
                "pub": material.public_key,
                "wsk": material.wrapped_private_key,
                "wsalt": material.wrap_salt,
                "rsk": material.recovery_wrapped_private_key,
                "rsalt": material.recovery_salt,
            },
        )

    async def get_zk_keys(self, user_id: uuid.UUID) -> list[ZkKeyBundle]:
        await self._bind_user_and_org(user_id)
        rows = (
            await self._session.execute(
                text(
                    "SELECT organization_id, public_key, wrapped_private_key, wrap_salt, "
                    "recovery_wrapped_private_key, recovery_salt, generation, sealed_org_key "
                    "FROM get_zk_keys(:uid)"
                ),
                {"uid": user_id},
            )
        ).all()
        return [
            ZkKeyBundle(
                organization_id=row.organization_id,
                public_key=row.public_key,
                generation=row.generation,
                sealed_org_key=row.sealed_org_key,
                wrapped_private_key=row.wrapped_private_key,
                wrap_salt=row.wrap_salt,
                recovery_wrapped_private_key=row.recovery_wrapped_private_key,
                recovery_salt=row.recovery_salt,
            )
            for row in rows
            if row.public_key is not None
        ]

    async def rewrap_zk_key(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        *,
        wrapped_private_key: str,
        wrap_salt: str,
    ) -> None:
        # The org is already known here — bind both contexts directly.
        await bind_user(self._session, user_id)
        await bind_org(self._session, org_id)
        await self._session.execute(
            text("SELECT rewrap_zk_key(:uid, :oid, :wsk, :wsalt)"),
            {"uid": user_id, "oid": org_id, "wsk": wrapped_private_key, "wsalt": wrap_salt},
        )

    async def get_by_email(self, email: str) -> AuthUserRecord | None:
        # Le seul chemin qui lit `users` sans tenir d'identifiant : il n'a qu'une adresse tapée
        # dans un formulaire. `users_email_lookup` ouvre la ligne qui porte l'adresse déclarée,
        # et rien d'autre — voir `bind_login_email`, qui dit ce que cela coûte et ce que cela ne
        # rouvre pas.
        await bind_login_email(self._session, email)
        stmt = (
            select(
                models.User.id,
                models.User.email,
                models.User.name,
                models.User.timezone,
                models.User.avatar_url,
                models.User.avatar_updated_at,
                models.User.email_verified_at,
                models.UserCredential.password_hash,
            )
            .outerjoin(models.UserCredential, models.UserCredential.user_id == models.User.id)
            .where(func.lower(models.User.email) == email)
        )
        row = (await self._session.execute(stmt)).first()
        return _to_record(row)

    async def get_by_id(self, user_id: uuid.UUID) -> AuthUserRecord | None:
        # `users_select` demande qu'on dise pour qui on agit. L'appelant le sait déjà — c'est le
        # porteur du jeton, ou l'identifiant qu'un jeton à usage unique vient de rendre. Déclarer
        # n'accorde rien de plus : la politique n'ouvre que cette ligne-là.
        await bind_user(self._session, user_id)
        stmt = (
            select(
                models.User.id,
                models.User.email,
                models.User.name,
                models.User.timezone,
                models.User.avatar_url,
                models.User.avatar_updated_at,
                models.User.email_verified_at,
                models.UserCredential.password_hash,
            )
            .outerjoin(models.UserCredential, models.UserCredential.user_id == models.User.id)
            .where(models.User.id == user_id)
        )
        row = (await self._session.execute(stmt)).first()
        return _to_record(row)

    async def add_email_verification(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        await self._session.execute(
            insert(models.EmailVerificationToken).values(
                user_id=user_id, token_hash=token_hash, expires_at=expires_at
            )
        )

    async def consume_email_verification(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        stmt = (
            update(models.EmailVerificationToken)
            .where(
                models.EmailVerificationToken.token_hash == token_hash,
                models.EmailVerificationToken.used_at.is_(None),
                models.EmailVerificationToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(models.EmailVerificationToken.user_id)
        )
        row = (await self._session.execute(stmt)).first()
        return row.user_id if row else None

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None:
        # ─── L'écriture qui ne levait rien ───
        #
        # Sans cette déclaration, `users_update` ne désigne aucune ligne et l'`UPDATE` touche
        # zéro ligne. Ce n'est pas une erreur pour PostgreSQL, et rien ici ne lit `rowcount` :
        # la vérification d'adresse réussissait en apparence et ne faisait rien.
        #
        # Le symptôme sortait trois appels plus loin — connexion refusée pour « adresse non
        # vérifiée », invitation refusée pour la même raison, sur un compte qui venait de
        # cliquer le lien. Mesuré le 2026-09-26 : `rowcount = 0` sans GUC, `1` avec.
        await bind_user(self._session, user_id)
        await self._session.execute(
            update(models.User).where(models.User.id == user_id).values(email_verified_at=now)
        )

    async def add_password_reset(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        await self._session.execute(
            insert(models.PasswordResetToken).values(
                user_id=user_id, token_hash=token_hash, expires_at=expires_at
            )
        )

    async def peek_password_reset(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        # A read, not an UPDATE: the reset page fetches the key envelopes before the user has
        # typed their recovery phrase, and a wrong phrase must not burn the link.
        row = (
            await self._session.execute(
                select(models.PasswordResetToken.user_id).where(
                    models.PasswordResetToken.token_hash == token_hash,
                    models.PasswordResetToken.used_at.is_(None),
                    models.PasswordResetToken.expires_at > now,
                )
            )
        ).first()
        return row.user_id if row else None

    async def consume_password_reset(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        # Single use enforced inside the UPDATE, like the verification token above: a check
        # followed by a write is two statements a second request can slip between.
        row = (
            await self._session.execute(
                update(models.PasswordResetToken)
                .where(
                    models.PasswordResetToken.token_hash == token_hash,
                    models.PasswordResetToken.used_at.is_(None),
                    models.PasswordResetToken.expires_at > now,
                )
                .values(used_at=now)
                .returning(models.PasswordResetToken.user_id)
            )
        ).first()
        return row.user_id if row else None

    async def add_refresh_token(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        await self._session.execute(
            insert(models.RefreshToken).values(
                user_id=user_id, token_hash=token_hash, expires_at=expires_at
            )
        )

    async def rotate_refresh_token(self, token_hash: str, now: datetime) -> uuid.UUID | None:
        stmt = (
            update(models.RefreshToken)
            .where(
                models.RefreshToken.token_hash == token_hash,
                models.RefreshToken.revoked_at.is_(None),
                models.RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(models.RefreshToken.user_id)
        )
        row = (await self._session.execute(stmt)).first()
        return row.user_id if row else None

    async def revoke_refresh_token(self, token_hash: str, now: datetime) -> None:
        await self._session.execute(
            update(models.RefreshToken)
            .where(
                models.RefreshToken.token_hash == token_hash,
                models.RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def revoke_all_refresh_tokens(self, user_id: uuid.UUID, now: datetime) -> int:
        # RETURNING rather than rowcount: it is what the rest of this repository uses, and
        # `Result.rowcount` is not part of the typed surface.
        stmt = (
            update(models.RefreshToken)
            .where(
                models.RefreshToken.user_id == user_id,
                models.RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(models.RefreshToken.id)
        )
        return len((await self._session.execute(stmt)).scalars().all())

    async def update_profile(
        self, user_id: uuid.UUID, *, name: str, timezone: str, avatar_url: str | None
    ) -> None:
        # Même silence que `mark_email_verified` sans cette ligne : le profil se disait
        # enregistré et ne l'était pas.
        await bind_user(self._session, user_id)
        await self._session.execute(
            update(models.User)
            .where(models.User.id == user_id)
            .values(name=name, timezone=timezone, avatar_url=avatar_url)
        )

    async def set_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        await self._session.execute(
            update(models.UserCredential)
            .where(models.UserCredential.user_id == user_id)
            .values(password_hash=password_hash)
        )


def _to_record(row: object) -> AuthUserRecord | None:
    if row is None:
        return None
    return AuthUserRecord(
        id=row.id,  # type: ignore[attr-defined]
        email=row.email,  # type: ignore[attr-defined]
        name=row.name,  # type: ignore[attr-defined]
        timezone=row.timezone,  # type: ignore[attr-defined]
        email_verified=row.email_verified_at is not None,  # type: ignore[attr-defined]
        password_hash=row.password_hash,  # type: ignore[attr-defined]
        avatar_url=row.avatar_url,  # type: ignore[attr-defined]
        avatar_updated_at=row.avatar_updated_at,  # type: ignore[attr-defined]
    )


class SqlAvatarRepository:
    """Lit et écrit l'avatar, et **filtre lui-même** l'organisation.

    Le filtre est dans la requête, pas dans la seule sécurité au niveau ligne. Trois
    requêtes de ce dépôt s'en étaient remises à elle et fuyaient entre organisations —
    corrigées le 2026-09-25. La production tourne en superutilisateur, où la RLS ne
    s'applique pas du tout : une requête ne vaut que par son `WHERE`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enregistrer(
        self, user_id: uuid.UUID, *, octets: bytes, mime: str, quand: datetime
    ) -> None:
        await self._session.execute(
            update(models.User)
            .where(models.User.id == user_id)
            .values(avatar_bytes=octets, avatar_mime=mime, avatar_updated_at=quand)
        )

    async def effacer(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(models.User)
            .where(models.User.id == user_id)
            .values(avatar_bytes=None, avatar_mime=None, avatar_updated_at=None)
        )

    async def lire_dans_l_organisation(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> tuple[bytes, str, datetime] | None:
        """L'avatar d'un membre, vu par un membre de la même organisation.

        La jointure porte son filtre d'organisation — c'est exactement la forme qui
        manquait à `member_public_keys` et `members_without_keypair`, et qui les faisait
        rendre les utilisateurs de tout le serveur.
        """
        row = (
            await self._session.execute(
                select(
                    models.User.avatar_bytes,
                    models.User.avatar_mime,
                    models.User.avatar_updated_at,
                )
                .join(models.Membership, models.Membership.user_id == models.User.id)
                .where(
                    models.User.id == user_id,
                    models.Membership.organization_id == organization_id,
                )
            )
        ).one_or_none()
        if row is None or row.avatar_bytes is None:
            return None
        return row.avatar_bytes, row.avatar_mime, row.avatar_updated_at
