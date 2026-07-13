"""booking retention

Adds an opt-in retention window per organization: ``booking_retention_days``. NULL — the default,
and what every existing organization gets — means keep bookings forever, so this migration changes
no behaviour on its own. Setting it makes the worker purge bookings that ended longer ago than the
window (GDPR: personal data is not kept longer than necessary; see ADR-0006).

``purge_expired_bookings`` is SECURITY DEFINER because the worker has no org context and the purge
spans tenants, exactly like the reminder scans. It is the only irreversible periodic job in the
system, so the floor below is enforced in the database and not only in the application: a fat-
fingered ``booking_retention_days = 1`` must not be able to erase a company's history.

Revision ID: c9e4a71b6d38
Revises: b2d8f30c17ae
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e4a71b6d38"
down_revision: str | Sequence[str] | None = "b2d8f30c17ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A retention window shorter than this is refused. Bookings are the organization's operational
# record; anything under a month is far more likely to be a mistake than a policy.
MIN_RETENTION_DAYS = 30

_FUNCTIONS = (("purge_expired_bookings", "", "()"),)


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("booking_retention_days", sa.SmallInteger(), nullable=True)
    )
    op.create_check_constraint(
        "booking_retention_floor",
        "organizations",
        f"booking_retention_days IS NULL OR booking_retention_days >= {MIN_RETENTION_DAYS}",
    )

    # Deletes bookings that ENDED more than the org's window ago. Bookings still in the future, or
    # in orgs with no window set, are never touched. Returns how many rows went, per organization,
    # so the worker can log what it destroyed — a silent purge is an unauditable one.
    op.execute(
        """
        CREATE FUNCTION purge_expired_bookings()
        RETURNS TABLE(organization_id uuid, purged bigint)
        LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            WITH deleted AS (
                DELETE FROM bookings b
                USING organizations o
                WHERE o.id = b.organization_id
                  AND o.booking_retention_days IS NOT NULL
                  AND b.end_at < now() - make_interval(days => o.booking_retention_days)
                RETURNING b.organization_id
            )
            SELECT organization_id, count(*) AS purged
            FROM deleted
            GROUP BY organization_id
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
    op.drop_constraint("ck_organizations_booking_retention_floor", "organizations")
    op.drop_column("organizations", "booking_retention_days")
