"""external_busy summary (read external CalDAV event titles into the agenda)

Add an encrypted-at-rest title to projected external busy blocks so the calendar agenda can show
the external event's name instead of a bare "Busy". Read-only sync; titles come from the user's
own calendar and are encrypted at rest. See ADR-0004 (Phase 2).

Revision ID: f6c3d4e5a7b8
Revises: e5b2c3d4f6a7
Create Date: 2026-06-30 23:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6c3d4e5a7b8"
down_revision: str | Sequence[str] | None = "e5b2c3d4f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("external_busy", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("external_busy", "summary")
