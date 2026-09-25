"""SQL implementation of the CalDAV connection repository (org-scoped, several per member)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.calendars import CaldavConnectionRepository, ConnectionRecord
from ghostcal.application.ports.calendar import BusyEvent
from ghostcal.infrastructure.db import models


def _record(row: models.CaldavConnection) -> ConnectionRecord:
    return ConnectionRecord(
        id=row.id,
        user_id=row.user_id,
        server_url=row.server_url,
        username=row.username,
        password_encrypted=row.password_encrypted,
        calendar_url=row.calendar_url,
        calendar_name=row.calendar_name,
        color=row.color,
        mirror_bookings=row.mirror_bookings,
        mirror_detail=row.mirror_detail,
        status=row.status,
        last_synced_at=row.last_synced_at,
    )


class SqlCaldavConnectionRepository(CaldavConnectionRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_for_user(self, user_id: uuid.UUID) -> list[ConnectionRecord]:
        rows = (
            await self._session.execute(
                select(models.CaldavConnection)
                .where(models.CaldavConnection.user_id == user_id)
                .order_by(models.CaldavConnection.created_at)
            )
        ).scalars()
        return [_record(row) for row in rows]

    async def get(self, connection_id: uuid.UUID, user_id: uuid.UUID) -> ConnectionRecord | None:
        row = (
            await self._session.execute(
                select(models.CaldavConnection).where(
                    models.CaldavConnection.id == connection_id,
                    # Scoped to the owner as well as the id: RLS keeps other organizations out, but
                    # nothing else would stop one member from syncing a colleague's calendar.
                    models.CaldavConnection.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        return _record(row) if row is not None else None

    async def mirror_target(self, user_id: uuid.UUID) -> ConnectionRecord | None:
        row = (
            await self._session.execute(
                select(models.CaldavConnection).where(
                    models.CaldavConnection.user_id == user_id,
                    models.CaldavConnection.mirror_bookings.is_(True),
                )
            )
        ).scalar_one_or_none()
        return _record(row) if row is not None else None

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        server_url: str,
        username: str,
        password_encrypted: str,
        calendar_url: str,
        calendar_name: str | None,
        color: str,
        mirror_bookings: bool,
    ) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.CaldavConnection)
                .values(
                    organization_id=self._org_id,
                    user_id=user_id,
                    server_url=server_url,
                    username=username,
                    password_encrypted=password_encrypted,
                    calendar_url=calendar_url,
                    calendar_name=calendar_name,
                    color=color,
                    mirror_bookings=mirror_bookings,
                    status="active",
                )
                .returning(models.CaldavConnection.id)
            )
        ).scalar_one()

    async def delete(self, connection_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.CaldavConnection)
            .where(
                models.CaldavConnection.id == connection_id,
                models.CaldavConnection.user_id == user_id,
            )
            .returning(models.CaldavConnection.mirror_bookings)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False

        # Deleting the mirror target would leave bookings mirroring nowhere, silently. Hand the job
        # to the oldest remaining calendar rather than let it fall on the floor.
        if row:
            await self._session.execute(
                update(models.CaldavConnection)
                .where(
                    models.CaldavConnection.id.in_(
                        select(models.CaldavConnection.id)
                        .where(models.CaldavConnection.user_id == user_id)
                        .order_by(models.CaldavConnection.created_at)
                        .limit(1)
                    )
                )
                .values(mirror_bookings=True)
            )
        return True

    async def set_mirror_target(self, connection_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        # Clear first: the partial unique index allows exactly one, so setting before clearing would
        # collide with the incumbent.
        await self._session.execute(
            update(models.CaldavConnection)
            .where(
                models.CaldavConnection.user_id == user_id,
                models.CaldavConnection.mirror_bookings.is_(True),
            )
            .values(mirror_bookings=False)
        )
        result = await self._session.execute(
            update(models.CaldavConnection)
            .where(
                models.CaldavConnection.id == connection_id,
                models.CaldavConnection.user_id == user_id,
            )
            .values(mirror_bookings=True)
            .returning(models.CaldavConnection.id)
        )
        return result.scalar_one_or_none() is not None

    async def set_mirror_detail(
        self, connection_id: uuid.UUID, user_id: uuid.UUID, detail: str
    ) -> bool:
        # `user_id` in the WHERE clause, like the neighbours: what a booking discloses to a third
        # party is not something one member may change on another's connection.
        result = await self._session.execute(
            update(models.CaldavConnection)
            .where(
                models.CaldavConnection.id == connection_id,
                models.CaldavConnection.user_id == user_id,
            )
            .values(mirror_detail=detail)
            .returning(models.CaldavConnection.id)
        )
        return result.scalar_one_or_none() is not None

    async def set_color(self, connection_id: uuid.UUID, user_id: uuid.UUID, color: str) -> bool:
        # `user_id` in the WHERE clause, like `set_mirror_target` above: ownership is enforced by
        # the statement itself rather than by a read that another request could race.
        result = await self._session.execute(
            update(models.CaldavConnection)
            .where(
                models.CaldavConnection.id == connection_id,
                models.CaldavConnection.user_id == user_id,
            )
            .values(color=color)
            .returning(models.CaldavConnection.id)
        )
        return result.scalar_one_or_none() is not None

    async def replace_busy(
        self, connection_id: uuid.UUID, host_id: uuid.UUID, busy: list[BusyEvent]
    ) -> None:
        await self._session.execute(
            delete(models.ExternalBusy).where(models.ExternalBusy.connection_id == connection_id)
        )
        if busy:
            await self._session.execute(
                insert(models.ExternalBusy),
                [
                    {
                        "organization_id": self._org_id,
                        "connection_id": connection_id,
                        "host_id": host_id,
                        "start_at": e.start,
                        "end_at": e.end,
                        "summary": e.summary,
                    }
                    for e in busy
                ],
            )

    async def host_timezone(self, user_id: uuid.UUID) -> str | None:
        return (
            await self._session.execute(
                select(models.User.timezone).where(models.User.id == user_id)
            )
        ).scalar_one_or_none()

    async def mark_synced(self, connection_id: uuid.UUID, when: datetime, status: str) -> None:
        await self._session.execute(
            update(models.CaldavConnection)
            .where(models.CaldavConnection.id == connection_id)
            .values(last_synced_at=when, status=status)
        )
