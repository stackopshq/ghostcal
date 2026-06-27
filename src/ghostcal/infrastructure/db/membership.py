"""Resolve a user's organization without an org context (via the SECURITY DEFINER function)."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def primary_organization(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    result = await session.execute(
        text("SELECT user_primary_organization(:uid) AS org"), {"uid": str(user_id)}
    )
    return result.scalar_one()  # type: ignore[no-any-return]


async def organization_id_by_slug(session: AsyncSession, slug: str) -> uuid.UUID | None:
    result = await session.execute(
        text("SELECT organization_id_by_slug(:slug) AS org"), {"slug": slug}
    )
    return result.scalar_one()  # type: ignore[no-any-return]


async def active_caldav_connections(
    session: AsyncSession,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """All active connections as (organization_id, user_id) across tenants (for the worker)."""
    result = await session.execute(
        text("SELECT organization_id, user_id FROM caldav_active_connections()")
    )
    return [(row.organization_id, row.user_id) for row in result.all()]
