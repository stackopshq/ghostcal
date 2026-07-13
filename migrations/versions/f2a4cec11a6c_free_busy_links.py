"""free-busy links

A link that shows *when* someone is busy, and never *what* they are doing.

Unlike ``calendar_links`` (ADR-0009), this one carries no key: there is nothing to decrypt, because
there is nothing sealed to hand over. Busy times are already cleartext on the server — the scheduler
has to reason about them — so a free-busy link discloses strictly what the server already knows.

That is the whole security story, and it is a good one. There is no fragment, so there is no secret
to leak beyond the token: whoever finds it learns when the owner is occupied, and never once what
occupies them.

Revision ID: f2a4cec11a6c
Revises: c7a41e9b03d5
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a4cec11a6c"
down_revision: str | Sequence[str] | None = "c7a41e9b03d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "busy_links",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # A person, not a calendar: "am I free?" cannot be answered by one calendar while the
        # others are ignored.
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        # Only the hash. The token is in the URL path and is shown to the owner exactly once.
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_busy_links_user", "busy_links", ["user_id"])

    op.execute("ALTER TABLE busy_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE busy_links FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON busy_links USING "
        "(organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
        "WITH CHECK "
        "(organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
    )

    # The visitor has no account and no organization, so no RLS context. This resolves their token
    # to the person it belongs to — and to nothing else. It returns no times: the busy intervals are
    # then read through the ordinary, RLS-scoped query the scheduler itself uses, so there is
    # exactly one definition of "busy" in the system and this door cannot drift from it.
    op.execute(
        """
        CREATE FUNCTION busy_link_by_token(p_token_hash text)
        RETURNS TABLE(organization_id uuid, user_id uuid, owner_name text, owner_timezone text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT l.organization_id, l.user_id, u.name, u.timezone
            FROM busy_links l
            JOIN users u ON u.id = l.user_id
            WHERE l.token_hash = p_token_hash
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION busy_link_by_token(text) FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT EXECUTE ON FUNCTION busy_link_by_token(text) TO ghostcal_app; END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT SELECT, INSERT, UPDATE, DELETE ON busy_links TO ghostcal_app; END IF; END $$;"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS busy_link_by_token(text)")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON busy_links")
    op.drop_index("ix_busy_links_user", table_name="busy_links")
    op.drop_table("busy_links")
