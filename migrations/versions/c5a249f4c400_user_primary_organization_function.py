"""user primary organization function

Revision ID: c5a249f4c400
Revises: 5f1ac9e25fd7
Create Date: 2026-06-27 14:29:12.123808

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5a249f4c400"
down_revision: str | Sequence[str] | None = "5f1ac9e25fd7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Resolve a user's organization without an org context. memberships is RLS-protected, so a
    # plain app-role query can't read it before the org is known (chicken-and-egg). This
    # SECURITY DEFINER function returns the user's primary org (first membership), bypassing RLS
    # in a controlled, read-only way. The app role only gets EXECUTE.
    op.execute(
        """
        CREATE FUNCTION user_primary_organization(p_user_id uuid) RETURNS uuid
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT organization_id
            FROM memberships
            WHERE user_id = p_user_id
            ORDER BY created_at
            LIMIT 1
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION user_primary_organization(uuid) FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
                GRANT EXECUTE ON FUNCTION user_primary_organization(uuid) TO ghostcal_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS user_primary_organization(uuid)")
