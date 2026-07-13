"""RLS: default-deny on a reused connection, instead of raising.

Every tenant policy reads the ``app.current_org_id`` GUC:

    USING (organization_id = current_setting('app.current_org_id', true)::uuid)

The intent — stated in the initial migration — was that an unbound session sees nothing: the GUC is
unset, ``current_setting(..., true)`` returns NULL, the comparison is NULL, no row matches.

That holds only on a connection that has *never* bound an organization. ``set_config(..., is_local
=> true)`` reverts the GUC at the end of the transaction, and PostgreSQL reverts a custom GUC to the
**empty string**, not to unset. So on any pooled connection that has already served one org-scoped
transaction, ``current_setting('app.current_org_id', true)`` returns ``''`` and the policy evaluates
``''::uuid`` — which raises ``invalid input syntax for type uuid: ""`` instead of denying.

It fails loudly rather than leaking, so this is not a disclosure. But the guarantee the code
documents is not the one the database enforces, and the first caller to rely on default-deny gets a
500 instead of an empty result. ``NULLIF(..., '')`` restores the documented behaviour.

Rewrites every ``tenant_isolation`` policy found in the catalog rather than a hand-kept list: they
were created across a dozen migrations, and a list would drift (``models.RLS_TABLES`` already has).

Revision ID: b2d8f30c17ae
Revises: a1c7e94b52f0
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b2d8f30c17ae"
down_revision: str | None = "a1c7e94b52f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# String concatenation rather than format(): '%s'/'%I' would be indistinguishable from driver bind
# placeholders on the way through. The tenant column is organization_id everywhere except on
# organizations itself (keyed by id) — read from the catalog, so no table can be missed.
_REWRITE = """
DO $$
DECLARE
    policy_row RECORD;
    tenant_column TEXT;
    predicate TEXT;
BEGIN
    FOR policy_row IN
        SELECT tablename FROM pg_policies
        WHERE schemaname = 'public' AND policyname = 'tenant_isolation'
    LOOP
        SELECT CASE WHEN EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = policy_row.tablename
              AND column_name = 'organization_id'
        ) THEN 'organization_id' ELSE 'id' END
        INTO tenant_column;

        predicate := quote_ident(tenant_column) || ' = ' || __GUC__;

        EXECUTE 'DROP POLICY tenant_isolation ON ' || quote_ident(policy_row.tablename);
        EXECUTE 'CREATE POLICY tenant_isolation ON ' || quote_ident(policy_row.tablename)
             || ' USING (' || predicate || ') WITH CHECK (' || predicate || ')';
    END LOOP;
END $$;
"""

# SQL literals holding the GUC expression; the inner quotes are doubled for the enclosing literal.
_FIXED = "'NULLIF(current_setting(''app.current_org_id'', true), '''')::uuid'"
_ORIGINAL = "'(current_setting(''app.current_org_id'', true))::uuid'"


def upgrade() -> None:
    op.execute(_REWRITE.replace("__GUC__", _FIXED))


def downgrade() -> None:
    op.execute(_REWRITE.replace("__GUC__", _ORIGINAL))
