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
