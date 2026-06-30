"""calendar foundation: calendars + calendar_events

A zero-knowledge personal calendar (see docs/adr/0004). Scheduling fields are cleartext
(start/end/all_day/timezone/rrule/exdates) so the server can expand recurrences and compute
free-busy; the event ``content`` (title/description/location) is a sealed blob the server can
never read. Both tables are tenant-scoped under RLS.

Revision ID: d4a1b2c3e5f6
Revises: c3f2e1d09a7b
Create Date: 2026-06-30 22:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4a1b2c3e5f6"
down_revision: str | Sequence[str] | None = "c3f2e1d09a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("calendars", "calendar_events")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} USING "
        "(organization_id = current_setting('app.current_org_id', true)::uuid) "
        "WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
    )


def upgrade() -> None:
    op.create_table(
        "calendars",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False, server_default="#00f0ff"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_calendars_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_calendars_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendars")),
    )

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("rrule", sa.Text(), nullable=True),
        sa.Column(
            "exdates", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        # Sealed blob {title, description, location} — encrypted to the org key; never read here.
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_calendar_events_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_calendar_events_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["calendars.id"],
            name=op.f("fk_calendar_events_calendar_id_calendars"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_events")),
    )
    op.create_index(
        "ix_calendar_events_org_start", "calendar_events", ["organization_id", "start_at"]
    )

    for table in _RLS_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    op.drop_index("ix_calendar_events_org_start", table_name="calendar_events")
    op.drop_table("calendar_events")
    op.drop_table("calendars")
