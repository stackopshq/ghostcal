"""publish a calendar to an external CalDAV server, without giving up zero-knowledge

A calendar may now be **published** to one of the member's connected CalDAV calendars, so their
GhostCal events show up on their phone.

The obvious way to do that is to let the server read the events and push them on a schedule. That
would work, and it would be the end of zero-knowledge for those calendars. So it is not what this
does.

Instead: **the server relays cleartext, and never stores it.** The browser holds the key, so the
browser is the only thing that can turn a sealed event into a VEVENT. It hands the cleartext to the
server at push time, the server forwards it to the CalDAV server, and nothing of it is written down.
That is not a new idea here — it is exactly what event invitations already do (see
``send_event_invitation_email``: "we only relay the invitation email built from browser-supplied
cleartext (never persisted)").

The cost, stated plainly: **a push waits for a browser.** There is no background reconciliation,
because there is nothing in the background that can read an event. Hence the queue: a write marks
the event as needing a push, and the next tab that opens with the key unlocked drains it. So the tab
does not have to be open at the moment of the change — only at some moment after it.

The queue is filled by a **trigger**, not by the application: every write path gets it, including the
ones written later by someone who never read this file. Deletes are why the queue has to exist at all
— once the row is gone there is nothing left to mark, so the UID is computed from the event id and
survives it.

Revision ID: b5e93a2f7c18
Revises: a3d5f8e21c64
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e93a2f7c18"
down_revision: str | Sequence[str] | None = "a3d5f8e21c64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendars",
        sa.Column(
            "push_connection_id",
            sa.Uuid(),
            sa.ForeignKey("caldav_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "calendar_push_queue",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "calendar_id",
            sa.Uuid(),
            sa.ForeignKey("calendars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # NULL for a delete: by then the event row is gone. The UID is what survives it.
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("calendar_events.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("external_uid", sa.String(512), nullable=False),
        sa.Column("op", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("op IN ('upsert', 'delete')", name="op_allowed"),
        # One pending operation per event: an upsert followed by a delete is a delete, not both.
        sa.UniqueConstraint("organization_id", "external_uid", name="uq_push_queue_uid"),
    )

    op.execute("ALTER TABLE calendar_push_queue ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE calendar_push_queue FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON calendar_push_queue USING "
        "(organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
        "WITH CHECK "
        "(organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
    )

    # The UID an event is published under. Deterministic, so a delete can still name it after the
    # row it referred to is gone.
    op.execute(
        """
        CREATE FUNCTION ghostcal_event_uid(p_event_id uuid)
        RETURNS text
        LANGUAGE sql IMMUTABLE
        AS $$ SELECT 'ghostcal-evt-' || p_event_id::text $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION enqueue_calendar_push()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_event calendar_events;
            v_op text;
            v_published boolean;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                v_event := OLD;
                v_op := 'delete';
            ELSE
                v_event := NEW;
                v_op := 'upsert';
            END IF;

            SELECT push_connection_id IS NOT NULL INTO v_published
            FROM calendars WHERE id = v_event.calendar_id;
            IF NOT COALESCE(v_published, false) THEN
                RETURN v_event;  -- the calendar publishes nowhere; nothing to queue
            END IF;

            INSERT INTO calendar_push_queue
                (organization_id, calendar_id, event_id, external_uid, op)
            VALUES (
                v_event.organization_id,
                v_event.calendar_id,
                CASE WHEN v_op = 'delete' THEN NULL ELSE v_event.id END,
                ghostcal_event_uid(v_event.id),
                v_op
            )
            ON CONFLICT (organization_id, external_uid) DO UPDATE SET
                op = EXCLUDED.op,
                event_id = EXCLUDED.event_id,
                created_at = now();

            RETURN v_event;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER enqueue_calendar_push_on_events
        AFTER INSERT OR UPDATE OR DELETE ON calendar_events
        FOR EACH ROW EXECUTE FUNCTION enqueue_calendar_push();
        """
    )

    # Publishing a calendar has to push what is already on it, not only what changes next.
    op.execute(
        """
        CREATE FUNCTION enqueue_calendar_backfill(p_calendar_id uuid)
        RETURNS bigint
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_count bigint;
        BEGIN
            INSERT INTO calendar_push_queue
                (organization_id, calendar_id, event_id, external_uid, op)
            SELECT e.organization_id, e.calendar_id, e.id, ghostcal_event_uid(e.id), 'upsert'
            FROM calendar_events e
            WHERE e.calendar_id = p_calendar_id
            ON CONFLICT (organization_id, external_uid) DO UPDATE SET
                op = 'upsert', event_id = EXCLUDED.event_id, created_at = now();
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count;
        END
        $$;
        """
    )

    for name, sig in (
        ("ghostcal_event_uid", "uuid"),
        ("enqueue_calendar_backfill", "uuid"),
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
            f"THEN GRANT EXECUTE ON FUNCTION {name}({sig}) TO ghostcal_app; END IF; END $$;"
        )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT SELECT, INSERT, UPDATE, DELETE ON calendar_push_queue TO ghostcal_app; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS enqueue_calendar_push_on_events ON calendar_events")
    op.execute("DROP FUNCTION IF EXISTS enqueue_calendar_backfill(uuid)")
    op.execute("DROP FUNCTION IF EXISTS enqueue_calendar_push()")
    op.execute("DROP FUNCTION IF EXISTS ghostcal_event_uid(uuid)")
    op.drop_table("calendar_push_queue")
    op.drop_column("calendars", "push_connection_id")
