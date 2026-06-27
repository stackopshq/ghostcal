"""Host dashboard endpoints. Availability-schedule management (first slice).

Authenticated (``current_user``) and resolved to the caller's organization, then run under an
org-scoped session (RLS) filtered by owner.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.auth import AuthenticatedUser
from ghostcal.application.schedules import (
    InvalidSchedule,
    OverrideData,
    RuleData,
    ScheduleData,
    ScheduleNotFound,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)
from ghostcal.infrastructure.db.membership import primary_organization
from ghostcal.infrastructure.db.schedules_repository import SqlSchedulesRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.presentation.auth_routes import current_user
from ghostcal.presentation.schemas import (
    CreatedOut,
    OverrideSchema,
    RuleSchema,
    ScheduleIn,
    ScheduleOut,
)

router = APIRouter(prefix="/v1/me", tags=["dashboard"])


@dataclass(frozen=True, slots=True)
class Member:
    user: AuthenticatedUser
    organization_id: uuid.UUID


async def current_member(user: AuthenticatedUser = Depends(current_user)) -> Member:
    async with db_session() as session:
        org_id = await primary_organization(session, user.id)
    if org_id is None:
        raise HTTPException(status_code=403, detail="user has no organization")
    return Member(user=user, organization_id=org_id)


def _to_out(schedule: ScheduleData) -> ScheduleOut:
    return ScheduleOut(
        id=schedule.id,
        name=schedule.name,
        timezone=schedule.timezone,
        rules=[RuleSchema(weekday=r.weekday, start=r.start, end=r.end) for r in schedule.rules],
        overrides=[
            OverrideSchema(day=o.day, is_available=o.is_available, start=o.start, end=o.end)
            for o in schedule.overrides
        ],
    )


def _rules_in(payload: ScheduleIn) -> list[RuleData]:
    return [RuleData(weekday=r.weekday, start=r.start, end=r.end) for r in payload.rules]


def _overrides_in(payload: ScheduleIn) -> list[OverrideData]:
    return [
        OverrideData(day=o.day, is_available=o.is_available, start=o.start, end=o.end)
        for o in payload.overrides
    ]


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_my_schedules(member: Member = Depends(current_member)) -> list[ScheduleOut]:
    async with org_session(member.organization_id) as session:
        repo = SqlSchedulesRepository(session, member.organization_id)
        schedules = await list_schedules(repo, member.user.id)
    return [_to_out(s) for s in schedules]


@router.post("/schedules", response_model=CreatedOut, status_code=201)
async def create_my_schedule(
    payload: ScheduleIn, member: Member = Depends(current_member)
) -> CreatedOut:
    async with org_session(member.organization_id) as session:
        repo = SqlSchedulesRepository(session, member.organization_id)
        try:
            schedule_id = await create_schedule(
                repo,
                member.user.id,
                name=payload.name,
                timezone=payload.timezone,
                rules=_rules_in(payload),
                overrides=_overrides_in(payload),
            )
        except InvalidSchedule as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreatedOut(id=schedule_id)


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut)
async def get_my_schedule(
    schedule_id: uuid.UUID, member: Member = Depends(current_member)
) -> ScheduleOut:
    async with org_session(member.organization_id) as session:
        repo = SqlSchedulesRepository(session, member.organization_id)
        try:
            schedule = await get_schedule(repo, schedule_id, member.user.id)
        except ScheduleNotFound as exc:
            raise HTTPException(status_code=404, detail="schedule not found") from exc
    return _to_out(schedule)


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
async def update_my_schedule(
    schedule_id: uuid.UUID, payload: ScheduleIn, member: Member = Depends(current_member)
) -> ScheduleOut:
    async with org_session(member.organization_id) as session:
        repo = SqlSchedulesRepository(session, member.organization_id)
        try:
            await update_schedule(
                repo,
                schedule_id,
                member.user.id,
                name=payload.name,
                timezone=payload.timezone,
                rules=_rules_in(payload),
                overrides=_overrides_in(payload),
            )
            schedule = await get_schedule(repo, schedule_id, member.user.id)
        except ScheduleNotFound as exc:
            raise HTTPException(status_code=404, detail="schedule not found") from exc
        except InvalidSchedule as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_out(schedule)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_my_schedule(
    schedule_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        repo = SqlSchedulesRepository(session, member.organization_id)
        try:
            await delete_schedule(repo, schedule_id, member.user.id)
        except ScheduleNotFound as exc:
            raise HTTPException(status_code=404, detail="schedule not found") from exc
