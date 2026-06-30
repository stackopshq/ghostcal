"""bind invitation acceptance to the invited email

Hardening (pentest): a leaked invitation link should not let an *arbitrary* authenticated account
join the org with the invited (possibly admin/owner) role. accept_organization_invitation now only
succeeds when the accepting user's verified email matches the invitation's email.

Revision ID: b9c0d1e2f3a4
Revises: a7b8c9d0e1f2
Create Date: 2026-07-01 01:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WITH_EMAIL_CHECK = """
CREATE OR REPLACE FUNCTION accept_organization_invitation(p_token_hash text, p_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    v_org uuid;
    v_role text;
    v_email text;
BEGIN
    SELECT organization_id, role, email INTO v_org, v_role, v_email
    FROM organization_invitations
    WHERE token_hash = p_token_hash AND accepted_at IS NULL AND expires_at > now()
    FOR UPDATE;
    IF v_org IS NULL THEN
        RETURN NULL;
    END IF;
    -- Only the verified owner of the invited address may accept (defence against link leakage).
    IF NOT EXISTS (
        SELECT 1 FROM users u
        WHERE u.id = p_user_id
          AND lower(u.email) = lower(v_email)
          AND u.email_verified_at IS NOT NULL
    ) THEN
        RETURN NULL;
    END IF;
    INSERT INTO memberships (organization_id, user_id, role)
    VALUES (v_org, p_user_id, v_role)
    ON CONFLICT (organization_id, user_id) DO NOTHING;
    UPDATE organization_invitations
    SET accepted_at = now(), accepted_by_user_id = p_user_id
    WHERE token_hash = p_token_hash;
    RETURN v_org;
END
$$;
"""

_WITHOUT_EMAIL_CHECK = """
CREATE OR REPLACE FUNCTION accept_organization_invitation(p_token_hash text, p_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    v_org uuid;
    v_role text;
BEGIN
    SELECT organization_id, role INTO v_org, v_role
    FROM organization_invitations
    WHERE token_hash = p_token_hash AND accepted_at IS NULL AND expires_at > now()
    FOR UPDATE;
    IF v_org IS NULL THEN
        RETURN NULL;
    END IF;
    INSERT INTO memberships (organization_id, user_id, role)
    VALUES (v_org, p_user_id, v_role)
    ON CONFLICT (organization_id, user_id) DO NOTHING;
    UPDATE organization_invitations
    SET accepted_at = now(), accepted_by_user_id = p_user_id
    WHERE token_hash = p_token_hash;
    RETURN v_org;
END
$$;
"""


def upgrade() -> None:
    op.execute(_WITH_EMAIL_CHECK)


def downgrade() -> None:
    op.execute(_WITHOUT_EMAIL_CHECK)
