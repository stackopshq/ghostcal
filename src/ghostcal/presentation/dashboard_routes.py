"""Host dashboard endpoints. Availability-schedule management (first slice).

Authenticated (``current_user``) and resolved to the caller's organization, then run under an
org-scoped session (RLS) filtered by owner.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.auth import AuthenticatedUser
from ghostcal.application.event_types import (
    EventTypeData,
    EventTypeInput,
    EventTypeInUse,
    EventTypeNotFound,
    InvalidEventType,
    create_event_type,
    delete_event_type,
    get_event_type,
    list_event_types,
    update_event_type,
)
from ghostcal.application.meetings import list_meetings
from ghostcal.application.ports.clock import SystemClock
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
from ghostcal.infrastructure.db.event_types_repository import SqlEventTypesRepository
from ghostcal.infrastructure.db.meetings_repository import SqlMeetingsRepository
from ghostcal.infrastructure.db.membership import primary_organization
from ghostcal.infrastructure.db.schedules_repository import SqlSchedulesRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.presentation.auth_routes import current_user
from ghostcal.presentation.schemas import (
    CreatedOut,
    EventTypeDetailOut,
    EventTypeIn,
    MeetingOut,
    OverrideSchema,
    RuleSchema,
    ScheduleIn,
    ScheduleOut,
)

router = APIRouter(prefix="/v1/me", tags=["dashboard"])
_clock = SystemClock()


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


# --- Event types -----------------------------------------------------------------------------

_EVENT_TYPE_NOT_FOUND = "event type not found"


def _event_type_out(event_type: EventTypeData) -> EventTypeDetailOut:
    return EventTypeDetailOut(**asdict(event_type))


def _event_type_in(payload: EventTypeIn) -> EventTypeInput:
    return EventTypeInput(
        title=payload.title,
        description=payload.description,
        duration_min=payload.duration_min,
        slot_interval_min=payload.slot_interval_min,
        buffer_before_min=payload.buffer_before_min,
        buffer_after_min=payload.buffer_after_min,
        min_notice_min=payload.min_notice_min,
        date_window_days=payload.date_window_days,
        max_per_day=payload.max_per_day,
        location_type=payload.location_type,
        active=payload.active,
    )


@router.get("/event-types", response_model=list[EventTypeDetailOut])
async def list_my_event_types(
    member: Member = Depends(current_member),
) -> list[EventTypeDetailOut]:
    async with org_session(member.organization_id) as session:
        repo = SqlEventTypesRepository(session, member.organization_id)
        items = await list_event_types(repo, member.user.id)
    return [_event_type_out(e) for e in items]


@router.post("/event-types", response_model=CreatedOut, status_code=201)
async def create_my_event_type(
    payload: EventTypeIn, member: Member = Depends(current_member)
) -> CreatedOut:
    async with org_session(member.organization_id) as session:
        repo = SqlEventTypesRepository(session, member.organization_id)
        try:
            event_type_id = await create_event_type(repo, member.user.id, _event_type_in(payload))
        except InvalidEventType as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreatedOut(id=event_type_id)


@router.get("/event-types/{event_type_id}", response_model=EventTypeDetailOut)
async def get_my_event_type(
    event_type_id: uuid.UUID, member: Member = Depends(current_member)
) -> EventTypeDetailOut:
    async with org_session(member.organization_id) as session:
        repo = SqlEventTypesRepository(session, member.organization_id)
        try:
            event_type = await get_event_type(repo, event_type_id, member.user.id)
        except EventTypeNotFound as exc:
            raise HTTPException(status_code=404, detail=_EVENT_TYPE_NOT_FOUND) from exc
    return _event_type_out(event_type)


@router.put("/event-types/{event_type_id}", response_model=EventTypeDetailOut)
async def update_my_event_type(
    event_type_id: uuid.UUID, payload: EventTypeIn, member: Member = Depends(current_member)
) -> EventTypeDetailOut:
    async with org_session(member.organization_id) as session:
        repo = SqlEventTypesRepository(session, member.organization_id)
        try:
            await update_event_type(repo, event_type_id, member.user.id, _event_type_in(payload))
            event_type = await get_event_type(repo, event_type_id, member.user.id)
        except EventTypeNotFound as exc:
            raise HTTPException(status_code=404, detail=_EVENT_TYPE_NOT_FOUND) from exc
        except InvalidEventType as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _event_type_out(event_type)


@router.delete("/event-types/{event_type_id}", status_code=204)
async def delete_my_event_type(
    event_type_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        repo = SqlEventTypesRepository(session, member.organization_id)
        try:
            await delete_event_type(repo, event_type_id, member.user.id)
        except EventTypeNotFound as exc:
            raise HTTPException(status_code=404, detail=_EVENT_TYPE_NOT_FOUND) from exc
        except EventTypeInUse as exc:
            raise HTTPException(
                status_code=409, detail="event type has bookings and cannot be deleted"
            ) from exc


# --- Meetings (bookings) ---------------------------------------------------------------------


@router.get("/meetings", response_model=list[MeetingOut])
async def list_my_meetings(
    scope: Literal["upcoming", "past"] = Query("upcoming"),
    member: Member = Depends(current_member),
) -> list[MeetingOut]:
    now = _clock.now()
    async with org_session(member.organization_id) as session:
        repo = SqlMeetingsRepository(session, member.organization_id)
        items = await list_meetings(repo, member.user.id, upcoming=(scope == "upcoming"), now=now)
    return [MeetingOut(**asdict(m)) for m in items]
