"""Shared fixtures for database integration tests.

The admin engine uses the privileged (superuser) connection, which bypasses RLS — used only to
seed data. Code under test uses the application connection via ``org_session``. Tests are skipped
automatically when no database is reachable (e.g. CI without infra).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ghostcal.config import get_settings


@pytest_asyncio.fixture
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    try:
        settings = get_settings()
    except Exception as exc:  # missing config => no DB available
        pytest.skip(f"settings unavailable: {exc}")
    if settings.database_admin_url is None:
        pytest.skip("GHOSTCAL_DATABASE_ADMIN_URL not configured")

    engine = create_async_engine(str(settings.database_admin_url))
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # database down
        await engine.dispose()
        pytest.skip(f"database unreachable: {exc}")
    try:
        yield engine
    finally:
        await engine.dispose()
