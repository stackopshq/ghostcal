"""zero-knowledge invitee data

Adds the organization X25519 public key, per-member wrapped private keys, and the booking
ciphertext blob, plus SECURITY DEFINER helpers to store/read/rewrap the wrapped keys (the
``org_member_keys`` writes happen across RLS boundaries during sign-up). Drops the cleartext
``bookings.answers`` column: invitee answers are now sealed client-side and the server can never
read them. See docs/adr/0002-zero-knowledge-invitee-data.md.

Revision ID: b7e1a2c3d4e5
Revises: 90633e84dfa8
Create Date: 2026-06-30 21:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7e1a2c3d4e5"
down_revision: str | Sequence[str] | None = "90633e84dfa8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FN_SIG = "text, text, text, text, text"


def upgrade() -> None:
    op.add_column("organizations", sa.Column("zk_public_key", sa.Text(), nullable=True))

    op.create_table(
        "org_member_keys",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("wrapped_private_key", sa.Text(), nullable=False),
        sa.Column("wrap_salt", sa.Text(), nullable=False),
        sa.Column("recovery_wrapped_private_key", sa.Text(), nullable=False),
        sa.Column("recovery_salt", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_org_member_keys_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_org_member_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", "user_id", name=op.f("pk_org_member_keys")),
    )
    # Defence-in-depth tenant isolation (the helpers below are the real access path).
    op.execute("ALTER TABLE org_member_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_member_keys FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON org_member_keys USING "
        "(organization_id = current_setting('app.current_org_id', true)::uuid) "
        "WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)"
    )

    # Replace the cleartext answers JSONB with the opaque sealed-box blob.
    op.add_column("bookings", sa.Column("invitee_private", sa.Text(), nullable=True))
    op.drop_column("bookings", "answers")

    # The invitee name is now zero-knowledge (it lives in the sealed blob), so the column is no
    # longer required and the server stores NULL for booking-page submissions.
    op.alter_column("bookings", "invitee_name", existing_type=sa.String(200), nullable=True)

    # Encrypt the remaining invitee PII at rest. Ciphertext is longer than the plaintext, so widen
    # to TEXT; the table is empty pre-launch, so the cast is a no-op. The server keeps the key (it
    # must send reminder emails), but a stolen dump reveals nothing.
    op.alter_column("bookings", "invitee_email", existing_type=sa.String(320), type_=sa.Text())
    op.alter_column("bookings", "location", existing_type=sa.String(500), type_=sa.Text())
    op.alter_column("bookings", "meeting_url", existing_type=sa.String(2048), type_=sa.Text())
    op.alter_column(
        "bookings",
        "guest_emails",
        existing_type=postgresql.JSONB(),
        type_=sa.Text(),
        postgresql_using="guest_emails::text",
        server_default=None,
    )

    # Store the wrapped keys at sign-up. Resolving the owner org + writing org_member_keys crosses
    # RLS (the GUC is unset during the auth session), so this runs SECURITY DEFINER like
    # provision_account. The server only ever sees ciphertext and salts here.
    op.execute(
        """
        CREATE FUNCTION store_zk_keys(
            p_user_id uuid, p_public_key text, p_wrapped_private_key text, p_wrap_salt text,
            p_recovery_wrapped_private_key text, p_recovery_salt text
        ) RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_org_id uuid;
        BEGIN
            SELECT organization_id INTO v_org_id FROM memberships
                WHERE user_id = p_user_id AND role = 'owner'
                ORDER BY created_at LIMIT 1;
            IF v_org_id IS NULL THEN
                RAISE EXCEPTION 'no owner organization for user %', p_user_id;
            END IF;
            UPDATE organizations SET zk_public_key = p_public_key WHERE id = v_org_id;
            INSERT INTO org_member_keys (
                organization_id, user_id, wrapped_private_key, wrap_salt,
                recovery_wrapped_private_key, recovery_salt
            ) VALUES (
                v_org_id, p_user_id, p_wrapped_private_key, p_wrap_salt,
                p_recovery_wrapped_private_key, p_recovery_salt
            )
            ON CONFLICT (organization_id, user_id) DO UPDATE SET
                wrapped_private_key = EXCLUDED.wrapped_private_key,
                wrap_salt = EXCLUDED.wrap_salt,
                recovery_wrapped_private_key = EXCLUDED.recovery_wrapped_private_key,
                recovery_salt = EXCLUDED.recovery_salt,
                updated_at = now();
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION get_zk_keys(p_user_id uuid)
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
            ORDER BY k.created_at
            LIMIT 1;
        $$;
        """
    )
    # Re-wrap after a password change/reset: the client unwraps the private key (from session or
    # the recovery phrase), re-wraps it under the new password, and posts the new blob + salt.
    op.execute(
        """
        CREATE FUNCTION rewrap_zk_key(
            p_user_id uuid, p_wrapped_private_key text, p_wrap_salt text
        ) RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            UPDATE org_member_keys
                SET wrapped_private_key = p_wrapped_private_key,
                    wrap_salt = p_wrap_salt,
                    updated_at = now()
                WHERE user_id = p_user_id;
        END;
        $$;
        """
    )

    for sig, fn in (
        (f"uuid, {_FN_SIG}", "store_zk_keys"),
        ("uuid", "get_zk_keys"),
        ("uuid, text, text", "rewrap_zk_key"),
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
    op.execute(f"DROP FUNCTION IF EXISTS store_zk_keys(uuid, {_FN_SIG})")
    op.execute("DROP FUNCTION IF EXISTS get_zk_keys(uuid)")
    op.execute("DROP FUNCTION IF EXISTS rewrap_zk_key(uuid, text, text)")
    op.alter_column(
        "bookings",
        "guest_emails",
        existing_type=sa.Text(),
        type_=postgresql.JSONB(),
        postgresql_using="guest_emails::jsonb",
        server_default=sa.text("'[]'::jsonb"),
    )
    op.alter_column("bookings", "meeting_url", existing_type=sa.Text(), type_=sa.String(2048))
    op.alter_column("bookings", "location", existing_type=sa.Text(), type_=sa.String(500))
    op.alter_column("bookings", "invitee_email", existing_type=sa.Text(), type_=sa.String(320))
    op.alter_column("bookings", "invitee_name", existing_type=sa.String(200), nullable=False)
    op.add_column(
        "bookings",
        sa.Column(
            "answers",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_column("bookings", "invitee_private")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON org_member_keys")
    op.drop_table("org_member_keys")
    op.drop_column("organizations", "zk_public_key")
