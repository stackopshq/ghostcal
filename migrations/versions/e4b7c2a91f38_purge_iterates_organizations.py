"""the retention purge iterates organizations instead of spanning them

`purge_expired_bookings()` was one cross-tenant DELETE joined to `organizations`. Under FORCE ROW
LEVEL SECURITY, with the schema owned by a plain role and nothing declared, that join sees no
organizations — so the statement matched nothing and the function returned an empty set.

Measured, one organization with a 30-day window and a booking that ended 100 days ago:

    function owned by a plain role (production)  →  0 rows, the booking stays
    function owned by a superuser (what CI had)  →  1 row, the table is empty

Same call, same data, same application role. Only the owner differed — which is why the suite was
green while a retention window announced to customers went unhonoured. Keeping data past a period
we committed to is a confidentiality defect, not caution.

**This migration exists in a second version, and the first one is the reason.** It replaced the
cross-tenant DELETE with a `SECURITY DEFINER` enumeration function — which was blind for exactly the
same reason: SECURITY DEFINER changes the role a function runs as, never the session it runs in, so
under FORCE ROW LEVEL SECURITY it inherits no sight of its own. The remedy reproduced the defect,
and the witness that was supposed to catch it ran on a stack whose schema had been created by a
superuser. **When a fix is about privileges, the witness has to run under the real privileges** — a
test stack that owns its schema as a superuser cannot measure a defect whose cause is the owner. It
only proves its own configuration.

## What grants sight, and why it is a policy

The enumeration has to see rows while declaring no tenant — that is its whole job. Three shapes
existed, and two were rejected:

- **A role with BYPASSRLS.** A standing permission that a query written later could reach without
  anyone noticing. A policy is a predicate: it shows up in a diff, and what it widens is readable.
- **`NO FORCE ROW LEVEL SECURITY` on `organizations`.** This weakens the table entirely and forever,
  to serve an intermittent scan. The highest price of the three, paid permanently for an occasional
  benefit.
- **A policy read from a declared scan** — this one. Same "the application declares, the policy
  enforces, row by row" model as `bind_org` and `bind_user`, and the fourth of a family that already
  has `memberships_self_read`, `organizations_member_read` and `org_member_keys_self_read`.

It is deliberately the narrowest thing that works:

- **only organizations that actually have a window.** An organization with no retention policy does
  not become visible because a scan exists;
- **`FOR SELECT` only.** The scan reads; it does not modify;
- **the GUC is set by the worker and nowhere else**, for the length of the scan, and read in the
  tolerant form — `current_setting('app.retention_scan', true)` — like the three others. Without the
  second argument, `current_setting` raises when the variable was never set, and a policy that
  raises turns a clean refusal into a 500;
- **the function still returns `(organization_id, retention_days)` and nothing else.** Even under a
  scan it hands over no name, no slug, no count, no date.

Purging opportunistically as bookings are read was rejected too: it would leave dormant accounts
unpurged forever, and those are exactly the ones we undertook to erase. It reappears every few
months because it looks safer.

Revision ID: e4b7c2a91f38
Revises: f2a9c41e73b6
"""

from __future__ import annotations

from alembic import op

revision = "e4b7c2a91f38"
down_revision = "f2a9c41e73b6"
branch_labels = None
depends_on = None

_SCAN_POLICY = """
    CREATE POLICY organizations_retention_scan ON organizations
    FOR SELECT
    USING (
        booking_retention_days IS NOT NULL
        AND NULLIF(current_setting('app.retention_scan', true), '') = 'on'
    )
"""

_ENUMERATE = """
    CREATE OR REPLACE FUNCTION organizations_with_retention()
    RETURNS TABLE(organization_id uuid, retention_days integer)
    LANGUAGE sql STABLE
    SET search_path = pg_catalog, public
    AS $$
        SELECT id, booking_retention_days
        FROM organizations
        WHERE booking_retention_days IS NOT NULL
    $$;
"""

_OLD_PURGE = """
    CREATE OR REPLACE FUNCTION purge_expired_bookings()
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


def upgrade() -> None:
    op.execute(_SCAN_POLICY)
    # Not SECURITY DEFINER: the policy is what grants sight now, and it grants it to whoever
    # declares the scan — the owner included. A definer here would add a role change that changes
    # nothing, and one more function whose name suggests a boundary it does not hold.
    op.execute(_ENUMERATE)
    op.execute("REVOKE ALL ON FUNCTION organizations_with_retention() FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT EXECUTE ON FUNCTION organizations_with_retention() TO ghostcal_app; "
        "END IF; END $$;"
    )
    # The cross-tenant DELETE goes. Leaving it would leave a function that silently deletes
    # nothing, which is worse than none: the next reader would assume the purge is covered.
    op.execute("DROP FUNCTION IF EXISTS purge_expired_bookings()")


def downgrade() -> None:
    op.execute(_OLD_PURGE)
    op.execute("REVOKE ALL ON FUNCTION purge_expired_bookings() FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT EXECUTE ON FUNCTION purge_expired_bookings() TO ghostcal_app; "
        "END IF; END $$;"
    )
    op.execute("DROP FUNCTION IF EXISTS organizations_with_retention()")
    op.execute("DROP POLICY IF EXISTS organizations_retention_scan ON organizations")
