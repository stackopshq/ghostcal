"""tasks todo

Zero-knowledge to-do items (Fantastical-style): sealed ``content`` blob the server can't read, plus
cleartext due date and completion state. RLS-scoped to the tenant, like the calendar tables.

Revision ID: 2d0861e4082b
Revises: b9c0d1e2f3a4
Create Date: 2026-07-02 12:27:44.051520

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2d0861e4082b"
down_revision: str | Sequence[str] | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_tasks_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_tasks_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("ix_tasks_owner_due", "tasks", ["owner_id", "due_at"], unique=False)

    # Tenant isolation, same policy shape as the calendar tables (applies to the app role; the
    # owner/migration role is exempt, so nothing else changes).
    op.execute("ALTER TABLE tasks ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON tasks USING "
        "(organization_id = current_setting('app.current_org_id', true)::uuid) "
        "WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_owner_due", table_name="tasks")
    op.drop_table("tasks")
