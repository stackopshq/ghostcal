"""SQL implementation of the organization repository (the caller's own org, RLS-scoped)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.organization import (
    HandleTaken,
    OrganizationData,
    OrganizationRepository,
)
from ghostcal.infrastructure.db import models


class SqlOrganizationRepository(OrganizationRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def get(self) -> OrganizationData | None:
        row = (
            await self._session.execute(
                select(models.Organization).where(models.Organization.id == self._org_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return OrganizationData(id=row.id, name=row.name, slug=row.slug)

    async def update(self, *, name: str, slug: str) -> None:
        try:
            await self._session.execute(
                update(models.Organization)
                .where(models.Organization.id == self._org_id)
                .values(name=name, slug=slug)
            )
            await self._session.flush()
        except IntegrityError as exc:
            raise HandleTaken(slug) from exc
