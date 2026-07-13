"""per-user keypairs

Foundation for org key rotation (ADR-0007). Each user gains an X25519 keypair: the public key in the
clear — the server may read it, that is what public keys are for — and the private key wrapped under
a key derived from their password (Argon2id), never reaching the server unwrapped.

With these, an admin rotating the org keypair can seal the new org private key **directly** to each
remaining member's public key: the members do nothing. Without them, rotation means one out-of-band
re-grant link per member, which is laborious enough that no one would ever rotate — and a revocation
nobody executes is not a revocation.

All three columns are nullable: existing accounts have no keypair until their next login, which is
the only moment their password is in the browser.

Revision ID: d7f31c0a94b2
Revises: c9e4a71b6d38
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f31c0a94b2"
down_revision: str | Sequence[str] | None = "c9e4a71b6d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("zk_public_key", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("zk_wrapped_private_key", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("zk_wrap_salt", sa.Text(), nullable=True))
    # A keypair is all-or-nothing: a public key with no wrapped private key is an account that can
    # be sealed to and can never open what it receives.
    op.create_check_constraint(
        "zk_keypair_complete",
        "users",
        "(zk_public_key IS NULL AND zk_wrapped_private_key IS NULL AND zk_wrap_salt IS NULL) "
        "OR (zk_public_key IS NOT NULL AND zk_wrapped_private_key IS NOT NULL "
        "AND zk_wrap_salt IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_zk_keypair_complete", "users")
    op.drop_column("users", "zk_wrap_salt")
    op.drop_column("users", "zk_wrapped_private_key")
    op.drop_column("users", "zk_public_key")
