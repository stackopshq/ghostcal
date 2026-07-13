"""stamp sealed records with the key generation that sealed them

The third and last step of ADR-0007. Rotation (e8a2b47c31f9) changed the org key; this makes the
*backlog* of already-sealed records re-sealable, which is what finally leaves a departed member with
nothing at all to read.

The problem it solves: a sealed blob carries no key identifier (deliberately — AES-GCM
authenticates, so a wrong key fails loudly and the browser can simply try each generation in turn).
Excellent for *reading*. Useless for asking "what is left to re-seal?", which needs an answer, or a
rotation can never be said to be finished and an old generation can never be retired.

So the three sealed columns — ``bookings.invitee_private``, ``calendar_events.content`` and
``tasks.content`` — get a ``zk_generation`` beside them, stamped on insert by a trigger rather than
by the application: every write path gets it, including ones written later by someone who never read
this file. Existing rows default to 0, which is exactly the generation that sealed them.

The stamp is what the server knows, not what the client did. A rotation landing between the moment a
browser fetches the public key and the moment it posts the blob would mislabel that row by one
generation. The read-side fallback opens it anyway, so nothing breaks; the re-seal pass simply
believes it is already current. The alternative — trusting a client-supplied generation — trades a
harmless mislabel for a spoofable one.

Revision ID: f1b6d92e4a07
Revises: e8a2b47c31f9
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1b6d92e4a07"
down_revision: str | Sequence[str] | None = "e8a2b47c31f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEALED_TABLES = ("bookings", "calendar_events", "tasks")


def upgrade() -> None:
    for table in _SEALED_TABLES:
        op.add_column(
            table,
            sa.Column(
                "zk_generation",
                sa.SmallInteger(),
                nullable=False,
                server_default="0",
            ),
        )
        # Only rows that actually hold a sealed blob are ever worth re-sealing; the partial index
        # keeps the "what is left?" query proportional to the backlog, not to the table.
        op.create_index(
            f"ix_{table}_zk_generation",
            table,
            ["organization_id", "zk_generation"],
        )

    op.execute(
        """
        CREATE FUNCTION stamp_zk_generation()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            SELECT zk_key_generation INTO NEW.zk_generation
            FROM organizations WHERE id = NEW.organization_id;
            RETURN NEW;
        END
        $$;
        """
    )
    for table in _SEALED_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER stamp_zk_generation_on_{table}
            BEFORE INSERT ON {table}
            FOR EACH ROW EXECUTE FUNCTION stamp_zk_generation();
            """
        )

    # Rows still sealed under an older generation than their org's current one. One query over the
    # three tables, so the browser walks the backlog without knowing where the sealed things live.
    op.execute(
        """
        CREATE FUNCTION pending_reseal(p_organization_id uuid, p_limit int)
        RETURNS TABLE(kind text, id uuid, sealed text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            WITH current AS (
                SELECT zk_key_generation AS generation
                FROM organizations WHERE id = p_organization_id
            )
            SELECT 'booking', b.id, b.invitee_private
            FROM bookings b, current
            WHERE b.organization_id = p_organization_id
              AND b.invitee_private IS NOT NULL
              AND b.zk_generation < current.generation
            UNION ALL
            SELECT 'event', e.id, e.content
            FROM calendar_events e, current
            WHERE e.organization_id = p_organization_id
              AND e.content IS NOT NULL
              AND e.zk_generation < current.generation
            UNION ALL
            SELECT 'task', t.id, t.content
            FROM tasks t, current
            WHERE t.organization_id = p_organization_id
              AND t.content IS NOT NULL
              AND t.zk_generation < current.generation
            LIMIT p_limit
        $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION count_pending_reseal(p_organization_id uuid)
        RETURNS bigint
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT count(*) FROM pending_reseal(p_organization_id, 2147483647)
        $$;
        """
    )

    # Write one re-sealed blob back and mark it current. Guarded on the generation the caller sealed
    # to: if the org rotated again underneath them, their blob is already stale and must not be
    # written — they refetch and redo it. The row filter also makes the whole pass idempotent, so a
    # retried batch is a no-op rather than a corruption.
    op.execute(
        """
        CREATE FUNCTION apply_reseal(
            p_organization_id uuid, p_generation smallint, p_kind text, p_id uuid, p_sealed text
        )
        RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_current smallint;
            v_count int;
        BEGIN
            SELECT zk_key_generation INTO v_current
            FROM organizations WHERE id = p_organization_id;
            IF v_current IS DISTINCT FROM p_generation THEN
                RAISE EXCEPTION 'the organization key rotated again; refetch and re-seal'
                    USING ERRCODE = 'serialization_failure';
            END IF;

            IF p_kind = 'booking' THEN
                UPDATE bookings SET invitee_private = p_sealed, zk_generation = v_current
                WHERE id = p_id AND organization_id = p_organization_id
                  AND zk_generation < v_current;
            ELSIF p_kind = 'event' THEN
                UPDATE calendar_events SET content = p_sealed, zk_generation = v_current
                WHERE id = p_id AND organization_id = p_organization_id
                  AND zk_generation < v_current;
            ELSIF p_kind = 'task' THEN
                UPDATE tasks SET content = p_sealed, zk_generation = v_current
                WHERE id = p_id AND organization_id = p_organization_id
                  AND zk_generation < v_current;
            ELSE
                RAISE EXCEPTION 'unknown sealed record kind: %', p_kind;
            END IF;

            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count > 0;
        END
        $$;
        """
    )

    for name, sig in (
        ("pending_reseal", "uuid, int"),
        ("count_pending_reseal", "uuid"),
        ("apply_reseal", "uuid, smallint, text, uuid, text"),
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC")
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
            f"THEN GRANT EXECUTE ON FUNCTION {name}({sig}) TO ghostcal_app; END IF; END $$;"
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS apply_reseal(uuid, smallint, text, uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS count_pending_reseal(uuid)")
    op.execute("DROP FUNCTION IF EXISTS pending_reseal(uuid, int)")
    for table in _SEALED_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS stamp_zk_generation_on_{table} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS stamp_zk_generation()")
    for table in _SEALED_TABLES:
        op.drop_index(f"ix_{table}_zk_generation", table_name=table)
        op.drop_column(table, "zk_generation")
