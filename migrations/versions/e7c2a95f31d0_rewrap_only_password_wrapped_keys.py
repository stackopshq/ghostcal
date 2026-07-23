"""rewrap_zk_key must only touch password-wrapped rows

Written before ADR-0007 and never revisited. Its UPDATE matches every row for (user, org):

    WHERE user_id = p_user_id AND organization_id = p_org_id

Before generations existed there was exactly one such row, so that was right. After a rotation a
member holds two or more: generation 0, wrapped under their password, and generation N, sealed to
their own keypair. The unfiltered UPDATE writes `wrapped_private_key`/`wrap_salt` onto *both* — and
the `one_way_in` check constraint (migration e8a2b47c31f9) requires each row to carry exactly one
route to the key, never both. So the statement aborts.

The effect is not theoretical and needs no attacker: **any member of an organization that has
rotated its key cannot change their password.** The route 500s, and because the password change
already committed in a separate request, their org key stays wrapped under the old one. Once the
browser forgets that password they can open nothing — recoverable only by the recovery phrase
(generation 0 only) or another full rotation. Silent loss of access, for exactly the organizations
that used the revocation feature.

Scoped to the password-wrapped rows. Sealed generations need no re-wrap at all: they are opened
with the member's own keypair, which a password change does not touch.

Revision ID: e7c2a95f31d0
Revises: b6d0f2a17c94
Create Date: 2026-07-20 16:55:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7c2a95f31d0"
down_revision: str | Sequence[str] | None = "b6d0f2a17c94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BODY_FIXED = """
            UPDATE org_member_keys
                SET wrapped_private_key = p_wrapped_private_key,
                    wrap_salt = p_wrap_salt,
                    updated_at = now()
                WHERE user_id = p_user_id
                  AND organization_id = p_org_id
                  AND sealed_org_key IS NULL;
"""

_BODY_ORIGINAL = """
            UPDATE org_member_keys
                SET wrapped_private_key = p_wrapped_private_key,
                    wrap_salt = p_wrap_salt,
                    updated_at = now()
                WHERE user_id = p_user_id AND organization_id = p_org_id;
"""


def _replace(body: str) -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION rewrap_zk_key(
            p_user_id uuid, p_org_id uuid, p_wrapped_private_key text, p_wrap_salt text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
        {body}
        END;
        $$;
        """
    )


def upgrade() -> None:
    _replace(_BODY_FIXED)


def downgrade() -> None:
    _replace(_BODY_ORIGINAL)
