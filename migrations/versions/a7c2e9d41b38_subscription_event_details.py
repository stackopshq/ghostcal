"""subscription_events location and description

Subscribed ICS feeds (a university timetable, a club's fixtures) carry the room and the teacher in
LOCATION and DESCRIPTION. Only the SUMMARY was kept, so a subscriber saw a course code and nothing
else (reported 2026-10-18). Both columns are encrypted at rest like the summary; they are refilled
by the next sync of each feed, which replaces its events wholesale.

Revision ID: a7c2e9d41b38
Revises: e3b7a91c5d20
Create Date: 2026-10-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c2e9d41b38"
down_revision: str | Sequence[str] | None = "e3b7a91c5d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("subscription_events", sa.Column("location", sa.Text(), nullable=True))
    op.add_column("subscription_events", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscription_events", "description")
    op.drop_column("subscription_events", "location")
