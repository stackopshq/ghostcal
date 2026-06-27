"""organization id by slug function

Revision ID: 392bd3452e18
Revises: c5a249f4c400
Create Date: 2026-06-27 21:05:54.314344

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "392bd3452e18"
down_revision: str | Sequence[str] | None = "c5a249f4c400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Resolve an organization id from its public slug. organizations is RLS-protected, so a
    # plain app-role query can't read it before the org is known. This SECURITY DEFINER function
    # returns just the id for a given slug (public booking pages are slug-addressed).
    op.execute(
        """
        CREATE FUNCTION organization_id_by_slug(p_slug text) RETURNS uuid
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT id FROM organizations WHERE slug = p_slug
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION organization_id_by_slug(text) FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
                GRANT EXECUTE ON FUNCTION organization_id_by_slug(text) TO ghostcal_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS organization_id_by_slug(text)")
