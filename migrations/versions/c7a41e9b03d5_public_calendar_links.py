"""share a calendar outside the organization, by secret link

ADR-0005 said sharing beyond the org "would require granting them the org key — that reuses the
invitation-fragment grant (ADR-0003) and is deferred". That path is not merely deferred: it is
**wrong**, and worth spelling out so nobody takes it later.

The org key opens ``bookings.invitee_private`` (every invitee's answers, org-wide),
``calendar_events.content`` (every calendar of every member) and ``tasks.content``. Handing it to an
outsider so they can see **one** calendar would hand them the encrypted contents of the entire
organization. See ADR-0009.

So a link gets its **own keypair**. Its public key is stored here — a public key is public. Its
**private key never reaches the server**: it lives in the URL fragment, which browsers do not send.
The owner's browser seals a copy of each event to the link's public key; the visitor's browser opens
those copies with the private key it read out of the fragment.

The keypair (rather than a shared symmetric key) is what lets the owner keep adding events later:
to seal a new one they need only the *public* key, which is right here. A symmetric key would have
to be kept somewhere, and "somewhere" is how a secret stops being one.

Revision ID: c7a41e9b03d5
Revises: b5e93a2f7c18
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a41e9b03d5"
down_revision: str | Sequence[str] | None = "b5e93a2f7c18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_links",
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
        # Only the hash. The token is in the URL path and is shown to the owner exactly once.
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        # The link's X25519 PUBLIC key. The private half is in the fragment and never arrives here.
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_calendar_links_calendar", "calendar_links", ["calendar_id"])

    op.create_table(
        "calendar_link_events",
        sa.Column(
            "link_id",
            sa.Uuid(),
            sa.ForeignKey("calendar_links.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("calendar_events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The event's content, re-sealed to the LINK's public key. The org-sealed original stays
        # put; this is a second envelope, not a replacement.
        sa.Column("content_sealed", sa.Text(), nullable=False),
    )

    for table in ("calendar_links", "calendar_link_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING "
            "(organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
            "WITH CHECK "
            "(organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )

    # A changed event invalidates every sealed copy of it: the copies are now lies. Deleting them is
    # what makes them "pending" again, and the owner's browser re-seals them on its next visit. A
    # trigger, so every write path is covered — including the ones written later.
    op.execute(
        """
        CREATE FUNCTION invalidate_link_copies()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            DELETE FROM calendar_link_events WHERE event_id = NEW.id;
            RETURN NEW;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER invalidate_link_copies_on_events
        AFTER UPDATE ON calendar_events
        FOR EACH ROW EXECUTE FUNCTION invalidate_link_copies();
        """
    )

    # The visitor has no account and no organization, so they have no RLS context at all. This is
    # the only door they get: a token hash in, one calendar's sealed copies out. Nothing else is
    # reachable through it, and it returns ciphertext — the server could do no better if it wanted.
    op.execute(
        """
        CREATE FUNCTION public_calendar_by_token(p_token_hash text)
        RETURNS TABLE(
            link_id uuid, calendar_name text, owner_name text,
            event_id uuid, start_at timestamptz, end_at timestamptz, all_day boolean,
            timezone text, rrule text, exdates jsonb, content_sealed text
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT l.id, c.name, u.name,
                   e.id, e.start_at, e.end_at, e.all_day, e.timezone, e.rrule, e.exdates,
                   le.content_sealed
            FROM calendar_links l
            JOIN calendars c ON c.id = l.calendar_id
            JOIN users u ON u.id = c.owner_id
            LEFT JOIN calendar_link_events le ON le.link_id = l.id
            LEFT JOIN calendar_events e ON e.id = le.event_id
            WHERE l.token_hash = p_token_hash
        $$;
        """
    )

    for name, sig in (("public_calendar_by_token", "text"),):
        op.execute(f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
            f"THEN GRANT EXECUTE ON FUNCTION {name}({sig}) TO ghostcal_app; END IF; END $$;"
        )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT SELECT, INSERT, UPDATE, DELETE ON calendar_links, calendar_link_events "
        "TO ghostcal_app; END IF; END $$;"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public_calendar_by_token(text)")
    op.execute("DROP TRIGGER IF EXISTS invalidate_link_copies_on_events ON calendar_events")
    op.execute("DROP FUNCTION IF EXISTS invalidate_link_copies()")
    op.drop_table("calendar_link_events")
    op.drop_index("ix_calendar_links_calendar", table_name="calendar_links")
    op.drop_table("calendar_links")
