"""stop FORCE-ing RLS on the owner, which blinded every SECURITY DEFINER function

Every RLS table in this schema carried FORCE ROW LEVEL SECURITY. FORCE means the
table *owner* is subject to the policy too — and the owner is `ghostcal`, the role
that owns and runs every SECURITY DEFINER function in the codebase.

So the entire trusted layer was blind. Not partly: blind. `store_zk_keys` looked
up the caller's organization in `memberships`, saw nothing, and raised "no owner
organization for user" while that membership sat in the table. `upsert_oidc_identity`
could not insert the organization it was creating. At least ten definer functions
read `memberships` or `organizations` and were affected the same way.

This module's own docstring said "goes through a SECURITY DEFINER function so the
org/membership inserts bypass RLS in a controlled way". That is precisely what
FORCE cancels, and nothing anywhere said so.

**Removing FORCE costs no protection against the threat this design guards against.**
Measured on 2026-08-13: `ghostcal_app` — the role the application connects as —
**owns no table at all**. It is therefore subject to RLS with or without FORCE. The
only role FORCE constrained was the owner, which is to say the trusted code that is
supposed to be able to see across tenants in order to establish one.

What each role can do after this:

    ghostcal_app   application connections   fully constrained by tenant_isolation
    ghostcal       migrations + definer fns  exempt, as the code has always assumed

Written as a loop over `pg_class` rather than a fixed list, so a table added later
does not silently reintroduce the problem for whoever adds it.

Revision ID: c4d9a7f21e08
Revises: b7e2f5c81d34
"""

from __future__ import annotations

from alembic import op

revision = "c4d9a7f21e08"
down_revision = "b7e2f5c81d34"
branch_labels = None
depends_on = None


def _apply(force: bool) -> None:
    keyword = "FORCE" if force else "NO FORCE"
    op.execute(
        f"""
        DO $$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT c.relname
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity
            LOOP
                EXECUTE format(
                    'ALTER TABLE public.%I {keyword} ROW LEVEL SECURITY', r.relname
                );
            END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    _apply(force=False)


def downgrade() -> None:
    _apply(force=True)
