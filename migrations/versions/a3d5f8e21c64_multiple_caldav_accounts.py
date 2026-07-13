"""multiple CalDAV accounts per user

``caldav_connections`` was UNIQUE on (organization_id, user_id): one external calendar per person.
That is fine for a scheduling tool, whose only use for CalDAV is "when am I busy". It is wrong for a
calendar client, where work + personal + a shared family calendar is the ordinary case.

Dropping the constraint makes two things ambiguous, and both are settled here rather than left to
whichever code path runs first:

- **Which account do bookings mirror onto?** Writing a booking to *every* connected calendar would
  duplicate it. ``mirror_bookings`` marks the one, and a partial unique index makes "the one" true in
  the database and not merely by convention. Existing connections inherit it — they were the only
  calendar, so they were already the mirror target.
- **Which account is an external event from?** Each connection gets a ``color``, so it is its own
  toggleable overlay in the calendar rather than all of them collapsing into one "External" chip.

Revision ID: a3d5f8e21c64
Revises: f1b6d92e4a07
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3d5f8e21c64"
down_revision: str | Sequence[str] | None = "f1b6d92e4a07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The overlay colours a new account cycles through, so two accounts never land on the same one by
# default. Matches the calendar palette already used for personal calendars.
_DEFAULT_COLOR = "#7aa2f7"


def upgrade() -> None:
    op.drop_constraint(
        "uq_caldav_connections_organization_id", "caldav_connections", type_="unique"
    )

    op.add_column(
        "caldav_connections",
        sa.Column("color", sa.String(20), nullable=False, server_default=_DEFAULT_COLOR),
    )
    op.add_column(
        "caldav_connections",
        sa.Column("mirror_bookings", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Every existing connection was the user's only one, so it was already where bookings mirrored.
    op.execute("UPDATE caldav_connections SET mirror_bookings = true")

    # At most one mirror target per person per org — enforced, not merely intended. A second one
    # would silently double-book the host's external calendar for every meeting.
    op.create_index(
        "uq_caldav_one_mirror_per_user",
        "caldav_connections",
        ["organization_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("mirror_bookings"),
    )


def downgrade() -> None:
    # The old schema holds one connection per user, so the extras have to go before the constraint
    # comes back — otherwise it simply fails on any live database that used the feature. Keep the
    # mirror target: it is the one bookings were actually written to. This runs FIRST, while
    # mirror_bookings still exists to be read.
    op.execute(
        """
        DELETE FROM caldav_connections c
        USING (
            SELECT organization_id, user_id,
                   (array_agg(id ORDER BY mirror_bookings DESC, created_at, id))[1] AS keep_id
            FROM caldav_connections
            GROUP BY organization_id, user_id
        ) k
        WHERE c.organization_id = k.organization_id
          AND c.user_id = k.user_id
          AND c.id <> k.keep_id
        """
    )

    op.drop_index("uq_caldav_one_mirror_per_user", table_name="caldav_connections")
    op.drop_column("caldav_connections", "mirror_bookings")
    op.drop_column("caldav_connections", "color")
    op.create_unique_constraint(
        "uq_caldav_connections_organization_id",
        "caldav_connections",
        ["organization_id", "user_id"],
    )
