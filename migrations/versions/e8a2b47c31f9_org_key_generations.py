"""org key generations and rotation

The second step of ADR-0007. An organization's keypair can now be rotated, which is what finally
makes removing a member *revoke* something.

Generations. ``org_member_keys`` gains a ``generation`` and becomes keyed by (org, user,
generation), so a member holds every org key the organization has ever had. That is not a hole: a
departed member already kept the old key, and keeping it for the *remaining* members is what lets
them still read records that have not been re-sealed yet. Generation 0 is the existing
password-wrapped key. From generation 1 on, the org private key is instead **sealed to the member's
own public key** (ADR-0007) — one mechanism instead of two, and no password needed to hand a member
a key.

Note what is *not* here: old public keys. Opening a sealed blob needs only the recipient's private
key, so a retired generation's public key has no further use. Nothing to store, nothing to prune.

``rotate_org_key`` does the flip in one statement-level transaction: insert the new generation's
per-member sealed keys, then point the organization at the new public key. It is SECURITY DEFINER
for the same reason ``get_zk_keys`` is — it must read ``memberships`` to check that every member has
been provided for, and refuse (rather than silently lock someone out) if any has not.

Revision ID: e8a2b47c31f9
Revises: d7f31c0a94b2
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8a2b47c31f9"
down_revision: str | Sequence[str] | None = "d7f31c0a94b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTIONS = (("rotate_org_key", "uuid, uuid, text, jsonb", "(uuid, uuid, text, jsonb)"),)


def upgrade() -> None:
    op.add_column("organizations", sa.Column("zk_key_generation", sa.SmallInteger(), nullable=True))
    op.execute("UPDATE organizations SET zk_key_generation = 0")
    op.alter_column("organizations", "zk_key_generation", nullable=False, server_default="0")

    op.add_column("org_member_keys", sa.Column("generation", sa.SmallInteger(), nullable=True))
    op.execute("UPDATE org_member_keys SET generation = 0")
    op.alter_column("org_member_keys", "generation", nullable=False, server_default="0")

    # From generation 1 on, the org private key is sealed to the member's user public key instead of
    # being wrapped under their password — so the password-wrapped columns stop being mandatory.
    op.add_column("org_member_keys", sa.Column("sealed_org_key", sa.Text(), nullable=True))
    op.alter_column("org_member_keys", "wrapped_private_key", nullable=True)
    op.alter_column("org_member_keys", "wrap_salt", nullable=True)

    # A row must carry exactly one way for the member to obtain that generation's key. Neither is
    # a row that grants nothing; both would be two doors into one key, and the weaker one decides.
    op.create_check_constraint(
        "one_way_in",
        "org_member_keys",
        "(sealed_org_key IS NOT NULL AND wrapped_private_key IS NULL AND wrap_salt IS NULL) "
        "OR (sealed_org_key IS NULL AND wrapped_private_key IS NOT NULL AND wrap_salt IS NOT NULL)",
    )

    op.drop_constraint("pk_org_member_keys", "org_member_keys", type_="primary")
    op.create_primary_key(
        "pk_org_member_keys", "org_member_keys", ["organization_id", "user_id", "generation"]
    )

    op.execute(
        """
        CREATE FUNCTION rotate_org_key(
            p_organization_id uuid,
            p_actor_id uuid,
            p_public_key text,
            p_member_keys jsonb
        )
        RETURNS smallint
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_role text;
            v_generation smallint;
            v_missing text;
        BEGIN
            SELECT role INTO v_role FROM memberships
            WHERE organization_id = p_organization_id AND user_id = p_actor_id;
            IF v_role IS NULL OR v_role NOT IN ('owner', 'admin') THEN
                RAISE EXCEPTION 'not authorized to rotate the organization key'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- Every current member must be provided for. Rotating past someone locks them out of
            -- their own organization's data, silently, and only they would ever find out.
            SELECT string_agg(u.email, ', ') INTO v_missing
            FROM memberships m
            JOIN users u ON u.id = m.user_id
            WHERE m.organization_id = p_organization_id
              AND NOT (p_member_keys ? m.user_id::text);
            IF v_missing IS NOT NULL THEN
                RAISE EXCEPTION 'no new key provided for: %', v_missing
                    USING ERRCODE = 'check_violation';
            END IF;

            -- ...and nobody else slipped in: a key for a non-member is a key for an outsider.
            SELECT string_agg(k.key, ', ') INTO v_missing
            FROM jsonb_each_text(p_member_keys) k
            WHERE NOT EXISTS (
                SELECT 1 FROM memberships m
                WHERE m.organization_id = p_organization_id AND m.user_id = k.key::uuid
            );
            IF v_missing IS NOT NULL THEN
                RAISE EXCEPTION 'not a member of this organization: %', v_missing
                    USING ERRCODE = 'check_violation';
            END IF;

            SELECT zk_key_generation + 1 INTO v_generation
            FROM organizations WHERE id = p_organization_id FOR UPDATE;

            INSERT INTO org_member_keys (organization_id, user_id, generation, sealed_org_key)
            SELECT p_organization_id, k.key::uuid, v_generation, k.value
            FROM jsonb_each_text(p_member_keys) k;

            UPDATE organizations
            SET zk_public_key = p_public_key, zk_key_generation = v_generation
            WHERE id = p_organization_id;

            RETURN v_generation;
        END
        $$;
        """
    )

    # Two existing functions write org_member_keys with ON CONFLICT (organization_id, user_id) — a
    # key that no longer exists now that generation is part of it. Both must also target the org's
    # CURRENT generation rather than assuming 0, or a member granted a key after a rotation would be
    # handed a row claiming to be the original key.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION store_zk_keys(
            p_user_id uuid, p_public_key text, p_wrapped_private_key text, p_wrap_salt text,
            p_recovery_wrapped_private_key text, p_recovery_salt text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_org_id uuid;
            v_generation smallint;
        BEGIN
            SELECT organization_id INTO v_org_id FROM memberships
                WHERE user_id = p_user_id AND role = 'owner'
                ORDER BY created_at LIMIT 1;
            IF v_org_id IS NULL THEN
                RAISE EXCEPTION 'no owner organization for user %', p_user_id;
            END IF;
            SELECT zk_key_generation INTO v_generation FROM organizations WHERE id = v_org_id;
            UPDATE organizations SET zk_public_key = p_public_key WHERE id = v_org_id;
            INSERT INTO org_member_keys (
                organization_id, user_id, generation, wrapped_private_key, wrap_salt,
                recovery_wrapped_private_key, recovery_salt
            ) VALUES (
                v_org_id, p_user_id, v_generation, p_wrapped_private_key, p_wrap_salt,
                p_recovery_wrapped_private_key, p_recovery_salt
            )
            ON CONFLICT (organization_id, user_id, generation) DO UPDATE SET
                wrapped_private_key = EXCLUDED.wrapped_private_key,
                wrap_salt = EXCLUDED.wrap_salt,
                recovery_wrapped_private_key = EXCLUDED.recovery_wrapped_private_key,
                recovery_salt = EXCLUDED.recovery_salt,
                sealed_org_key = NULL,
                updated_at = now();
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION store_member_org_key(
            p_org_id uuid, p_user_id uuid, p_wrapped_private_key text, p_wrap_salt text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_generation smallint;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM memberships WHERE organization_id = p_org_id AND user_id = p_user_id
            ) THEN
                RAISE EXCEPTION 'user % is not a member of organization %', p_user_id, p_org_id;
            END IF;
            -- An invitation grant carries the key the org is using *now*, so that is the generation
            -- the member is handed. Records still sealed under an older one stay unreadable to them
            -- until the backlog is re-sealed — see ADR-0007.
            SELECT zk_key_generation INTO v_generation FROM organizations WHERE id = p_org_id;
            INSERT INTO org_member_keys (
                organization_id, user_id, generation, wrapped_private_key, wrap_salt,
                recovery_wrapped_private_key, recovery_salt
            ) VALUES (p_org_id, p_user_id, v_generation, p_wrapped_private_key, p_wrap_salt,
                      NULL, NULL)
            ON CONFLICT (organization_id, user_id, generation) DO UPDATE SET
                wrapped_private_key = EXCLUDED.wrapped_private_key,
                wrap_salt = EXCLUDED.wrap_salt,
                sealed_org_key = NULL,
                updated_at = now();
        END;
        $$;
        """
    )

    # Hand every generation to the browser, newest first: a blob carries no key id, so it opens by
    # trying the current key and falling back through the older ones (AES-GCM fails loudly, so a
    # wrong key costs a failed decryption, never a wrong answer).
    op.execute("DROP FUNCTION IF EXISTS get_zk_keys(uuid)")
    op.execute(
        """
        CREATE FUNCTION get_zk_keys(p_user_id uuid)
        RETURNS TABLE(
            organization_id uuid, public_key text, wrapped_private_key text, wrap_salt text,
            recovery_wrapped_private_key text, recovery_salt text,
            generation smallint, sealed_org_key text
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT o.id, o.zk_public_key, k.wrapped_private_key, k.wrap_salt,
                   k.recovery_wrapped_private_key, k.recovery_salt,
                   k.generation, k.sealed_org_key
            FROM org_member_keys k
            JOIN organizations o ON o.id = k.organization_id
            WHERE k.user_id = p_user_id
            ORDER BY k.organization_id, k.generation DESC
        $$;
        """
    )

    for name, sig, _drop in (*_FUNCTIONS, ("get_zk_keys", "uuid", "(uuid)")):
        op.execute(f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
            f"THEN GRANT EXECUTE ON FUNCTION {name}({sig}) TO ghostcal_app; END IF; END $$;"
        )


