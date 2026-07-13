"""Tombstone user for account deletion.

Account deletion anonymizes a departing member out of a shared organization's records rather than
destroying them: bookings and event types are reassigned to a single, global tombstone user. See
ADR-0006.

The tombstone can never authenticate: it has no ``user_credentials`` row, no ``identities`` row and
no ``memberships`` row, and its address uses the RFC 2606 reserved ``.invalid`` TLD, so it can never
receive mail either.

Revision ID: a1c7e94b52f0
Revises: 47a95e221504
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a1c7e94b52f0"
down_revision: str | None = "47a95e221504"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOMBSTONE_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO users (id, email, name, timezone, email_verified_at)
        VALUES ('{TOMBSTONE_USER_ID}', 'deleted-user@ghostcal.invalid', 'Deleted user', 'UTC', NULL)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Deliberately not forced: bookings/event_types reference users with ON DELETE RESTRICT, so this
    # fails if any account has already been deleted. That is the correct outcome — a downgrade must
    # not silently orphan anonymized records, and deleted accounts cannot be brought back.
    op.execute(f"DELETE FROM users WHERE id = '{TOMBSTONE_USER_ID}'")
