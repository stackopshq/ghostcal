"""SQL implementation of the CalDAV connection repository (org-scoped, one per member)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.calendars import CaldavConnectionRepository, ConnectionRecord
from ghostcal.domain.time import TimeRange
from ghostcal.infrastructure.db import models


class SqlCaldavConnectionRepository(CaldavConnectionRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def get(self, user_id: uuid.UUID) -> ConnectionRecord | None:
        row = (
            await self._session.execute(
                select(models.CaldavConnection).where(models.CaldavConnection.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return ConnectionRecord(
            id=row.id,
            user_id=row.user_id,
            server_url=row.server_url,
            username=row.username,
            password_encrypted=row.password_encrypted,
            calendar_url=row.calendar_url,
            calendar_name=row.calendar_name,
            status=row.status,
            last_synced_at=row.last_synced_at,
        )

    async def save(
        self,
        user_id: uuid.UUID,
        *,
        server_url: str,
        username: str,
        password_encrypted: str,
        calendar_url: str,
        calendar_name: str | None,
    ) -> uuid.UUID:
        values = {
            "organization_id": self._org_id,
            "user_id": user_id,
            "server_url": server_url,
            "username": username,
            "password_encrypted": password_encrypted,
            "calendar_url": calendar_url,
            "calendar_name": calendar_name,
            "status": "active",
        }
        stmt = (
            pg_insert(models.CaldavConnection)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    models.CaldavConnection.organization_id,
                    models.CaldavConnection.user_id,
                ],
                set_={
                    "server_url": server_url,
                    "username": username,
                    "password_encrypted": password_encrypted,
                    "calendar_url": calendar_url,
                    "calendar_name": calendar_name,
                    "status": "active",
                },
            )
            .returning(models.CaldavConnection.id)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def delete(self, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.CaldavConnection)
            .where(models.CaldavConnection.user_id == user_id)
            .returning(models.CaldavConnection.id)
        )
        return result.scalar_one_or_none() is not None

    async def replace_busy(
        self, connection_id: uuid.UUID, host_id: uuid.UUID, busy: list[TimeRange]
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
                        "start_at": tr.start,
                        "end_at": tr.end,
                    }
                    for tr in busy
                ],
            )

    async def mark_synced(self, connection_id: uuid.UUID, when: datetime, status: str) -> None:
        await self._session.execute(
            update(models.CaldavConnection)
            .where(models.CaldavConnection.id == connection_id)
            .values(last_synced_at=when, status=status)
        )
