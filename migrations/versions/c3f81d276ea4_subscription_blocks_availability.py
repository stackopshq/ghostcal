"""subscribed calendars can block availability, one calendar at a time

`busy_for()` named three sources of "busy" — confirmed bookings, CalDAV-synced
time, and the host's own events — and subscribed calendars were not among
them. An all-day event coming from a subscribed iCloud calendar therefore left
the whole day bookable, which is not what anyone expects from a calendar they
can see in their own agenda.

The flag defaults to **false**, deliberately. Seeing an event and being busy
are different things: the very examples the subscribe dialog offers — public
holidays, fixtures — are informational, and blocking by default would close
eleven days of the year with nothing to say why. A personal calendar becomes
blocking with one click.

Revision ID: c3f81d276ea4
Revises: b7e14a92c3d5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3f81d276ea4"
down_revision = "b7e14a92c3d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_subscriptions",
        sa.Column(
            "blocks_availability",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    # Reverting loses which calendars were set to block. Nothing else breaks —
    # availability simply returns to ignoring subscriptions, which is what it
    # did before this column existed.
    op.drop_column("calendar_subscriptions", "blocks_availability")
