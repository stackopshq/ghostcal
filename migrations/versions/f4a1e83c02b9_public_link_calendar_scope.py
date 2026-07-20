"""a public calendar link may only publish its own calendar's events

`public_calendar_by_token` reached the events through the join table and never checked they
belonged to the link's calendar:

    LEFT JOIN calendar_link_events le ON le.link_id = l.id
    LEFT JOIN calendar_events e ON e.id = le.event_id

ADR-0009's premise is "a link is one calendar" — that is the whole reason it is not "just hand them
the org key". The invariant was enforced only by `pending_seals`, which offers the right events;
nothing stopped a caller sealing a different `event_id` into the table, and this function then
published whatever it found: `start_at`, `end_at`, `timezone`, `rrule`, `exdates`.

Concretely, an org member with read access to a colleague's shared calendar (ADR-0005) could mint a
link on their *own* calendar, seal a colleague's event id into it, and publish that event's times
and recurrence to an anonymous URL. Content stays sealed — the copy is the attacker's own junk
ciphertext — so this is metadata, but a weekly `FREQ=WEEKLY;BYDAY=TU` on a private appointment is
not nothing, and the colleague has no way to see it happened.

The predicate is added here so the DEFINER door re-derives the event set instead of trusting a
table the application writes. The write path is constrained too (`store_copies`), because a link
whose contents are wrong is worth catching before it is served — but the two fixes are independent
on purpose: this one holds even if a future writer forgets.

Revision ID: f4a1e83c02b9
Revises: f2a4cec11a6c
Create Date: 2026-07-20 17:20:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f4a1e83c02b9"
down_revision: str | Sequence[str] | None = "f2a4cec11a6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPED = "LEFT JOIN calendar_events e ON e.id = le.event_id AND e.calendar_id = l.calendar_id"
_UNSCOPED = "LEFT JOIN calendar_events e ON e.id = le.event_id"


def _replace(event_join: str) -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public_calendar_by_token(p_token_hash text)
        RETURNS TABLE(
            link_id uuid, calendar_name text, owner_name text,
            event_id uuid, start_at timestamptz, end_at timestamptz, all_day boolean,
            timezone text, rrule text, exdates jsonb, content_sealed text
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT l.id, c.name, u.name,
                   e.id, e.start_at, e.end_at, e.all_day, e.timezone, e.rrule, e.exdates,
                   le.content_sealed
            FROM calendar_links l
            JOIN calendars c ON c.id = l.calendar_id
            JOIN users u ON u.id = c.owner_id
            LEFT JOIN calendar_link_events le ON le.link_id = l.id
            {event_join}
            WHERE l.token_hash = p_token_hash
        $$;
        """
    )


def upgrade() -> None:
    _replace(_SCOPED)


def downgrade() -> None:
    _replace(_UNSCOPED)
