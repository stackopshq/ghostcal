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


async def reset_engine() -> None:
    """Dispose the cached engine and clear the caches.

    Each Celery task runs under a fresh ``asyncio.run`` event loop; the cached engine would stay
    bound to the previous (closed) loop. Calling this at the end of a task keeps the next run clean.
    """
    await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    """Open a transactional session WITHOUT tenant binding.

    For operations on global (non-RLS) tables — authentication, account provisioning — that run
    before or outside an organization context. Commits on clean exit, rolls back on exception.

    Tenant tables stay default-deny here (they return nothing), including on a pooled connection
    that has already served an org-scoped transaction — see migration b2d8f30c17ae, which is what
    makes that true.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session, session.begin():
        yield session


@asynccontextmanager
async def org_session(organization_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Open a transactional session bound to ``organization_id``.

    Commits on clean exit, rolls back on exception. All statements run under RLS scoped to the
    given organization.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session, session.begin():
        await bind_org(session, organization_id)
        yield session


async def bind_org(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Bind (or re-bind) the tenant GUC on an open transaction.

    ``org_session`` uses this once at the start. Account deletion re-binds it as it walks the
    user's organizations, so a single transaction can act on several tenants in turn while every
    statement stays under RLS.
    """
    await session.execute(
        text("SELECT set_config('app.current_org_id', :oid, true)"),
        {"oid": str(organization_id)},
    )
