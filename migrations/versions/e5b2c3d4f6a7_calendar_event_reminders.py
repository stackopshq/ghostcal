"""calendar event reminders

A reminder offset on calendar events + an idempotency table for sent reminders. Recurrence is
expanded in Python by the worker (it cannot be done in SQL), so the ``due`` function just returns
all reminder-enabled events with the owner's cleartext email and the cleartext scheduling fields;
the worker finds occurrences whose reminder moment has arrived and claims each one. The reminder
email never names the event (the content is zero-knowledge). See ADR-0004 (Phase 2).

Revision ID: e5b2c3d4f6a7
Revises: d4a1b2c3e5f6
Create Date: 2026-06-30 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b2c3d4f6a7"
down_revision: str | Sequence[str] | None = "d4a1b2c3e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("reminder_minutes", sa.Integer(), nullable=True))

    op.create_table(
        "calendar_event_reminders",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("occurrence_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["calendar_events.id"],
            name=op.f("fk_calendar_event_reminders_event_id_calendar_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_calendar_event_reminders_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_event_reminders")),
        sa.UniqueConstraint(
            "event_id", "occurrence_start", name=op.f("uq_calendar_event_reminders_event_id")
        ),
    )
    op.execute("ALTER TABLE calendar_event_reminders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE calendar_event_reminders FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON calendar_event_reminders USING "
        "(organization_id = current_setting('app.current_org_id', true)::uuid) "
        "WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
    )

    # Reminder-enabled events that could still have an upcoming occurrence (cross-tenant — the
    # worker has no org context, hence SECURITY DEFINER). The worker expands the recurrence.
    op.execute(
        """
        CREATE FUNCTION reminder_calendar_events()
        RETURNS TABLE(
            event_id uuid, organization_id uuid, owner_email text, owner_timezone text,
            start_at timestamptz, end_at timestamptz, timezone text, rrule text,
            exdates jsonb, reminder_minutes int
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT e.id, e.organization_id, u.email, u.timezone,
                   e.start_at, e.end_at, e.timezone, e.rrule, e.exdates, e.reminder_minutes
            FROM calendar_events e
            JOIN users u ON u.id = e.owner_id
            WHERE e.reminder_minutes IS NOT NULL
              AND (e.rrule IS NOT NULL OR e.end_at > now())
        $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION claim_calendar_event_reminder(
            p_event_id uuid, p_organization_id uuid, p_occurrence_start timestamptz
        )
        RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_count int;
        BEGIN
            INSERT INTO calendar_event_reminders (organization_id, event_id, occurrence_start)
            VALUES (p_organization_id, p_event_id, p_occurrence_start)
            ON CONFLICT (event_id, occurrence_start) DO NOTHING;
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count > 0;
        END
        $$;
        """
    )

    for fn in (
        "reminder_calendar_events()",
        "claim_calendar_event_reminder(uuid, uuid, timestamptz)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
            f"THEN GRANT EXECUTE ON FUNCTION {fn} TO ghostcal_app; END IF; END $$;"
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS claim_calendar_event_reminder(uuid, uuid, timestamptz)")
    op.execute("DROP FUNCTION IF EXISTS reminder_calendar_events()")
    op.drop_table("calendar_event_reminders")
    op.drop_column("calendar_events", "reminder_minutes")
