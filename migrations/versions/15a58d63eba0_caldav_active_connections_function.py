"""caldav active connections function

Revision ID: 15a58d63eba0
Revises: 2f53e39f1743
Create Date: 2026-06-27 22:24:11.565057

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "15a58d63eba0"
down_revision: str | Sequence[str] | None = "2f53e39f1743"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enumerate all active CalDAV connections for the periodic sync worker. caldav_connections is
    # RLS-protected; the worker has no org context, so this SECURITY DEFINER function lists them
    # (ids only). Each is then synced under its own org-scoped session.
    op.execute(
        """
        CREATE FUNCTION caldav_active_connections()
        RETURNS TABLE(id uuid, organization_id uuid, user_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT id, organization_id, user_id
            FROM caldav_connections
            WHERE status = 'active'
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION caldav_active_connections() FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
                GRANT EXECUTE ON FUNCTION caldav_active_connections() TO ghostcal_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS caldav_active_connections()")
