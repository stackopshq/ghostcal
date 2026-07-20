"""a reminder claim must belong to the organization it names

`claim_booking_reminder` and `claim_calendar_event_reminder` insert a claim row using a
caller-supplied `p_organization_id` that is never checked against the target's actual owner. Both
foreign keys are satisfied by *any* real org, so the pair need not belong together.

That makes each one a cross-tenant denial-of-notification primitive: claim a victim's booking under
your own org id, the unique constraint on `(booking_id, minutes_before)` is now taken, and the
worker's `NOT EXISTS` sub-select — which also does not filter on org — suppresses the real reminder.
The invitee is never told about their meeting, and the poisoned row is attributed to the attacker's
organization.

Not reachable today: the only callers are the worker's repositories, and no HTTP route reaches them.
That is routing, not a control. `claim_task_reminder`, added later in the same family, already binds
the two (`WHERE id = p_task_id AND organization_id = p_organization_id`) — these two are brought to
that shape.

Both are `SELECT ... WHERE EXISTS` rather than a plain INSERT so a mismatched pair inserts nothing
and returns false, which is exactly how the callers already treat "someone else got there first".

Revision ID: b6d0f2a17c94
Revises: f2a4cec11a6c
Create Date: 2026-07-20 17:45:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b6d0f2a17c94"
down_revision: str | Sequence[str] | None = "f2a4cec11a6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOOKING_BOUND = """
            INSERT INTO booking_reminders (organization_id, booking_id, minutes_before)
            SELECT p_organization_id, p_booking_id, p_minutes_before
            WHERE EXISTS (
                SELECT 1 FROM bookings
                WHERE id = p_booking_id AND organization_id = p_organization_id
            )
            ON CONFLICT (booking_id, minutes_before) DO NOTHING;
"""

_BOOKING_ORIGINAL = """
            INSERT INTO booking_reminders (organization_id, booking_id, minutes_before)
            VALUES (p_organization_id, p_booking_id, p_minutes_before)
            ON CONFLICT (booking_id, minutes_before) DO NOTHING;
"""

_EVENT_BOUND = """
            INSERT INTO calendar_event_reminders (organization_id, event_id, occurrence_start)
            SELECT p_organization_id, p_event_id, p_occurrence_start
            WHERE EXISTS (
                SELECT 1 FROM calendar_events
                WHERE id = p_event_id AND organization_id = p_organization_id
            )
            ON CONFLICT (event_id, occurrence_start) DO NOTHING;
"""

_EVENT_ORIGINAL = """
            INSERT INTO calendar_event_reminders (organization_id, event_id, occurrence_start)
            VALUES (p_organization_id, p_event_id, p_occurrence_start)
            ON CONFLICT (event_id, occurrence_start) DO NOTHING;
"""


def _replace(booking_body: str, event_body: str) -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION claim_booking_reminder(
            p_booking_id uuid, p_organization_id uuid, p_minutes_before int
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_count int;
        BEGIN
        {booking_body}
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count > 0;
        END
        $$;
        """
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION claim_calendar_event_reminder(
            p_event_id uuid, p_organization_id uuid, p_occurrence_start timestamptz
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_count int;
        BEGIN
        {event_body}
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count > 0;
        END
        $$;
        """
    )


def upgrade() -> None:
    _replace(_BOOKING_BOUND, _EVENT_BOUND)


def downgrade() -> None:
    _replace(_BOOKING_ORIGINAL, _EVENT_ORIGINAL)
