"""Resolve a user's organization without an org context.

Every helper here first declares the user via `bind_user`. The SECURITY DEFINER
functions do NOT see across tenants — FORCE ROW LEVEL SECURITY subjects the owner
to the policies too — so their internal queries pass through the
`memberships_self_read` / `organizations_member_read` policies, which only open
the declared caller's own rows. Without the declaration, every resolver returns
NULL, which is exactly what production did until 2026-08-13.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.infrastructure.db.session import bind_user


async def primary_organization(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    await bind_user(session, user_id)
    result = await session.execute(
        text("SELECT user_primary_organization(:uid) AS org"), {"uid": str(user_id)}
    )
    return result.scalar_one()  # type: ignore[no-any-return]


async def primary_membership(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[uuid.UUID, str] | None:
    """(organization_id, role) of the user's primary membership, or None."""
    await bind_user(session, user_id)
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
    await bind_user(session, user_id)
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
    await bind_user(session, user_id)
    return (  # type: ignore[no-any-return]
        await session.execute(
            text("SELECT user_role_in_org(:uid, :oid) AS role"),
            {"uid": str(user_id), "oid": str(organization_id)},
        )
    ).scalar_one()


async def organization_id_by_slug(session: AsyncSession, slug: str) -> uuid.UUID | None:
    """Anonymous by design: a visitor follows /{org-slug}/... with no account.

    The caller declares the slug it is resolving; the `organizations_slug_lookup`
    policy opens exactly that one row, SELECT-only. Without the declaration the
    definer function is blind under FORCE RLS — measured 2026-08-13, every shared
    booking link 404'd minutes after the first one was sent.
    """
    await session.execute(
        text("SELECT set_config('app.public_lookup_slug', :slug, true)"), {"slug": slug}
    )
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
