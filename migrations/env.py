"""Alembic environment.

Migrations run with the **admin** connection (a privileged role that owns the schema and can
create RLS policies), taken from ``GHOSTCAL_DATABASE_ADMIN_URL`` (falling back to
``GHOSTCAL_DATABASE_URL``). The application itself connects with a non-privileged role.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql.schema import SchemaItem

# Import models so their tables register on Base.metadata for autogenerate.
import ghostcal.infrastructure.db.models  # noqa: F401
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _include_object(
    obj: SchemaItem,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """Keep autogenerate additive: propose what the models gained, never what they never had.

    A large part of this schema is created by hand-written SQL inside migrations — RLS policies,
    SECURITY DEFINER functions, triggers, and the partial and GiST indexes the booking engine
    relies on — and is deliberately not declared on any model. Autogenerate compares the models
    against the database, sees those objects on only one side, and reads them as things to
    delete. Run unfiltered against the current schema it proposes dropping the
    ``calendar_event_reminders`` table, six indexes (including
    ``uq_caldav_one_mirror_per_user``, which is what makes "exactly one mirror" true in the
    database rather than by convention) and three trigger-maintained ``updated_at`` columns.
    Accepting that output silently destroys the guarantees those objects exist to provide.

    An object that is in the database but on no model (``reflected`` with nothing to compare to)
    is therefore treated as hand-managed and left alone. The trade-off is that genuinely removing
    a model no longer autogenerates its ``DROP`` — which is the intended posture here: removals
    are written by hand, where the RLS and trigger fallout can be reasoned about.
    """
    return not (reflected and compare_to is None)


def _database_url() -> str:
    settings = get_settings()
    url = settings.database_admin_url or settings.database_url
    return str(url)


config.set_main_option("sqlalchemy.url", _database_url())


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
