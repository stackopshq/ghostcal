"""SQL implementation of the retention repository port. See ADR-0006.

Reading and writing an organization's own window runs under RLS (an ``org_session``).

The purge is two steps rather than one, and the split is the point. Enumerating the organizations
that have a window needs no tenant — nothing is bound yet — so it goes through the
``organizations_with_retention`` SECURITY DEFINER function, whose return type is the whole of what
it may hand over: an id and a number of days. The deletion itself is an ordinary DELETE under an
``org_session``, subject to the same policy as everything else.

It used to be one cross-tenant DELETE joined to ``organizations``. On a schema owned by a plain
role, with no tenant bound, that join saw nothing and the purge silently deleted nothing — for as
long as CI owned its schema with a superuser, which made it work there and only there.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.retention import RetentionRepository, RetentionWindow
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_retention_scan


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

    async def retention_windows(self) -> list[RetentionWindow]:
        # Declare the scan first: without it `organizations_retention_scan` matches nothing and this
        # returns an empty list — silently, which is exactly how the previous purge deleted nothing
        # for months. The witness covers both directions.
        await bind_retention_scan(self._session)
        rows = (
            await self._session.execute(
                text("SELECT organization_id, retention_days FROM organizations_with_retention()")
            )
        ).all()
        return [
            RetentionWindow(organization_id=r.organization_id, days=r.retention_days) for r in rows
        ]

    async def purge_organization(self, organization_id: uuid.UUID, days: int) -> int:
        # No join to `organizations`, and no filter on organization_id either: the tenant is
        # already bound, so the policy scopes this to exactly one organization. Adding the filter
        # would suggest the policy might not — and a guard that duplicates a guarantee is how the
        # guarantee stops being read.
        result = await self._session.execute(
            text(
                "DELETE FROM bookings "
                "WHERE end_at < now() - make_interval(days => :days) "
                "RETURNING id"
            ),
            {"days": days},
        )
        return len(result.all())
