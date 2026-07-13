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


async def primary_membership(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[uuid.UUID, str] | None:
    """(organization_id, role) of the user's primary membership, or None."""
    row = (
        await session.execute(
            text("SELECT organization_id, role FROM user_primary_membership(:uid)"),
            {"uid": str(user_id)},
        )
    ).first()
    if row is None:
        return None
    return (row.organization_id, row.role)


async def user_organizations(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[uuid.UUID, str, str, str]]:
    """All orgs the user belongs to as (id, name, slug, role), oldest membership first."""
    rows = (
        await session.execute(
            text("SELECT organization_id, name, slug, role FROM user_organizations(:uid)"),
            {"uid": str(user_id)},
        )
    ).all()
    return [(r.organization_id, r.name, r.slug, r.role) for r in rows]


async def role_in_org(
    session: AsyncSession, user_id: uuid.UUID, organization_id: uuid.UUID
) -> str | None:
    """The user's role in a specific org, or None if not a member."""
    return (  # type: ignore[no-any-return]
        await session.execute(
            text("SELECT user_role_in_org(:uid, :oid) AS role"),
            {"uid": str(user_id), "oid": str(organization_id)},
        )
    ).scalar_one()


async def organization_id_by_slug(session: AsyncSession, slug: str) -> uuid.UUID | None:
    result = await session.execute(
        text("SELECT organization_id_by_slug(:slug) AS org"), {"slug": slug}
    )
    return result.scalar_one()  # type: ignore[no-any-return]


async def poll_organization_by_slug(session: AsyncSession, slug: str) -> uuid.UUID | None:
    result = await session.execute(
        text("SELECT poll_organization_by_slug(:slug) AS org"), {"slug": slug}
    )
    return result.scalar_one()  # type: ignore[no-any-return]


async def active_caldav_connections(
    session: AsyncSession,
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """All active connections as (organization_id, user_id, connection_id), across tenants.

    Per *connection*, not per user: a member may have several calendars, and one of them failing to
    sync must not stop the others.
    """
    result = await session.execute(
        text("SELECT id, organization_id, user_id FROM caldav_active_connections()")
    )
    return [(row.organization_id, row.user_id, row.id) for row in result.all()]


async def active_subscriptions(
    session: AsyncSession,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """All active ICS subscriptions as (organization_id, subscription_id) across tenants."""
    result = await session.execute(
        text("SELECT organization_id, subscription_id FROM active_subscriptions()")
    )
    return [(row.organization_id, row.subscription_id) for row in result.all()]
