"""SQL implementation of the per-user keypair repository port (ADR-0007).

``users`` is a global (non-RLS) table, so this runs on a plain ``db_session``. Listing an
organization's member public keys crosses from that global table into the tenant-scoped
``memberships``, so it runs under the org's GUC and RLS scopes the join for us: a caller can only
ever see the public keys of people they share an organization with.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.keypairs import (
    KeypairRepository,
    MemberPublicKey,
    UserKeypair,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_org


class SqlKeypairRepository(KeypairRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> UserKeypair | None:
        row = (
            await self._session.execute(
                select(
                    models.User.zk_public_key,
                    models.User.zk_wrapped_private_key,
                    models.User.zk_wrap_salt,
                ).where(models.User.id == user_id)
            )
        ).first()
        if row is None or row.zk_public_key is None:
            return None
        return UserKeypair(
            public_key=row.zk_public_key,
            wrapped_private_key=row.zk_wrapped_private_key,
            wrap_salt=row.zk_wrap_salt,
        )

    async def set(self, user_id: uuid.UUID, keypair: UserKeypair) -> bool:
        # Write-once, enforced in the WHERE clause rather than by a read-then-write: two logins
        # racing each other must not end with one user's keypair overwriting the other's, stranding
        # whatever was already sealed to the loser.
        result = await self._session.execute(
            update(models.User)
            .where(models.User.id == user_id, models.User.zk_public_key.is_(None))
            .values(
                zk_public_key=keypair.public_key,
                zk_wrapped_private_key=keypair.wrapped_private_key,
                zk_wrap_salt=keypair.wrap_salt,
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def member_public_keys(self, organization_id: uuid.UUID) -> list[MemberPublicKey]:
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                select(
                    models.User.id,
                    models.User.name,
                    models.User.email,
                    models.User.zk_public_key,
                )
                .join(models.Membership, models.Membership.user_id == models.User.id)
                .order_by(models.User.name)
            )
        ).all()
        return [
            MemberPublicKey(user_id=r.id, name=r.name, email=r.email, public_key=r.zk_public_key)
            for r in rows
        ]
