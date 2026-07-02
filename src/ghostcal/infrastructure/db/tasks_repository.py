"""SQL implementation of the task repository port (org-scoped RLS session)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.tasks import TaskInput, TaskRecord, TaskRepository
from ghostcal.infrastructure.db import models


def _record(row: models.Task) -> TaskRecord:
    return TaskRecord(
        id=row.id,
        content=row.content,
        due_at=row.due_at,
        completed=row.completed,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


class SqlTaskRepository(TaskRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def create_task(self, owner_id: uuid.UUID, data: TaskInput) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.Task)
                .values(
                    organization_id=self._org_id,
                    owner_id=owner_id,
                    content=data.content,
                    due_at=data.due_at,
                )
                .returning(models.Task.id)
            )
        ).scalar_one()

    async def list_tasks(self, owner_id: uuid.UUID) -> list[TaskRecord]:
        rows = (
            (
                await self._session.execute(
                    select(models.Task)
                    .where(models.Task.owner_id == owner_id)
                    .order_by(
                        models.Task.completed,
                        models.Task.due_at.asc().nullslast(),
                        models.Task.created_at,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_record(r) for r in rows]

    async def update_task(self, owner_id: uuid.UUID, task_id: uuid.UUID, data: TaskInput) -> bool:
        result = await self._session.execute(
            update(models.Task)
            .where(models.Task.id == task_id, models.Task.owner_id == owner_id)
            .values(content=data.content, due_at=data.due_at)
            .returning(models.Task.id)
        )
        return result.first() is not None

    async def set_completed(
        self, owner_id: uuid.UUID, task_id: uuid.UUID, *, completed: bool, now: datetime
    ) -> bool:
        result = await self._session.execute(
            update(models.Task)
            .where(models.Task.id == task_id, models.Task.owner_id == owner_id)
            .values(completed=completed, completed_at=now if completed else None)
            .returning(models.Task.id)
        )
        return result.first() is not None

    async def delete_task(self, owner_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.Task)
            .where(models.Task.id == task_id, models.Task.owner_id == owner_id)
            .returning(models.Task.id)
        )
        return result.first() is not None
