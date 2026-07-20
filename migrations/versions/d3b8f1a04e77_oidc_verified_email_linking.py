"""require a verified email on both sides before linking an OIDC identity

`upsert_oidc_identity` linked an OIDC login to any local account sharing its email, on the strength
of a comment — *"(the IdP verified it)"* — that nothing enforced. Two distinct takeovers followed
from that, and they need two distinct checks.

**The IdP's side.** The callback never read the `email_verified` claim. On any provider that lets a
user set an address without proving ownership, an attacker sets theirs to the victim's, signs in,
and is linked straight into the victim's account. The claim is now required at the callback and
passed in here as ``p_email_verified``; a false or absent claim never reaches this function.

**Our side.** The linking branch did not care whether the *local* account was verified. So an
attacker could register the victim's address first, ignore the verification mail — leaving an
account they cannot log into, which looks inert — and wait. Their registration also ran
``store_zk_keys``, so that org's key is wrapped under the attacker's passphrase. When the victim
later signs in via SSO, the old code adopted the squatted row and seated them in the attacker's
organization, encrypting everything afterwards under a key the attacker can unwrap. Linking now
requires ``email_verified_at IS NOT NULL`` on the existing row, which a squatted account never has.

The provisioning branch keeps writing ``email_verified_at = now()``, and that is now honest: it is
only reachable once the IdP has asserted the address as verified. That matters beyond login, since
``accept_organization_invitation`` treats a verified email as proof of ownership — the invitation
binding was bypassable through exactly this path.

Revision ID: d3b8f1a04e77
Revises: f2a4cec11a6c
Create Date: 2026-07-20 16:20:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d3b8f1a04e77"
down_revision: str | Sequence[str] | None = "f2a4cec11a6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_SIG = "text, text, text, text, text, text, text"
_NEW_SIG = "text, text, text, text, text, text, text, boolean"


def upgrade() -> None:
    # Dropped rather than replaced: the signature gains a parameter, and leaving both overloads in
    # place would keep the permissive one callable.
    op.execute(f"DROP FUNCTION IF EXISTS upsert_oidc_identity({_OLD_SIG})")
    op.execute(
        """
        CREATE FUNCTION upsert_oidc_identity(
            p_provider text, p_issuer text, p_subject text, p_email text,
            p_name text, p_org_name text, p_org_slug text, p_email_verified boolean
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_user_id uuid;
            v_org_id uuid;
            v_verified timestamptz;
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
    op.execute(f"REVOKE ALL ON FUNCTION upsert_oidc_identity({_NEW_SIG}) FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        f"THEN GRANT EXECUTE ON FUNCTION upsert_oidc_identity({_NEW_SIG}) TO ghostcal_app; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS upsert_oidc_identity({_NEW_SIG})")
    op.execute(
        """
        CREATE FUNCTION upsert_oidc_identity(
            p_provider text, p_issuer text, p_subject text, p_email text,
            p_name text, p_org_name text, p_org_slug text
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_user_id uuid;
            v_org_id uuid;
        BEGIN
            SELECT user_id INTO v_user_id FROM identities
                WHERE provider = p_provider AND issuer = p_issuer AND subject = p_subject;
            IF v_user_id IS NOT NULL THEN
                RETURN v_user_id;
            END IF;
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
    op.execute(f"REVOKE ALL ON FUNCTION upsert_oidc_identity({_OLD_SIG}) FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        f"THEN GRANT EXECUTE ON FUNCTION upsert_oidc_identity({_OLD_SIG}) TO ghostcal_app; "
        "END IF; END $$;"
    )
