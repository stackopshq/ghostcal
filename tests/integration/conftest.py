"""Shared fixtures for database integration tests.

The admin engine uses the privileged (superuser) connection, which bypasses RLS — used only to
seed data. Code under test uses the application connection via ``org_session``.

When no database is reachable these tests skip, so a contributor without infrastructure still gets
a useful run. That convenience is dangerous anywhere the database is supposed to exist: a skip is
reported as success, and this suite is where RLS, invitations and key rotation are actually
exercised. ``GHOSTCAL_TESTS_REQUIRE_DB=1`` turns the skip into a failure, and CI sets it.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import NoReturn

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ghostcal.application.auth import ZkKeyMaterial
from ghostcal.config import get_settings

# Opaque placeholder zero-knowledge key material for registration in tests. The server stores it
# verbatim and never interprets it, so any base64 strings work.
ZK_PLACEHOLDER = ZkKeyMaterial(
    public_key="cHVibGljLWtleQ==",
    wrapped_private_key="d3JhcHBlZC1zaw==",
    wrap_salt="c2FsdA==",
    recovery_wrapped_private_key="cmVjb3Zlcnktd3JhcHBlZA==",
    recovery_salt="cmVjb3Zlcnktc2FsdA==",
)


def _no_database(reason: str) -> NoReturn:
    """Skip where a database is optional, fail where it is expected."""
    if os.environ.get("GHOSTCAL_TESTS_REQUIRE_DB") == "1":
        pytest.fail(f"integration database required but {reason}")
    pytest.skip(reason)


@pytest_asyncio.fixture
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    try:
        settings = get_settings()
    except Exception as exc:  # missing config => no DB available
        _no_database(f"settings unavailable: {exc}")
    if settings.database_admin_url is None:
        _no_database("GHOSTCAL_DATABASE_ADMIN_URL not configured")

    engine = create_async_engine(str(settings.database_admin_url))
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # database down
        await engine.dispose()
        _no_database(f"database unreachable: {exc}")
    try:
        yield engine
    finally:
        await engine.dispose()
