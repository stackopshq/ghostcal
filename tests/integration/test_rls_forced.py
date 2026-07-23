"""Every tenant table forces RLS, not merely enables it (live PostgreSQL).

`ENABLE` applies the policy to ordinary roles; `FORCE` applies it to the table's owner as well.
Four tables had only the first, across three feature migrations — a copy-paste omission rather than
a decision. This asserts the property for the whole set at once, so the next table to be added
cannot quietly join the exceptions.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_every_tenant_table_forces_row_level_security(admin_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(admin_engine)
    async with maker() as s:
        rows = (
            (
                await s.execute(
                    text(
                        "SELECT c.relname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                        "  AND c.relrowsecurity AND NOT c.relforcerowsecurity"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert list(rows) == [], f"RLS enabled but not forced on: {sorted(rows)}"
