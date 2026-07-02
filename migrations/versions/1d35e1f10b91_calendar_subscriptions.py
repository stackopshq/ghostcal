"""calendar subscriptions

Subscribed public ICS feeds (RLS-scoped) + a cache of their events. A SECURITY DEFINER enumerator
lets the background worker list active subscriptions across tenants to refresh them.

Revision ID: 1d35e1f10b91
Revises: 6eb1155de74c
Create Date: 2026-07-02 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import ghostcal.infrastructure.db.types

revision: str = "1d35e1f10b91"
down_revision: str | Sequence[str] | None = "6eb1155de74c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS = ("calendar_subscriptions", "subscription_events")


def upgrade() -> None:
    op.create_table(
        "calendar_subscriptions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_calendar_subscriptions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_calendar_subscriptions_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_subscriptions")),
    )
    op.create_table(
        "subscription_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("uid", sa.String(length=512), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("summary", ghostcal.infrastructure.db.types.EncryptedString(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_subscription_events_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_subscription_events_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["calendar_subscriptions.id"],
            name=op.f("fk_subscription_events_subscription_id_calendar_subscriptions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_events")),
        sa.UniqueConstraint(
            "subscription_id", "uid", name=op.f("uq_subscription_events_subscription_id")
        ),
    )
    op.create_index(
        "ix_subscription_events_org_start",
        "subscription_events",
        ["organization_id", "start_at"],
        unique=False,
    )

    for table in _RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING "
            f"(organization_id = current_setting('app.current_org_id', true)::uuid) "
            f"WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
        )

    # Enumerate subscriptions across tenants for the refresh worker (RLS-scoped table → controlled
    # read-only bypass; EXECUTE-only for the app role).
    op.execute(
        """
        CREATE FUNCTION active_subscriptions()
        RETURNS TABLE(organization_id uuid, subscription_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT organization_id, id FROM calendar_subscriptions WHERE status = 'active'
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION active_subscriptions() FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT EXECUTE ON FUNCTION active_subscriptions() TO ghostcal_app; END IF; END $$;"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS active_subscriptions()")
    op.drop_index("ix_subscription_events_org_start", table_name="subscription_events")
    op.drop_table("subscription_events")
    op.drop_table("calendar_subscriptions")
