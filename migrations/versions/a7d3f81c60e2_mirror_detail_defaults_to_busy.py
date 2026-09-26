"""a mirrored booking says "busy" unless the host asks for more

What GhostCal writes onto the host's external calendar today, measured on 2026-08-31 at
`routes.py:105` and `manage_routes.py:76`:

    summary     = the event type's title            e.g. "Intro call"
    description = "Booked via GhostCal · " + the invitee's email address
    location    = a label

So **the invitee's email address leaves the product** and lands, in the clear, in the host's iCloud,
Fastmail or Nextcloud calendar. No setting offered it, no screen said it, and the invitee — whose
address it is — was never party to the decision. Everything else about that invitee is sealed; this
one field walked out through a convenience.

The column carries `'busy'` or `'detailed'`, and the two defaults are deliberately different:

- **existing connections become `'detailed'`**, because they already behave that way and a
  migration must not silently change what a running deployment sends to a third party. Someone
  relying on the invitee address being there would lose it without being told;
- **new connections default to `'busy'`**, because the first mirror of a connection nobody has
  configured should be the one that discloses least.

`ADD COLUMN ... DEFAULT 'detailed'` then `ALTER COLUMN ... SET DEFAULT 'busy'` is what expresses
that: the first fills the rows that exist, the second governs the rows that do not yet.

The redaction itself lives in `mirror_booking`, not at its call sites. There are two callers today
and a third would forget — and forgetting here means an address at a third party, which is not the
kind of mistake a code review reliably catches.

Revision ID: a7d3f81c60e2
Revises: e4b7c2a91f38
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7d3f81c60e2"
down_revision = "e4b7c2a91f38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "caldav_connections",
        sa.Column(
            "mirror_detail",
            sa.String(length=20),
            nullable=False,
            server_default="detailed",
        ),
    )
    # From here on, a connection nobody has configured mirrors the least it can.
    op.alter_column("caldav_connections", "mirror_detail", server_default="busy")
    op.create_check_constraint(
        "caldav_mirror_detail_known",
        "caldav_connections",
        "mirror_detail IN ('busy', 'detailed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_caldav_connections_caldav_mirror_detail_known", "caldav_connections")
    op.drop_column("caldav_connections", "mirror_detail")
