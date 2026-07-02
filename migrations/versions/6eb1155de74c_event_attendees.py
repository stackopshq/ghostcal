"""event attendees

Guests invited to a personal calendar event (RLS-scoped). Two SECURITY DEFINER helpers let an
unauthenticated invitee, reached by a tokenised link, preview the event time and submit an RSVP
without an org context.

Revision ID: 6eb1155de74c
Revises: cf4775779ba3
Create Date: 2026-07-02 15:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6eb1155de74c"
down_revision: str | Sequence[str] | None = "cf4775779ba3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTIONS = (
    ("event_invitation_preview", "text", "(text)"),
    ("respond_to_event_invitation", "text, text", "(text, text)"),
)


def upgrade() -> None:
    op.create_table(
        "event_attendees",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="needs_action", nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('needs_action', 'accepted', 'declined', 'tentative')",
            name=op.f("ck_event_attendees_attendee_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["calendar_events.id"],
            name=op.f("fk_event_attendees_event_id_calendar_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_event_attendees_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_attendees")),
        sa.UniqueConstraint("event_id", "email", name=op.f("uq_event_attendees_event_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_event_attendees_token_hash")),
    )

    op.execute("ALTER TABLE event_attendees ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON event_attendees USING "
        "(organization_id = current_setting('app.current_org_id', true)::uuid) "
        "WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
    )

    # The invitee opens the link without an account: preview the event time + their current status.
    op.execute(
        """
        CREATE FUNCTION event_invitation_preview(p_token_hash text)
        RETURNS TABLE(start_at timestamptz, end_at timestamptz, timezone text, all_day boolean,
                      status text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT e.start_at, e.end_at, e.timezone, e.all_day, a.status
            FROM event_attendees a
            JOIN calendar_events e ON e.id = a.event_id
            WHERE a.token_hash = p_token_hash
        $$;
        """
    )
    # Record the RSVP. Returns true when a valid token was updated to an allowed status.
    op.execute(
        """
        CREATE FUNCTION respond_to_event_invitation(p_token_hash text, p_status text)
        RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_count int;
        BEGIN
            IF p_status NOT IN ('accepted', 'declined', 'tentative') THEN
                RETURN false;
            END IF;
            UPDATE event_attendees SET status = p_status WHERE token_hash = p_token_hash;
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
    op.drop_table("event_attendees")
