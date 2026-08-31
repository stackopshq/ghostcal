"""password reset tokens

The recovery phrase shown at sign-up had nothing to spend itself on. Its envelope was stored
(`org_member_keys.recovery_wrapped_private_key`) and `unlockWithRecovery` was written, but nothing
ever called it: there was no way to start a reset, no route to finish one, and the only password
route demanded the current password. Someone who forgot theirs was out for good.

Same shape as `email_verification_tokens`, and for the same reasons: only the hash is stored, so a
database read hands over nothing usable; single use, enforced by `used_at IS NULL` inside the
UPDATE rather than by a read-then-write; and an expiry, so a link left in a mailbox stops working.

Revision ID: d5c1a83f04e6
Revises: c4e8a1f70b62
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d5c1a83f04e6"
down_revision = "c4e8a1f70b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    # The app role reads and writes this table like the other auth tables; `users` is global and
    # carries no RLS, so neither does this.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO ghostcal_app")


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
