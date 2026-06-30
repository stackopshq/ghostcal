"""team zero-knowledge key sharing

Lets an admin hand the organization private key to a new member through the invitation link
fragment (see docs/adr/0003). Adds ``organization_invitations.wrapped_org_key`` (org_sk sealed
under a random grant key carried in the link fragment), makes the per-member recovery copy optional
(granted access is re-grantable, not recoverable), exposes the wrapped key in the invitation
preview, and adds a membership-checked helper to store a member's wrapped org key.

Revision ID: c3f2e1d09a7b
Revises: b7e1a2c3d4e5
Create Date: 2026-06-30 22:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f2e1d09a7b"
down_revision: str | Sequence[str] | None = "b7e1a2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_invitations", sa.Column("wrapped_org_key", sa.Text(), nullable=True)
    )
    # Granted members keep only a password-wrapped key (re-grantable); recovery copies are optional.
    op.alter_column("org_member_keys", "recovery_wrapped_private_key", nullable=True)
    op.alter_column("org_member_keys", "recovery_salt", nullable=True)

    # Preview now also returns the wrapped org key so the accept page can recover org_sk with the
    # fragment grant key. Drop + create because the OUT columns change.
    op.execute("DROP FUNCTION IF EXISTS organization_invitation_preview(text)")
    op.execute(
        """
        CREATE FUNCTION organization_invitation_preview(p_token_hash text)
        RETURNS TABLE(
            organization_id uuid, organization_name text, email text, role text,
            wrapped_org_key text
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT i.organization_id, o.name, i.email, i.role, i.wrapped_org_key
            FROM organization_invitations i
            JOIN organizations o ON o.id = i.organization_id
            WHERE i.token_hash = p_token_hash
              AND i.accepted_at IS NULL
              AND i.expires_at > now()
        $$;
        """
    )

    # Store a member's org key, wrapped under their own password. SECURITY DEFINER (it writes
    # across RLS during the accept flow), but it verifies the user actually belongs to the org.
    op.execute(
        """
        CREATE FUNCTION store_member_org_key(
            p_org_id uuid, p_user_id uuid, p_wrapped_private_key text, p_wrap_salt text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM memberships WHERE organization_id = p_org_id AND user_id = p_user_id
            ) THEN
                RAISE EXCEPTION 'user % is not a member of organization %', p_user_id, p_org_id;
            END IF;
            INSERT INTO org_member_keys (
                organization_id, user_id, wrapped_private_key, wrap_salt,
                recovery_wrapped_private_key, recovery_salt
            ) VALUES (p_org_id, p_user_id, p_wrapped_private_key, p_wrap_salt, NULL, NULL)
            ON CONFLICT (organization_id, user_id) DO UPDATE SET
                wrapped_private_key = EXCLUDED.wrapped_private_key,
                wrap_salt = EXCLUDED.wrap_salt,
                updated_at = now();
        END;
        $$;
        """
    )

    # A member can now belong to several orgs, each with its own key — return them all (drop the
    # single-row LIMIT) so the browser can unwrap every org key at login.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_zk_keys(p_user_id uuid)
        RETURNS TABLE(
            organization_id uuid, public_key text, wrapped_private_key text, wrap_salt text,
            recovery_wrapped_private_key text, recovery_salt text
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT o.id, o.zk_public_key, k.wrapped_private_key, k.wrap_salt,
                   k.recovery_wrapped_private_key, k.recovery_salt
            FROM org_member_keys k
            JOIN organizations o ON o.id = k.organization_id
            WHERE k.user_id = p_user_id
            ORDER BY k.created_at;
        $$;
        """
    )

    # Re-wrap is now per-organization (a member holds a distinct key per org); the old signature
    # would overwrite every org key with the same blob.
    op.execute("DROP FUNCTION IF EXISTS rewrap_zk_key(uuid, text, text)")
    op.execute(
        """
        CREATE FUNCTION rewrap_zk_key(
            p_user_id uuid, p_org_id uuid, p_wrapped_private_key text, p_wrap_salt text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            UPDATE org_member_keys
                SET wrapped_private_key = p_wrapped_private_key,
                    wrap_salt = p_wrap_salt,
                    updated_at = now()
                WHERE user_id = p_user_id AND organization_id = p_org_id;
        END;
        $$;
        """
    )

    for sig, fn in (
        ("text", "organization_invitation_preview"),
        ("uuid, uuid, text, text", "store_member_org_key"),
        ("uuid, uuid, text, text", "rewrap_zk_key"),
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}({sig}) FROM PUBLIC")
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
                    GRANT EXECUTE ON FUNCTION {fn}({sig}) TO ghostcal_app;
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS rewrap_zk_key(uuid, uuid, text, text)")
    op.execute(
        """
        CREATE FUNCTION rewrap_zk_key(
            p_user_id uuid, p_wrapped_private_key text, p_wrap_salt text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            UPDATE org_member_keys
                SET wrapped_private_key = p_wrapped_private_key, wrap_salt = p_wrap_salt,
                    updated_at = now()
                WHERE user_id = p_user_id;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_zk_keys(p_user_id uuid)
        RETURNS TABLE(
            organization_id uuid, public_key text, wrapped_private_key text, wrap_salt text,
            recovery_wrapped_private_key text, recovery_salt text
        )
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT o.id, o.zk_public_key, k.wrapped_private_key, k.wrap_salt,
                   k.recovery_wrapped_private_key, k.recovery_salt
            FROM org_member_keys k JOIN organizations o ON o.id = k.organization_id
            WHERE k.user_id = p_user_id ORDER BY k.created_at LIMIT 1;
        $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS store_member_org_key(uuid, uuid, text, text)")
    op.execute("DROP FUNCTION IF EXISTS organization_invitation_preview(text)")
    op.execute(
        """
        CREATE FUNCTION organization_invitation_preview(p_token_hash text)
        RETURNS TABLE(organization_id uuid, organization_name text, email text, role text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT i.organization_id, o.name, i.email, i.role
            FROM organization_invitations i
            JOIN organizations o ON o.id = i.organization_id
            WHERE i.token_hash = p_token_hash
              AND i.accepted_at IS NULL
              AND i.expires_at > now()
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION organization_invitation_preview(text) FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT EXECUTE ON FUNCTION organization_invitation_preview(text) TO ghostcal_app; "
        "END IF; END $$;"
    )
    op.alter_column("org_member_keys", "recovery_salt", nullable=False)
    op.alter_column("org_member_keys", "recovery_wrapped_private_key", nullable=False)
    op.drop_column("organization_invitations", "wrapped_org_key")
