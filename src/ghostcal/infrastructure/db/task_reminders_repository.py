"""SQL implementation of the task reminder gateway (non-tenant; SECURITY DEFINER functions)."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.task_reminders import DueTask, TaskReminderGateway

_DUE = text(
    "SELECT task_id, organization_id, owner_email, owner_timezone, due_at, reminder_minutes "
    "FROM due_task_reminders()"
)


class SqlTaskReminderGateway(TaskReminderGateway):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def due_tasks(self) -> list[DueTask]:
        rows = (await self._session.execute(_DUE)).all()
        return [
            DueTask(
                task_id=r.task_id,
                organization_id=r.organization_id,
                owner_email=r.owner_email,
                owner_timezone=r.owner_timezone,
                due_at=r.due_at,
                reminder_minutes=r.reminder_minutes,
            )
            for r in rows
        ]

    async def claim(self, task_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        return bool(
            (
                await self._session.execute(
                    text("SELECT claim_task_reminder(:t, :o) AS claimed"),
                    {"t": str(task_id), "o": str(organization_id)},
                )
            ).scalar_one()
        )
