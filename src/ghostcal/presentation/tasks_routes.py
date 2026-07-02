"""To-do / task endpoints (zero-knowledge). Authenticated and scoped to the caller's org (RLS)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.tasks import (
    TaskInput,
    TaskNotFound,
    create_task,
    delete_task,
    list_tasks,
    set_task_completed,
    update_task,
)
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.db.tasks_repository import SqlTaskRepository
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import CreatedOut, TaskCompleteIn, TaskIn, TaskOut

router = APIRouter(prefix="/v1/me", tags=["tasks"])
_clock = SystemClock()


def _repo(session: object, org_id: uuid.UUID) -> SqlTaskRepository:
    return SqlTaskRepository(session, org_id)  # type: ignore[arg-type]


@router.get("/tasks", response_model=list[TaskOut])
async def list_my_tasks(member: Member = Depends(current_member)) -> list[TaskOut]:
    async with org_session(member.organization_id) as session:
        tasks = await list_tasks(_repo(session, member.organization_id), member.user.id)
    return [
        TaskOut(
            id=task.id,
            content=task.content,
            due_at=task.due_at,
            completed=task.completed,
            completed_at=task.completed_at,
            created_at=task.created_at,
        )
        for task in tasks
    ]


@router.post("/tasks", response_model=CreatedOut, status_code=201)
async def create_my_task(payload: TaskIn, member: Member = Depends(current_member)) -> CreatedOut:
    async with org_session(member.organization_id) as session:
        task_id = await create_task(
            _repo(session, member.organization_id),
            member.user.id,
            TaskInput(content=payload.content, due_at=payload.due_at),
        )
    return CreatedOut(id=task_id)


@router.put("/tasks/{task_id}", status_code=204)
async def update_my_task(
    task_id: uuid.UUID, payload: TaskIn, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await update_task(
                _repo(session, member.organization_id),
                member.user.id,
                task_id,
                TaskInput(content=payload.content, due_at=payload.due_at),
            )
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc


@router.post("/tasks/{task_id}/complete", status_code=204)
async def complete_my_task(
    task_id: uuid.UUID, payload: TaskCompleteIn, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await set_task_completed(
                _repo(session, member.organization_id),
                _clock,
                member.user.id,
                task_id,
                completed=payload.completed,
            )
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_my_task(task_id: uuid.UUID, member: Member = Depends(current_member)) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await delete_task(_repo(session, member.organization_id), member.user.id, task_id)
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
