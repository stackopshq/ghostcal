"""Booking reminders carry the meeting link.

``due_booking_reminders`` gains ``meeting_url`` (encrypted at rest with the application key, like
``invitee_email``; the gateway decrypts both). A RETURNS TABLE change needs DROP + CREATE, so the
grant is re-applied. Downgrade restores the previous definition.

Revision ID: e3b7a91c5d20
Revises: d2e5b71c48a9
"""

from __future__ import annotations

from alembic import op

revision = "e3b7a91c5d20"
down_revision = "d2e5b71c48a9"
branch_labels = None
depends_on = None

_FN = "due_booking_reminders(int[])"

_BODY = """
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT b.id, b.organization_id, ofs.minutes_before,
                   b.invitee_name, b.invitee_email, b.invitee_timezone,
                   et.title, u.name, u.email, u.timezone,
                   et.location_type, b.start_at, b.end_at{extra_select}
            FROM bookings b
            JOIN event_types et ON et.id = b.event_type_id
            JOIN users u ON u.id = b.host_id
            CROSS JOIN unnest(p_offsets) AS ofs(minutes_before)
            WHERE b.status = 'confirmed'
              AND b.start_at > now()
              AND b.start_at - make_interval(mins => ofs.minutes_before) <= now()
              AND b.start_at - make_interval(mins => ofs.minutes_before) >= b.created_at
              AND NOT EXISTS (
                  SELECT 1 FROM booking_reminders r
                  WHERE r.booking_id = b.id AND r.minutes_before = ofs.minutes_before
              )
        $$;
"""

_COLUMNS = """
            booking_id uuid, organization_id uuid, minutes_before int,
            invitee_name text, invitee_email text, invitee_timezone text,
            event_title text, host_name text, host_email text, host_timezone text,
            location_type text, start_at timestamptz, end_at timestamptz"""


def _create(*, with_meeting_url: bool) -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}")
    columns = _COLUMNS + (", meeting_url text" if with_meeting_url else "")
    body = _BODY.format(extra_select=", b.meeting_url" if with_meeting_url else "")
    op.execute(
        f"CREATE FUNCTION due_booking_reminders(p_offsets int[]) RETURNS TABLE({columns}){body}"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FN} FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        f"THEN GRANT EXECUTE ON FUNCTION {_FN} TO ghostcal_app; END IF; END $$;"
    )


def upgrade() -> None:
    _create(with_meeting_url=True)


def downgrade() -> None:
    _create(with_meeting_url=False)
