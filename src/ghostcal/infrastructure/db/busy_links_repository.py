"""SQL implementation of the free-busy link repository port.

The owner's side runs under RLS in their organization's session, and is scoped to their own links on
top of that: publishing a colleague's availability is not a thing anyone should be able to do.

The visitor has no account and no organization, so no RLS context at all. They get one door —
``busy_link_by_token`` — and it hands back a person, not a calendar and not a time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.busy_links import BusyLinkOwner, BusyLinkRecord, BusyLinkRepository
from ghostcal.infrastructure.db import models


class SqlBusyLinkRepository(BusyLinkRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def create(self, user_id: uuid.UUID, *, token_hash: str, name: str) -> uuid.UUID:
        return (
            await self._session.execute(
                pg_insert(models.BusyLink)
                .values(
                    organization_id=self._org_id,
                    user_id=user_id,
                    token_hash=token_hash,
                    name=name,
                )
                .returning(models.BusyLink.id)
            )
        ).scalar_one()

    async def list_for_user(self, user_id: uuid.UUID) -> list[BusyLinkRecord]:
        rows = (
            await self._session.execute(
                select(models.BusyLink.id, models.BusyLink.name, models.BusyLink.created_at)
                .where(models.BusyLink.user_id == user_id)
                .order_by(models.BusyLink.created_at)
            )
        ).all()
        return [BusyLinkRecord(id=r.id, name=r.name, created_at=r.created_at) for r in rows]

    async def delete(self, user_id: uuid.UUID, link_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.BusyLink)
            .where(models.BusyLink.id == link_id, models.BusyLink.user_id == user_id)
            .returning(models.BusyLink.id)
        )
        return result.scalar_one_or_none() is not None

    async def resolve(self, token_hash: str) -> BusyLinkOwner | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT organization_id, user_id, owner_name, owner_timezone "
                    "FROM busy_link_by_token(:h)"
                ),
                {"h": token_hash},
            )
        ).one_or_none()
        if row is None:
            return None
        return BusyLinkOwner(
            organization_id=row.organization_id,
            user_id=row.user_id,
            owner_name=row.owner_name,
            owner_timezone=row.owner_timezone,
        )
