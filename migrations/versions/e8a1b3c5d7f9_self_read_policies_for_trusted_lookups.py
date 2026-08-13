"""self-read policies, so the trusted layer works without any RLS bypass

**What was broken, and why CI never saw it.** Every RLS table carries FORCE ROW
LEVEL SECURITY — deliberately, `test_rls_forced.py` pins it. FORCE subjects the
table *owner* to the policy, and the owner is `ghostcal`, the role that owns and
executes every SECURITY DEFINER function. In production the whole trusted layer
was therefore blind: `user_primary_organization()` returned NULL for a user whose
membership sat in the table, and `store_zk_keys` raised "no owner organization
for user" right after provisioning had created that very membership.

CI never caught it because its bootstrap makes `ghostcal` the container's
POSTGRES_USER — a **superuser**, and superusers bypass RLS entirely, FORCE or
not. The product had never run with a non-superuser owner before 2026-08-13.

**Why not BYPASSRLS, and why not dropping FORCE.** Both produce the same state:
the trusted role sees every row of every tenant, always — one bad join in any of
seventeen definer functions leaks or edits another tenant's data, with no net
underneath. The choice made here keeps the net tensioned under the trusted code
itself.

**The mechanism.** RLS policies are permissive — they OR together. Two narrow
additions:

  * `memberships_self_read`: a membership row is visible when it belongs to the
    user the application has declared via `app.current_user_id`.
  * `organizations_member_read`: an organization row is visible when that same
    declared user is one of its members.

Both are SELECT-only. Writes still require the tenant context
(`app.current_org_id`), exactly as before. The application declares who it is
acting for — same trust model as the tenant GUC that already underpins every
policy — and the resolvers' internal queries pass on their own merits, row by
row. Nothing traverses tenants: a resolver sees the caller's memberships and the
caller's organizations, and nothing else.

**Known not-covered:** `purge_expired_bookings` and `stamp_zk_generation` are
genuinely cross-tenant batch jobs; they iterate organizations and stay blind
under FORCE. They were already broken in production before this migration and
need their own treatment (likely an explicit per-org iteration driven from the
worker, which can bind each org in turn).

Revision ID: e8a1b3c5d7f9
Revises: b7e2f5c81d34
"""

from __future__ import annotations

from alembic import op

revision = "e8a1b3c5d7f9"
down_revision = "b7e2f5c81d34"
branch_labels = None
depends_on = None

_USER_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE POLICY memberships_self_read ON memberships
            FOR SELECT
            USING (user_id = {_USER_GUC})
        """
    )
    op.execute(
        f"""
        CREATE POLICY organizations_member_read ON organizations
            FOR SELECT
            USING (id IN (SELECT m.organization_id FROM memberships m
                          WHERE m.user_id = {_USER_GUC}))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS organizations_member_read ON organizations")
    op.execute("DROP POLICY IF EXISTS memberships_self_read ON memberships")
