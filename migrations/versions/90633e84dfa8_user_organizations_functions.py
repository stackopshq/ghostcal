"""user organizations functions

Revision ID: 90633e84dfa8
Revises: 84db310aacb3
Create Date: 2026-06-28 06:48:50.667755

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "90633e84dfa8"
down_revision: str | Sequence[str] | None = "84db310aacb3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # All organizations a user belongs to (memberships is RLS-protected, so this needs a controlled
    # bypass to enumerate across tenants). Used by the org switcher.
    op.execute(
        """
        CREATE FUNCTION user_organizations(p_user_id uuid)
        RETURNS TABLE(organization_id uuid, name text, slug text, role text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT o.id, o.name, o.slug, m.role
            FROM memberships m
            JOIN organizations o ON o.id = m.organization_id
            WHERE m.user_id = p_user_id
            ORDER BY m.created_at
        $$;
        """
    )
    # A user's role in a specific org, or NULL if they are not a member (validates a chosen org).
    op.execute(
        """
        CREATE FUNCTION user_role_in_org(p_user_id uuid, p_org_id uuid)
        RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT role FROM memberships
            WHERE user_id = p_user_id AND organization_id = p_org_id
        $$;
        """
    )
    for fn in ("user_organizations(uuid)", "user_role_in_org(uuid, uuid)"):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
            f"THEN GRANT EXECUTE ON FUNCTION {fn} TO ghostcal_app; END IF; END $$;"
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS user_role_in_org(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS user_organizations(uuid)")
