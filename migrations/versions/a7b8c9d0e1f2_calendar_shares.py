"""calendar shares (within-org read-only calendar sharing)

Map a calendar to the org members it is shared with. Sharing is pure authorization — the events
stay sealed to the org key the members already hold (see ADR-0005). Org-scoped under RLS.

Revision ID: a7b8c9d0e1f2
Revises: f6c3d4e5a7b8
Create Date: 2026-07-01 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6c3d4e5a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_shares",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("shared_with_user_id", sa.Uuid(), nullable=False),
        sa.Column("can_edit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_calendar_shares_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["calendars.id"],
            name=op.f("fk_calendar_shares_calendar_id_calendars"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shared_with_user_id"],
            ["users.id"],
            name=op.f("fk_calendar_shares_shared_with_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_shares")),
        sa.UniqueConstraint(
            "calendar_id", "shared_with_user_id", name=op.f("uq_calendar_shares_calendar_id")
        ),
    )
    op.create_index("ix_calendar_shares_shared_with", "calendar_shares", ["shared_with_user_id"])
    op.execute("ALTER TABLE calendar_shares ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE calendar_shares FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON calendar_shares USING "
        "(organization_id = current_setting('app.current_org_id', true)::uuid) "
        "WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_shares_shared_with", table_name="calendar_shares")
    op.drop_table("calendar_shares")
