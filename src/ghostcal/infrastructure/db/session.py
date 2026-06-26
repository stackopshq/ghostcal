"""Async session layer with per-transaction tenant binding.

Every unit of work runs inside a transaction that first sets the ``app.current_org_id`` GUC.
Row-Level Security policies read that GUC, so a query can only ever see (or write) rows of the
current organization — even if the application code forgets a ``WHERE organization_id = ...``.

``set_config(..., is_local => true)`` scopes the setting to the surrounding transaction, so it
is automatically cleared on commit/rollback and never leaks to the next checkout of a pooled
connection.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ghostcal.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        # Tenant isolation must not depend on statement caching quirks; keep it predictable.
        echo=False,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def org_session(organization_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Open a transactional session bound to ``organization_id``.

    Commits on clean exit, rolls back on exception. All statements run under RLS scoped to the
    given organization.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session, session.begin():
        await _bind_org(session, organization_id)
        yield session


async def _bind_org(session: AsyncSession, organization_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_org_id', :oid, true)"),
        {"oid": str(organization_id)},
    )
