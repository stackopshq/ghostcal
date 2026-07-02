"""Task reminders: find tasks whose reminder moment has arrived and email the owner.

A task fires a single reminder at ``due_at - reminder_minutes``. There's no recurrence, so the
gateway lists due tasks and atomically claims each (setting ``reminded_at``) so at most one reminder
is sent. The email never names the task — the content is zero-knowledge.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from ghostcal.application.notifications import send_task_reminder
from ghostcal.application.ports.email import EmailSender

logger = logging.getLogger("ghostcal.task_reminders")


@dataclass(frozen=True, slots=True)
class DueTask:
    task_id: uuid.UUID
    organization_id: uuid.UUID
    owner_email: str
    owner_timezone: str
    due_at: datetime
    reminder_minutes: int


class TaskReminderGateway:
    async def due_tasks(self) -> list[DueTask]:
        """Reminder-enabled, incomplete tasks whose reminder moment has passed and not yet sent."""
        raise NotImplementedError

    async def claim(self, task_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Mark the task reminded. Return True only if THIS call claimed it (idempotent)."""
        raise NotImplementedError


async def dispatch_task_reminders(gateway: TaskReminderGateway, mailer: EmailSender) -> int:
    """Send a reminder for each due task, claiming it first. Returns the count sent."""
    sent = 0
    for task in await gateway.due_tasks():
        if not await gateway.claim(task.task_id, task.organization_id):
            continue
        try:
            await send_task_reminder(
                mailer,
                to=task.owner_email,
                due_at=task.due_at,
                timezone=task.owner_timezone,
                minutes_before=task.reminder_minutes,
            )
            sent += 1
        except Exception:
            logger.exception("failed to send task reminder for %s", task.task_id)
    return sent
