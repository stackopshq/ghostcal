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
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        # Server-side limits, applied to every connection as it is opened. A statement that runs
        # past the timeout is cancelled and its connection returned, so one pathological query
        # cannot pin a pool slot indefinitely — which is the difference between a slow minute and
        # an outage. asyncpg takes these through `server_settings`, not as SQL on connect.
        connect_args={
            "server_settings": {
                "statement_timeout": str(settings.db_statement_timeout_ms),
                "idle_in_transaction_session_timeout": str(
                    settings.db_idle_in_transaction_timeout_ms
                ),
                "application_name": "ghostcal",
            }
        },
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


async def bind_retention_scan(session: AsyncSession) -> None:
    """Declare that this transaction is the retention scan.

    The `organizations_retention_scan` policy reads this GUC, and it is the only thing that lets a
    background job see which organizations have asked for a window — it declares no tenant and no
    user, because it is about to iterate every tenant in turn.

    The policy is narrow on purpose and this helper is the whole of its trigger: only organizations
    that actually have a window match, only SELECT is permitted, and the enumeration function still
    returns two columns. Set nowhere else: a scan declared outside the purge would widen what the
    policy sees without widening what anyone reviewed.

    Transaction-local, like `bind_org` and `bind_user`, so it cannot outlive the scan on a pooled
    connection.
    """
    await session.execute(text("SELECT set_config('app.retention_scan', 'on', true)"))


async def bind_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Declare which authenticated user this transaction acts for.

    The `memberships_self_read` and `organizations_member_read` policies read this
    GUC: with it bound, a resolver can see the caller's own memberships and the
    organizations they belong to — and nothing else. Same trust model as
    `bind_org`: the application declares, the policies enforce row by row.

    This exists because FORCE ROW LEVEL SECURITY subjects even the table owner to
    the policies, so SECURITY DEFINER functions inherit no sight at all — measured
    on 2026-08-13, `user_primary_organization()` returned NULL for a user whose
    membership sat in the table. Declaring the user is what makes the trusted
    layer work *without* any RLS bypass.
    """
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user_id)},
    )


async def bind_login_email(session: AsyncSession, email: str) -> None:
    """Declare the address a pre-authentication lookup is about to name.

    The connexion path is the one place that must read `users` with no user to declare: it holds
    an address typed into a form and nothing else. `users_select` cannot help it, and neither can
    a SECURITY DEFINER function — under FORCE ROW LEVEL SECURITY a definer function inherits no
    sight of its own, which is the lesson `_bind_user_and_org` and `store_member_key` already
    wrote down.

    So the address itself is declared, and `users_email_lookup` opens exactly the row that carries
    it. The shape is the one `organizations_slug_lookup`, `invitations_token_read` and
    `public_calendar_by_token` already use: name a value, see the row that holds it.

    What this does **not** reopen is the failure this whole chantier exists for. A query that
    forgets its `WHERE` still returns nothing, because nothing was declared — the policy widens on
    an explicit declaration, never by default. The most it ever yields is one row, to a caller who
    already knew the address to ask for. That is the same question the login form answers.

    Transaction-local, like every other binding here, so it cannot outlive the lookup on a pooled
    connection.
    """
    await session.execute(
        text("SELECT set_config('app.login_email', :email, true)"),
        {"email": email.strip().lower()},
    )