def downgrade() -> None:
    for _name, _sig, drop in _FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS rotate_org_key{drop}")

    # Only generation 0 survives a downgrade — the older schema cannot represent the others. Any
    # organization that has actually rotated would lose its members' access to the current key, so
    # refuse rather than corrupt.
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM organizations WHERE zk_key_generation > 0) THEN
                RAISE EXCEPTION 'cannot downgrade: an organization has rotated its key, and the '
                                'previous schema cannot hold the generations that resulted';
            END IF;
        END $$;
        """
    )
    op.execute("DELETE FROM org_member_keys WHERE generation > 0")

    op.drop_constraint("pk_org_member_keys", "org_member_keys", type_="primary")
    op.create_primary_key("pk_org_member_keys", "org_member_keys", ["organization_id", "user_id"])
    op.drop_constraint("ck_org_member_keys_one_way_in", "org_member_keys")
    op.alter_column("org_member_keys", "wrap_salt", nullable=False)
    op.alter_column("org_member_keys", "wrapped_private_key", nullable=False)
    op.drop_column("org_member_keys", "sealed_org_key")
    op.drop_column("org_member_keys", "generation")
    op.drop_column("organizations", "zk_key_generation")

    op.execute("DROP FUNCTION IF EXISTS get_zk_keys(uuid)")
    op.execute(
        """
        CREATE FUNCTION get_zk_keys(p_user_id uuid)
        RETURNS TABLE(
            organization_id uuid, public_key text, wrapped_private_key text, wrap_salt text,
            recovery_wrapped_private_key text, recovery_salt text
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT o.id, o.zk_public_key, k.wrapped_private_key, k.wrap_salt,
                   k.recovery_wrapped_private_key, k.recovery_salt
            FROM org_member_keys k
            JOIN organizations o ON o.id = k.organization_id
            WHERE k.user_id = p_user_id
            ORDER BY k.created_at
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION get_zk_keys(uuid) FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT EXECUTE ON FUNCTION get_zk_keys(uuid) TO ghostcal_app; END IF; END $$;"
    )

    # Restore the two writers to their pre-generation form. Leaving them keyed on a column that no
    # longer exists would break every sign-up and every invitation grant — a downgrade that only
    # half-undoes is worse than none.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION store_zk_keys(
            p_user_id uuid, p_public_key text, p_wrapped_private_key text, p_wrap_salt text,
            p_recovery_wrapped_private_key text, p_recovery_salt text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
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
        CREATE OR REPLACE FUNCTION store_member_org_key(
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
