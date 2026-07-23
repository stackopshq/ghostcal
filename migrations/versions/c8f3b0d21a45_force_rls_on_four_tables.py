"""FORCE row level security on the four tables that only ENABLEd it

Twenty-six tenant tables do `ENABLE` then `FORCE ROW LEVEL SECURITY`. Four do only the first:
`tasks`, `event_attendees`, `calendar_subscriptions` and `subscription_events`, added across three
separate feature migrations. A copy-paste omission, not a decision — nothing anywhere argues for
treating these four differently, and two of them are among the most sensitive in the schema
(`tasks` holds sealed content, `event_attendees` holds guest email addresses).

Without `FORCE`, the table **owner** bypasses RLS. The application connects as `ghostcal_app`,
which is not the owner, so tenant isolation holds today for every request — verified. The gap is
that the admin role does not, and the schema currently disagrees with itself about whether that
matters. Any future code path that reaches for the admin connection would silently lose isolation
on exactly these four tables and on no others, which is the kind of inconsistency that is only ever
discovered afterwards.

Defence in depth, then, not a live hole. Applied because the four are indistinguishable from their
twenty-six neighbours in every respect except this one.

Revision ID: c8f3b0d21a45
Revises: f2a4cec11a6c
Create Date: 2026-07-20 18:05:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c8f3b0d21a45"
down_revision: str | Sequence[str] | None = "f2a4cec11a6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("tasks", "event_attendees", "calendar_subscriptions", "subscription_events")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
