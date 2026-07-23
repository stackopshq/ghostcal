"""The server-side limits every application connection carries.

These are configured on the engine, which is easy to get subtly wrong (asyncpg wants them via
`server_settings`, not as SQL on connect) and impossible to notice when wrong — until a runaway
query pins a pool slot in production. So assert them on a real connection.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from ghostcal.config import get_settings
from ghostcal.infrastructure.db.session import db_session

pytestmark = pytest.mark.integration


async def test_application_connections_carry_the_configured_limits(admin_engine: object) -> None:
    settings = get_settings()
    async with db_session() as session:
        statement = (await session.execute(text("SHOW statement_timeout"))).scalar_one()
        idle = (
            await session.execute(text("SHOW idle_in_transaction_session_timeout"))
        ).scalar_one()
        name = (await session.execute(text("SHOW application_name"))).scalar_one()

    # Postgres reports these in its own units ("15s"), so compare in milliseconds.
    assert _ms(statement) == settings.db_statement_timeout_ms
    assert _ms(idle) == settings.db_idle_in_transaction_timeout_ms
    assert name == "ghostcal"


async def test_a_runaway_statement_is_cancelled_rather_than_holding_its_connection(
    admin_engine: object,
) -> None:
    # Sleep past the timeout and expect the server to cut it off. Without the setting this test
    # would simply wait, which is exactly the production failure it stands in for.
    async with db_session() as session:
        await session.execute(
            text("SET LOCAL statement_timeout = '250ms'")
        )  # keep the test fast; the mechanism is the same
        with pytest.raises(Exception, match=r"canceling statement|timeout"):
            await session.execute(text("SELECT pg_sleep(2)"))


def _ms(value: str) -> int:
    value = value.strip()
    if value.endswith("ms"):
        return int(value[:-2])
    if value.endswith("s"):
        return int(float(value[:-1]) * 1000)
    if value.endswith("min"):
        return int(value[:-3]) * 60_000
    return int(value)
