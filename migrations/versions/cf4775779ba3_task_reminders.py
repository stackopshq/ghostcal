"""task reminders

Adds a content-less reminder to tasks: ``reminder_minutes`` (minutes before ``due_at`` to email the
owner) and ``reminded_at`` (idempotency). Two SECURITY DEFINER helpers let the background worker,
which has no org context, list due reminders across tenants and atomically claim each.

Revision ID: cf4775779ba3
Revises: 2d0861e4082b
Create Date: 2026-07-02 13:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cf4775779ba3"
down_revision: str | Sequence[str] | None = "2d0861e4082b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTIONS = (
    ("due_task_reminders", "", "()"),
    ("claim_task_reminder", "uuid, uuid", "(uuid, uuid)"),
)


def upgrade() -> None:
    op.add_column("tasks", sa.Column("reminder_minutes", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))

    # Reminder-enabled, incomplete, not-yet-reminded tasks whose reminder moment has passed. A grace
    # window (fire until 1 day after due) avoids ancient backfill spam after long worker downtime.
    op.execute(
        """
        CREATE FUNCTION due_task_reminders()
        RETURNS TABLE(
            task_id uuid, organization_id uuid, owner_email text, owner_timezone text,
            due_at timestamptz, reminder_minutes int
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT t.id, t.organization_id, u.email, u.timezone, t.due_at, t.reminder_minutes
            FROM tasks t
            JOIN users u ON u.id = t.owner_id
            WHERE t.reminder_minutes IS NOT NULL
              AND t.reminded_at IS NULL
              AND t.completed = false
              AND t.due_at IS NOT NULL
              AND now() >= t.due_at - make_interval(mins => t.reminder_minutes)
              AND now() < t.due_at + interval '1 day'
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION claim_task_reminder(p_task_id uuid, p_organization_id uuid)
        RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_count int;
        BEGIN
            UPDATE tasks SET reminded_at = now()
            WHERE id = p_task_id AND organization_id = p_organization_id AND reminded_at IS NULL;
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count > 0;
        END
        $$;
        """
    )
    for name, sig, _drop in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
            f"THEN GRANT EXECUTE ON FUNCTION {name}({sig}) TO ghostcal_app; END IF; END $$;"
        )


def downgrade() -> None:
    for name, _sig, drop in _FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {name}{drop}")
    op.drop_column("tasks", "reminded_at")
    op.drop_column("tasks", "reminder_minutes")
