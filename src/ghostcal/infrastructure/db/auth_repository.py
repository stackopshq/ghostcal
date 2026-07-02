"""SQL implementation of the auth repository port.

Operates on global (non-RLS) identity tables via a plain ``db_session``. Account provisioning
goes through the ``provision_account`` SECURITY DEFINER function so the org/membership inserts
bypass RLS in a controlled way.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.auth import (
    AuthRepository,
    AuthUserRecord,
    EmailAlreadyRegistered,
    ZkKeyBundle,
    ZkKeyMaterial,
)
from ghostcal.infrastructure.db import models


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
    ) -> uuid.UUID:
        row = (
            await self._session.execute(
                text(
                    "SELECT upsert_oidc_identity("
                    ":provider, :issuer, :subject, :email, :name, :org_name, :org_slug) AS user_id"
                ),
                {
                    "provider": provider,
                    "issuer": issuer,
                    "subject": subject,
                    "email": email,
                    "name": name,
                    "org_name": org_name,
                    "org_slug": org_slug,
                },
            )
        ).one()
        return row.user_id  # type: ignore[no-any-return]

    async def store_zk_keys(self, user_id: uuid.UUID, material: ZkKeyMaterial) -> None:
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
        rows = (
            await self._session.execute(
                text(
                    "SELECT organization_id, public_key, wrapped_private_key, wrap_salt, "
                    "recovery_wrapped_private_key, recovery_salt FROM get_zk_keys(:uid)"
                ),
                {"uid": user_id},
            )
        ).all()
        return [
            ZkKeyBundle(
                organization_id=row.organization_id,
                public_key=row.public_key,
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
        await self._session.execute(
            text("SELECT rewrap_zk_key(:uid, :oid, :wsk, :wsalt)"),
            {"uid": user_id, "oid": org_id, "wsk": wrapped_private_key, "wsalt": wrap_salt},
        )

    async def get_by_email(self, email: str) -> AuthUserRecord | None:
        stmt = (
            select(
                models.User.id,
                models.User.email,
                models.User.name,
                models.User.timezone,
                models.User.avatar_url,
                models.User.email_verified_at,
                models.UserCredential.password_hash,
            )
            .outerjoin(models.UserCredential, models.UserCredential.user_id == models.User.id)
            .where(func.lower(models.User.email) == email)
        )
        row = (await self._session.execute(stmt)).first()
        return _to_record(row)

    async def get_by_id(self, user_id: uuid.UUID) -> AuthUserRecord | None:
        stmt = (
            select(
                models.User.id,
                models.User.email,
                models.User.name,
                models.User.timezone,
                models.User.avatar_url,
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
        await self._session.execute(
            update(models.User).where(models.User.id == user_id).values(email_verified_at=now)
        )

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

    async def update_profile(
        self, user_id: uuid.UUID, *, name: str, timezone: str, avatar_url: str | None
    ) -> None:
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
    )
