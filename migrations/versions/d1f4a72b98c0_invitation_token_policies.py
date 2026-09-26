"""token-declaring policies, so an invitation link can be opened by its invitee

**What was broken.** Every team invitation link answered "invitation not found or
expired", from the day FORCE ROW LEVEL SECURITY was rolled out. Not one had ever
worked.

`organization_invitations` carries FORCE ROW LEVEL SECURITY, which subjects the
table *owner* to the policies too — and the owner in production is `ghostcal`, a
role that is neither superuser nor BYPASSRLS. So `organization_invitation_preview`
and `accept_organization_invitation`, both SECURITY DEFINER and both running as
that owner, inherit no sight at all. Their only policy, `tenant_isolation`, keys
off `app.current_org_id`, and an invitee opening a link is not authenticated and
belongs to no organization yet: the GUC is empty, the policy filters every row,
and the function returns nothing. The route reads that as an invalid token.

**Why CI never saw it.** The integration tests exercise the preview, and they
pass. In CI the owner is `POSTGRES_USER: ghostcal`, the cluster's *bootstrap
superuser* — and a superuser bypasses RLS whatever FORCE says. The test and
production differ by one role attribute, and it is the attribute the whole
mechanism turns on. Measured on 2026-08-29: same schema, same query, same data —
`1` with a superuser owner, `0` with a plain one.

This is the second time this class of bug has shipped; migration e8a1b3c5d7f9
fixed it for `memberships` and `organizations` with the same reasoning. The
lesson it carries forward: a SECURITY DEFINER function under FORCE RLS sees
nothing it has not been given a policy for.

**The fix, and why not a bypass.** The caller declares the token hash it already
holds, and the policies open exactly the row that matches it — the same
"application declares, policies enforce" shape as `bind_user`. The GUC is set
inside the definer functions only, transaction-local, and never from user input
that has not already been hashed. Granting BYPASSRLS or dropping FORCE would open
every row instead of one, and would do it for every caller.

Revision ID: d1f4a72b98c0
Revises: c3f81d276ea4
"""

from __future__ import annotations

from alembic import op

revision = "d1f4a72b98c0"
down_revision = "c3f81d276ea4"
branch_labels = None
depends_on = None

_DECLARED = "NULLIF(current_setting('app.invitation_token_hash', true), '')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE POLICY invitations_token_read ON organization_invitations
            FOR SELECT USING (token_hash = {_DECLARED})
        """
    )
    # The accept path marks the row consumed; same key, so a token can only ever
    # close its own invitation.
    op.execute(
        f"""
        CREATE POLICY invitations_token_accept ON organization_invitations
            FOR UPDATE USING (token_hash = {_DECLARED})
        """
    )
    # The preview shows the organization's name, so that row must be reachable
    # too — but only through an invitation that names it.
    op.execute(
        f"""
        CREATE POLICY organizations_invitation_read ON organizations
            FOR SELECT USING (
                id IN (
                    SELECT i.organization_id FROM organization_invitations i
                    WHERE i.token_hash = {_DECLARED}
                )
            )
        """
    )

    # VOLATILE, not STABLE: it now writes a setting. plpgsql also checks the
    # returned row types strictly, hence the explicit casts off varchar.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION organization_invitation_preview(p_token_hash text)
        RETURNS TABLE(
            organization_id uuid, organization_name text, email text, role text,
            wrapped_org_key text
        )
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $fn$
        BEGIN
            PERFORM set_config('app.invitation_token_hash', p_token_hash, true);
            RETURN QUERY
                SELECT i.organization_id, o.name::text, i.email::text, i.role::text,
                       i.wrapped_org_key::text
                FROM organization_invitations i
                JOIN organizations o ON o.id = i.organization_id
                WHERE i.token_hash = p_token_hash
                  AND i.accepted_at IS NULL
                  AND i.expires_at > now();
        END
        $fn$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION accept_organization_invitation(
            p_token_hash text, p_user_id uuid
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $fn$
        DECLARE
            v_org uuid;
            v_role text;
            v_email text;
        BEGIN
            PERFORM set_config('app.invitation_token_hash', p_token_hash, true);
            SELECT organization_id, role, email INTO v_org, v_role, v_email
            FROM organization_invitations
            WHERE token_hash = p_token_hash
              AND accepted_at IS NULL
              AND expires_at > now()
            FOR UPDATE;
            IF v_org IS NULL THEN
                RETURN NULL;
            END IF;
            -- Only the verified owner of the invited address may accept
            -- (defence against link leakage).
            IF NOT EXISTS (
                SELECT 1 FROM users u
                WHERE u.id = p_user_id
                  AND lower(u.email) = lower(v_email)
                  AND u.email_verified_at IS NOT NULL
            ) THEN
                RETURN NULL;
            END IF;
            -- The membership lands in the invited tenant, so bind it before
            -- writing: tenant_isolation guards this insert as it guards any other.
            PERFORM set_config('app.current_org_id', v_org::text, true);
            INSERT INTO memberships (organization_id, user_id, role)
            VALUES (v_org, p_user_id, v_role)
            ON CONFLICT (organization_id, user_id) DO NOTHING;
            UPDATE organization_invitations
            SET accepted_at = now(), accepted_by_user_id = p_user_id
            WHERE token_hash = p_token_hash;
            RETURN v_org;
        END
        $fn$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS organizations_invitation_read ON organizations")
    op.execute("DROP POLICY IF EXISTS invitations_token_accept ON organization_invitations")
    op.execute("DROP POLICY IF EXISTS invitations_token_read ON organization_invitations")
