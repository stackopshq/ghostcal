"""Calendar endpoints: calendars CRUD, events CRUD, and the unified agenda read (ADR-0004)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.calendar import (
    CalendarError,
    EventInput,
    EventNotFound,
    create_event,
    delete_event,
    get_agenda,
    get_event,
    list_calendars,
    update_event,
)
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.session import org_session
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    AgendaItemOut,
    CalendarIn,
    CalendarOut,
    CreatedOut,
    EventIn,
    EventOut,
)

router = APIRouter(prefix="/v1/me", tags=["calendar"])


def _repo(session: object, org_id: uuid.UUID) -> SqlCalendarRepository:
    return SqlCalendarRepository(session, org_id)  # type: ignore[arg-type]


def _to_input(payload: EventIn) -> EventInput:
    return EventInput(
        calendar_id=payload.calendar_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        timezone=payload.timezone,
        all_day=payload.all_day,
        rrule=payload.rrule,
        exdates=tuple(payload.exdates),
        content=payload.content,
        reminder_minutes=payload.reminder_minutes,
    )


@router.get("/calendars", response_model=list[CalendarOut])
async def list_my_calendars(member: Member = Depends(current_member)) -> list[CalendarOut]:
    async with org_session(member.organization_id) as session:
        calendars = await list_calendars(_repo(session, member.organization_id), member.user.id)
    return [
        CalendarOut(id=c.id, name=c.name, color=c.color, is_default=c.is_default) for c in calendars
    ]


@router.post("/calendars", response_model=CalendarOut, status_code=201)
async def create_my_calendar(
    payload: CalendarIn, member: Member = Depends(current_member)
) -> CalendarOut:
    async with org_session(member.organization_id) as session:
        c = await _repo(session, member.organization_id).create_calendar(
            member.user.id, name=payload.name, color=payload.color
        )
    return CalendarOut(id=c.id, name=c.name, color=c.color, is_default=c.is_default)


@router.get("/calendar/agenda", response_model=list[AgendaItemOut])
async def read_agenda(
    member: Member = Depends(current_member),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(alias="to"),
) -> list[AgendaItemOut]:
    async with org_session(member.organization_id) as session:
        items = await get_agenda(_repo(session, member.organization_id), member.user.id, from_, to)
    return [
        AgendaItemOut(
            source=i.source,
            start=i.start,
            end=i.end,
            all_day=i.all_day,
            calendar_id=i.calendar_id,
            event_id=i.event_id,
            content=i.content,
            title=i.title,
        )
        for i in items
    ]


@router.post("/calendar/events", response_model=CreatedOut, status_code=201)
async def create_my_event(payload: EventIn, member: Member = Depends(current_member)) -> CreatedOut:
    async with org_session(member.organization_id) as session:
        try:
            event_id = await create_event(
                _repo(session, member.organization_id), member.user.id, _to_input(payload)
            )
        except CalendarError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreatedOut(id=event_id)


@router.get("/calendar/events/{event_id}", response_model=EventOut)
async def read_my_event(event_id: uuid.UUID, member: Member = Depends(current_member)) -> EventOut:
    async with org_session(member.organization_id) as session:
        try:
            e = await get_event(_repo(session, member.organization_id), member.user.id, event_id)
        except EventNotFound as exc:
            raise HTTPException(status_code=404, detail="event not found") from exc
    return EventOut(
        id=e.id,
        calendar_id=e.calendar_id,
        start_at=e.start_at,
        end_at=e.end_at,
        timezone=e.timezone,
        all_day=e.all_day,
        rrule=e.rrule,
        exdates=list(e.exdates),
        content=e.content,
        reminder_minutes=e.reminder_minutes,
    )


@router.put("/calendar/events/{event_id}", status_code=204)
async def update_my_event(
    event_id: uuid.UUID, payload: EventIn, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await update_event(
                _repo(session, member.organization_id), member.user.id, event_id, _to_input(payload)
            )
        except EventNotFound as exc:
            raise HTTPException(status_code=404, detail="event not found") from exc
        except CalendarError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_my_event(event_id: uuid.UUID, member: Member = Depends(current_member)) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await delete_event(_repo(session, member.organization_id), member.user.id, event_id)
        except EventNotFound as exc:
            raise HTTPException(status_code=404, detail="event not found") from exc
