"""To-do / task use cases (Fantastical-style). Framework-free; persistence is a port.

Zero-knowledge: the task title/notes live in the sealed ``content`` blob (the server never reads
them); the due date and completion state are cleartext so due lists and reminders work.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from ghostcal.application.ports.clock import Clock


class TaskError(Exception):
    pass


class TaskNotFound(TaskError):
    pass


@dataclass(frozen=True, slots=True)
class TaskInput:
    content: str | None
    due_at: datetime | None
    reminder_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class TaskRecord:
    id: uuid.UUID
    content: str | None
    due_at: datetime | None
    completed: bool
    completed_at: datetime | None
    created_at: datetime
    reminder_minutes: int | None = None


class TaskRepository:
    async def create_task(self, owner_id: uuid.UUID, data: TaskInput) -> uuid.UUID:
        raise NotImplementedError

    async def list_tasks(self, owner_id: uuid.UUID) -> list[TaskRecord]:
        raise NotImplementedError

    async def update_task(self, owner_id: uuid.UUID, task_id: uuid.UUID, data: TaskInput) -> bool:
        raise NotImplementedError

    async def set_completed(
        self, owner_id: uuid.UUID, task_id: uuid.UUID, *, completed: bool, now: datetime
    ) -> bool:
        raise NotImplementedError

    async def delete_task(self, owner_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        raise NotImplementedError


async def create_task(repo: TaskRepository, owner_id: uuid.UUID, data: TaskInput) -> uuid.UUID:
    return await repo.create_task(owner_id, data)


async def list_tasks(repo: TaskRepository, owner_id: uuid.UUID) -> list[TaskRecord]:
    return await repo.list_tasks(owner_id)


async def update_task(
    repo: TaskRepository, owner_id: uuid.UUID, task_id: uuid.UUID, data: TaskInput
) -> None:
    if not await repo.update_task(owner_id, task_id, data):
        raise TaskNotFound(str(task_id))


async def set_task_completed(
    repo: TaskRepository,
    clock: Clock,
    owner_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    completed: bool,
) -> None:
    if not await repo.set_completed(owner_id, task_id, completed=completed, now=clock.now()):
        raise TaskNotFound(str(task_id))


async def delete_task(repo: TaskRepository, owner_id: uuid.UUID, task_id: uuid.UUID) -> None:
    if not await repo.delete_task(owner_id, task_id):
        raise TaskNotFound(str(task_id))
