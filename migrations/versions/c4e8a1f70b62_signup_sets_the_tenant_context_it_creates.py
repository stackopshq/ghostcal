"""signup sets the tenant context it is about to create

`upsert_oidc_identity` was given this exact fix on 2026-08-13 (b7e2f5c81d34) and
`provision_account` — its twin, the one every password signup goes through — was
not. The two functions create the same three rows for the same reason; only one
of them learned to bind the tenant first.

`organizations` and `memberships` carry FORCE ROW LEVEL SECURITY with a single
`tenant_isolation` policy requiring `app.current_org_id` to already equal the
row's organization. The INSERT that *creates* the tenant therefore cannot pass:
the id it is checked against does not exist until that INSERT runs. FORCE is
what makes it inescapable — without it the table owner would be exempt and
SECURITY DEFINER would have carried the write through.

**Which is why nobody saw it.** SECURITY DEFINER runs the body as the function's
owner, and the owner is whoever ran the migrations. In `compose.yaml` that is
`ghostcal`, the container's POSTGRES_USER, a superuser — and a superuser is
exempt from RLS entirely, FORCE or not. So the defect is invisible on every
development stack and in CI, and appears only where the schema is owned by a
plain role, which is how production has run since 2026-08-13. The fix for the
OIDC twin shipped the same day the ownership changed; this path was never
replayed under the new shape.

Measured on 2026-08-30 against a stack whose schema owner is NOSUPERUSER
NOBYPASSRLS, running `tests/integration/test_auth.py::test_full_auth_flow`
unchanged:

    sqlalchemy.exc.ProgrammingError: InsufficientPrivilegeError:
      new row violates row-level security policy for table "organizations"
    [SQL: SELECT user_id FROM provision_account($1, $2, $3, $4, $5)]

Every password registration returned 500. The fix is the twin's, verbatim in
shape: generate the organization id here, point `app.current_org_id` at it for
the rest of the transaction, insert, then restore the previous setting so a
caller doing more work in the same transaction is not left inside a tenant it
never chose. No policy is relaxed and no hole is opened — the only rows that
pass are the ones this function is creating.

Revision ID: c4e8a1f70b62
Revises: d1f4a72b98c0
"""

from __future__ import annotations

from alembic import op

revision = "c4e8a1f70b62"
down_revision = "d1f4a72b98c0"
branch_labels = None
depends_on = None

_BODY = """
    DECLARE
        v_user_id uuid;
        v_org_id uuid;
        v_prev_org text;
    BEGIN
        INSERT INTO users (email, name, timezone)
            VALUES (p_email, p_name, 'UTC')
            RETURNING id INTO v_user_id;
        INSERT INTO user_credentials (user_id, password_hash)
            VALUES (v_user_id, p_password_hash);

        -- The id is generated here rather than by the column default, because the
        -- tenant_isolation policy on `organizations` is checked against it and there is
        -- otherwise nothing to point `app.current_org_id` at: the row that defines the
        -- tenant is the row being inserted.
        v_org_id := gen_random_uuid();
        v_prev_org := current_setting('app.current_org_id', true);
        PERFORM set_config('app.current_org_id', v_org_id::text, true);

        INSERT INTO organizations (id, name, slug)
            VALUES (v_org_id, p_org_name, p_org_slug);
        INSERT INTO memberships (organization_id, user_id, role)
            VALUES (v_org_id, v_user_id, 'owner');

        -- Restored so a caller doing more work in this transaction is not silently left
        -- inside a tenant it never selected. `true` keeps both calls transaction-local.
        PERFORM set_config('app.current_org_id', coalesce(v_prev_org, ''), true);

        RETURN QUERY SELECT v_user_id, v_org_id;
    END;
"""

_PREVIOUS_BODY = """
    DECLARE
        v_user_id uuid;
        v_org_id uuid;
    BEGIN
        INSERT INTO users (email, name, timezone)
            VALUES (p_email, p_name, 'UTC')
            RETURNING id INTO v_user_id;
        INSERT INTO user_credentials (user_id, password_hash)
            VALUES (v_user_id, p_password_hash);
        INSERT INTO organizations (name, slug)
            VALUES (p_org_name, p_org_slug)
            RETURNING id INTO v_org_id;
        INSERT INTO memberships (organization_id, user_id, role)
            VALUES (v_org_id, v_user_id, 'owner');
        RETURN QUERY SELECT v_user_id, v_org_id;
    END;
"""

_DECL = """
    CREATE OR REPLACE FUNCTION provision_account(
        p_email text, p_name text, p_password_hash text, p_org_name text, p_org_slug text
    ) RETURNS TABLE(user_id uuid, organization_id uuid)
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
    AS $$%s$$
"""


def upgrade() -> None:
    op.execute(_DECL % _BODY)


def downgrade() -> None:
    op.execute(_DECL % _PREVIOUS_BODY)
