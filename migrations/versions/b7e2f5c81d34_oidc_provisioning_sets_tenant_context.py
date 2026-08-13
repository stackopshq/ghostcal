"""oidc provisioning sets the tenant context it is about to create

Provisioning the very first organization was impossible. `organizations` and
`memberships` both carry FORCE ROW LEVEL SECURITY with a single `tenant_isolation`
policy requiring `app.current_org_id` to already equal the row's organization —
so the INSERT that *creates* the tenant cannot pass, because the id it will be
checked against does not exist until that INSERT runs.

FORCE is what makes it inescapable: without it, the table owner would be exempt
and the SECURITY DEFINER function would have gone through. With it, nobody is
exempt, which is the right posture for tenant data and the wrong one for the one
write that has no tenant yet.

Measured on 2026-08-13, replaying the call in a rolled-back transaction:

    ERROR:  new row violates row-level security policy for table "organizations"
    CONTEXT:  SQL statement "INSERT INTO organizations (name, slug) ..."

**And it never looked like that from the outside.** An RLS violation raises
SQLSTATE 42501 — `insufficient_privilege` — the same code the function itself
uses to say "I refuse to link this identity". The repository maps that code to
`OidcIdentityRefused`, so a structural impossibility surfaced as a policy
decision, and the login page merely hid its SSO button.

The fix keeps the policy exactly as it is. The function generates the org id
itself, sets `app.current_org_id` to that value for the remainder of the
transaction, then inserts. No permissive hole is opened: the only rows that pass
are the ones this function is creating, and the previous setting is restored so
a caller doing more work in the same transaction is not left in a tenant context
it did not choose.

Revision ID: b7e2f5c81d34
Revises: a1c7d4e90b23
"""

from __future__ import annotations

from alembic import op

revision = "b7e2f5c81d34"
down_revision = "a1c7d4e90b23"
branch_labels = None
depends_on = None

_BODY = """
    DECLARE
        v_user_id uuid;
        v_org_id uuid;
        v_verified timestamptz;
        v_prev_org text;
    BEGIN
        -- Returning user: the identity is already linked, so none of the email reasoning
        -- applies — the binding was established on a previous login.
        SELECT user_id INTO v_user_id FROM identities
            WHERE provider = p_provider AND issuer = p_issuer AND subject = p_subject;
        IF v_user_id IS NOT NULL THEN
            RETURN v_user_id;
        END IF;

        -- First login for this subject. Refuse outright unless the IdP vouched for the
        -- address: everything below treats the email as proof of who the caller is.
        IF p_email_verified IS NOT TRUE THEN
            RAISE EXCEPTION 'oidc email not verified by the provider'
                USING ERRCODE = 'insufficient_privilege';
        END IF;

        SELECT id, email_verified_at INTO v_user_id, v_verified
            FROM users WHERE email = p_email;

        IF v_user_id IS NOT NULL AND v_verified IS NULL THEN
            -- An account exists on this address but never proved ownership of it. Adopting it
            -- would hand the SSO user whatever the squatter set up, including the org key.
            RAISE EXCEPTION 'an unverified local account already holds this email'
                USING ERRCODE = 'insufficient_privilege';
        END IF;

        IF v_user_id IS NULL THEN
            INSERT INTO users (email, name, timezone, email_verified_at)
                VALUES (p_email, p_name, 'UTC', now())
                RETURNING id INTO v_user_id;

            -- The id is generated here rather than by the column default, because the
            -- tenant_isolation policy on `organizations` is checked against it and there is
            -- otherwise nothing to point `app.current_org_id` at: the row that defines the
            -- tenant is the row being inserted. FORCE ROW LEVEL SECURITY means even the table
            -- owner is subject to that check, so SECURITY DEFINER alone does not get through.
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
        END IF;

        INSERT INTO identities (user_id, provider, issuer, subject)
            VALUES (v_user_id, p_provider, p_issuer, p_subject)
            ON CONFLICT (provider, issuer, subject) DO NOTHING;
        RETURN v_user_id;
    END;
"""

_PREVIOUS_BODY = """
    DECLARE
        v_user_id uuid;
        v_org_id uuid;
        v_verified timestamptz;
    BEGIN
        SELECT user_id INTO v_user_id FROM identities
            WHERE provider = p_provider AND issuer = p_issuer AND subject = p_subject;
        IF v_user_id IS NOT NULL THEN
            RETURN v_user_id;
        END IF;

        IF p_email_verified IS NOT TRUE THEN
            RAISE EXCEPTION 'oidc email not verified by the provider'
                USING ERRCODE = 'insufficient_privilege';
        END IF;

        SELECT id, email_verified_at INTO v_user_id, v_verified
            FROM users WHERE email = p_email;

        IF v_user_id IS NOT NULL AND v_verified IS NULL THEN
            RAISE EXCEPTION 'an unverified local account already holds this email'
                USING ERRCODE = 'insufficient_privilege';
        END IF;

        IF v_user_id IS NULL THEN
            INSERT INTO users (email, name, timezone, email_verified_at)
                VALUES (p_email, p_name, 'UTC', now())
                RETURNING id INTO v_user_id;
            INSERT INTO organizations (name, slug)
                VALUES (p_org_name, p_org_slug)
                RETURNING id INTO v_org_id;
            INSERT INTO memberships (organization_id, user_id, role)
                VALUES (v_org_id, v_user_id, 'owner');
        END IF;

        INSERT INTO identities (user_id, provider, issuer, subject)
            VALUES (v_user_id, p_provider, p_issuer, p_subject)
            ON CONFLICT (provider, issuer, subject) DO NOTHING;
        RETURN v_user_id;
    END;
"""

_DECL = """
    CREATE OR REPLACE FUNCTION upsert_oidc_identity(
        p_provider text, p_issuer text, p_subject text, p_email text,
        p_name text, p_org_name text, p_org_slug text, p_email_verified boolean
    ) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
    AS $$%s$$
"""


def upgrade() -> None:
    op.execute(_DECL % _BODY)


def downgrade() -> None:
    op.execute(_DECL % _PREVIOUS_BODY)
