"""subscription events: a UID is not an identity on its own

RFC 5545 §3.8.4.4: a moved or modified occurrence of a recurring series is
described by a *second* VEVENT carrying THE SAME UID plus a RECURRENCE-ID
naming the occurrence it replaces. That is ordinary calendar data, not a
malformed feed — any real calendar eventually contains one.

The `(subscription_id, uid)` unique constraint therefore rejected perfectly
valid calendars. Measured 2026-08-14 on a 400-event iCloud feed in which
exactly ONE event was a moved occurrence: the whole subscription failed with
`UniqueViolationError`, and the user was told to check their URL.

`recurrence_id` is NOT NULL, defaulting to '' outside a recurrence, never
NULL: PostgreSQL does not treat two NULLs as equal, so a nullable column
would have let the real duplicates through — the ones this constraint exists
to forbid.

Revision ID: b7e14a92c3d5
Revises: a9c2e4f61b83
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7e14a92c3d5"
down_revision = "a9c2e4f61b83"
branch_labels = None
depends_on = None

_TABLE = "subscription_events"
_OLD = "uq_subscription_events_subscription_id"
_NEW = "uq_subscription_events_subscription_id_uid_recurrence"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("recurrence_id", sa.String(length=128), nullable=False, server_default=""),
    )
    op.drop_constraint(_OLD, _TABLE, type_="unique")
    op.create_unique_constraint(_NEW, _TABLE, ["subscription_id", "uid", "recurrence_id"])


def downgrade() -> None:
    # Reverting narrows the key, so rows that are legitimately distinct today
    # would collide. Drop the moved occurrences first — they are a cache of a
    # remote feed and come back on the next refresh, so nothing is lost that
    # the source cannot replace. Doing it in the other order would fail on
    # exactly the calendars this migration was written for.
    op.execute(sa.text(f"DELETE FROM {_TABLE} WHERE recurrence_id <> ''"))
    op.drop_constraint(_NEW, _TABLE, type_="unique")
    op.create_unique_constraint(_OLD, _TABLE, ["subscription_id", "uid"])
    op.drop_column(_TABLE, "recurrence_id")
