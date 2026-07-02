"""OIDC identity provisioning function

Adds a SECURITY DEFINER function that resolves an OIDC login to a local user: it returns the user
linked to an existing (provider, issuer, subject) identity, or — on first login — links the identity
to an existing account with the same (IdP-verified) email, or provisions a fresh passwordless
account (user + owner org + membership) with the email pre-verified. Runs as the owner so it can
write the global identity/user/org tables without an org RLS context, mirroring provision_account.

Revision ID: 47a95e221504
Revises: 1d35e1f10b91
Create Date: 2026-07-02

"""

from __future__ import annotations

from alembic import op

revision = "47a95e221504"
down_revision = "1d35e1f10b91"
branch_labels = None
depends_on = None

_SIG = "text, text, text, text, text, text, text"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION upsert_oidc_identity(
            p_provider text, p_issuer text, p_subject text,
            p_email text, p_name text, p_org_name text, p_org_slug text
        ) RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_user_id uuid;
            v_org_id uuid;
        BEGIN
            -- Returning user: the identity is already linked.
            SELECT user_id INTO v_user_id FROM identities
                WHERE provider = p_provider AND issuer = p_issuer AND subject = p_subject;
            IF v_user_id IS NOT NULL THEN
                RETURN v_user_id;
            END IF;

            -- First OIDC login. Link to an existing account with the same email (the IdP verified
            -- it), otherwise provision a fresh passwordless account with the email pre-verified.
            SELECT id INTO v_user_id FROM users WHERE email = p_email;
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
        $$;
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION upsert_oidc_identity({_SIG}) FROM PUBLIC")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
                GRANT EXECUTE ON FUNCTION upsert_oidc_identity({_SIG}) TO ghostcal_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS upsert_oidc_identity({_SIG})")
