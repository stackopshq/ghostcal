"""SQL implementation of the retention repository port. See ADR-0006.

Reading and writing an organization's own window runs under RLS (an ``org_session``). The purge does
not: it spans tenants and runs from a worker with no org context, so it goes through the
``purge_expired_bookings`` SECURITY DEFINER function — the same shape as the reminder scans.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.retention import PurgeResult, RetentionRepository
from ghostcal.infrastructure.db import models


class SqlRetentionRepository(RetentionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_window(self, organization_id: uuid.UUID) -> int | None:
        return (
            await self._session.execute(
                select(models.Organization.booking_retention_days).where(
                    models.Organization.id == organization_id
                )
            )
        ).scalar_one_or_none()

    async def set_window(self, organization_id: uuid.UUID, days: int | None) -> None:
        await self._session.execute(
            update(models.Organization)
            .where(models.Organization.id == organization_id)
            .values(booking_retention_days=days)
        )

    async def purge_expired(self) -> list[PurgeResult]:
        rows = (await self._session.execute(text("SELECT * FROM purge_expired_bookings()"))).all()
        return [PurgeResult(organization_id=r.organization_id, purged=r.purged) for r in rows]
