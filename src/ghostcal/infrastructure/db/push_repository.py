"""SQL implementation of the CalDAV publication repository port.

The queue is filled by a trigger on ``calendar_events`` (migration b5e93a2f7c18), not by anything
here — every write path gets it that way, including the ones written later by someone who never read
the migration. What this does is hand rows out and take them back once they have landed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.push import (
    PendingPush,
    PushOp,
    PushRepository,
    PushTarget,
)
from ghostcal.infrastructure.db import models


def _op(value: str) -> PushOp:
    if value not in ("upsert", "delete"):
        raise ValueError(f"unknown push op: {value}")
    return value  # type: ignore[return-value]


class SqlPushRepository(PushRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def set_target(
        self, owner_id: uuid.UUID, calendar_id: uuid.UUID, connection_id: uuid.UUID | None
    ) -> bool:
        # Scoped to the owner: RLS keeps other organizations out, and inside one, publishing a
        # colleague's calendar to your own phone is not a thing anyone should be able to do.
        result = await self._session.execute(
            update(models.Calendar)
            .where(
                models.Calendar.id == calendar_id,
                models.Calendar.owner_id == owner_id,
            )
            .values(push_connection_id=connection_id)
            .returning(models.Calendar.id)
        )
        return result.scalar_one_or_none() is not None

    async def backfill(self, calendar_id: uuid.UUID) -> int:
        count = (
            await self._session.execute(
                text("SELECT enqueue_calendar_backfill(:cid)"), {"cid": str(calendar_id)}
            )
        ).scalar_one()
        return int(count)

    async def pending(self, owner_id: uuid.UUID, *, limit: int) -> list[PendingPush]:
        rows = (
            await self._session.execute(
                select(
                    models.CalendarPushQueue.id,
                    models.CalendarPushQueue.op,
                    models.CalendarPushQueue.external_uid,
                    models.CalendarEvent.content,
                    models.CalendarEvent.start_at,
                    models.CalendarEvent.end_at,
                    models.CalendarEvent.all_day,
                    models.CalendarEvent.rrule,
                )
                .join(
                    models.Calendar,
                    models.Calendar.id == models.CalendarPushQueue.calendar_id,
                )
                .outerjoin(
                    models.CalendarEvent,
                    models.CalendarEvent.id == models.CalendarPushQueue.event_id,
                )
                .where(models.Calendar.owner_id == owner_id)
                .order_by(models.CalendarPushQueue.created_at)
                .limit(limit)
            )
        ).all()
        return [
            PendingPush(
                id=r.id,
                op=_op(r.op),
                external_uid=r.external_uid,
                content=r.content,
                start_at=r.start_at,
                end_at=r.end_at,
                all_day=r.all_day if r.all_day is not None else False,
                rrule=r.rrule,
            )
            for r in rows
        ]

    async def target_for(self, owner_id: uuid.UUID, queue_id: uuid.UUID) -> PushTarget | None:
        row = (
            await self._session.execute(
                select(
                    models.Calendar.id,
                    models.CaldavConnection.id.label("connection_id"),
                    models.CaldavConnection.server_url,
                    models.CaldavConnection.username,
                    models.CaldavConnection.password_encrypted,
                    models.CaldavConnection.calendar_url,
                )
                .join(
                    models.CalendarPushQueue,
                    models.CalendarPushQueue.calendar_id == models.Calendar.id,
                )
                .join(
                    models.CaldavConnection,
                    models.CaldavConnection.id == models.Calendar.push_connection_id,
                )
                .where(
                    models.CalendarPushQueue.id == queue_id,
                    models.Calendar.owner_id == owner_id,
                )
            )
        ).first()
        if row is None:
            return None
        return PushTarget(
            calendar_id=row.id,
            connection_id=row.connection_id,
            server_url=row.server_url,
            username=row.username,
            password_encrypted=row.password_encrypted,
            calendar_url=row.calendar_url,
        )

    async def done(self, owner_id: uuid.UUID, queue_id: uuid.UUID) -> None:
        # Only after the CalDAV write landed. Dropping the row first would lose the change on any
        # failure, silently — the whole point of a queue is that a failed push stays queued.
        await self._session.execute(
            delete(models.CalendarPushQueue).where(
                models.CalendarPushQueue.id == queue_id,
                models.CalendarPushQueue.calendar_id.in_(
                    select(models.Calendar.id).where(models.Calendar.owner_id == owner_id)
                ),
            )
        )
