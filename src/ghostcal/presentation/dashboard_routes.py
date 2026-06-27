"""Host dashboard endpoints. Availability-schedule management (first slice).

Authenticated (``current_user``) and resolved to the caller's organization, then run under an
org-scoped session (RLS) filtered by owner.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.auth import AuthenticatedUser
from ghostcal.application.calendars import (
    NotConnected,
    connect_calendar,
    disconnect_calendar,
    list_available_calendars,
    sync_calendar,
)
from ghostcal.application.event_types import (
    BookingQuestion,
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
from ghostcal.application.meetings import MeetingNotFound, cancel_meeting, list_meetings
from ghostcal.application.mirror import unmirror_booking
from ghostcal.application.notifications import send_booking_cancellation
from ghostcal.application.organization import (
    HandleTaken,
    InvalidHandle,
    OrganizationData,
    get_organization,
    update_organization,
)
from ghostcal.application.ports.calendar import CalendarAuthError, CalendarError
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
from ghostcal.config import get_settings
from ghostcal.infrastructure.calendars import CaldavCalendarClient
from ghostcal.infrastructure.db.caldav_repository import SqlCaldavConnectionRepository
from ghostcal.infrastructure.db.event_types_repository import SqlEventTypesRepository
from ghostcal.infrastructure.db.meetings_repository import SqlMeetingsRepository
from ghostcal.infrastructure.db.membership import primary_membership
from ghostcal.infrastructure.db.organization_repository import SqlOrganizationRepository
from ghostcal.infrastructure.db.schedules_repository import SqlSchedulesRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.security.encryption import SecretBox
from ghostcal.presentation.auth_routes import current_user
from ghostcal.presentation.schemas import (
    CalendarConnectIn,
    CalendarCredentialsIn,
    CalendarInfoOut,
    CalendarStatusOut,
    CreatedOut,
    EventTypeDetailOut,
    EventTypeIn,
    MeetingOut,
    OrganizationIn,
    OrganizationOut,
    OverrideSchema,
    RuleSchema,
    ScheduleIn,
    ScheduleOut,
    SyncResultOut,
)

_settings = get_settings()
router = APIRouter(prefix="/v1/me", tags=["dashboard"])
_clock = SystemClock()
_mailer = build_email_sender(_settings)
_cipher = SecretBox(_settings.token_encryption_key.get_secret_value())
_calendar_client = CaldavCalendarClient()
_logger = logging.getLogger("ghostcal.dashboard")


@dataclass(frozen=True, slots=True)
class Member:
    user: AuthenticatedUser
    organization_id: uuid.UUID
    role: str


async def current_member(user: AuthenticatedUser = Depends(current_user)) -> Member:
    async with db_session() as session:
        membership = await primary_membership(session, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="user has no organization")
    org_id, role = membership
    return Member(user=user, organization_id=org_id, role=role)


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
        questions=tuple(
            BookingQuestion(
                id=q.id,
                label=q.label,
                type=q.type,
                required=q.required,
                options=tuple(q.options),
            )
            for q in payload.questions
        ),
        kind=payload.kind,
        host_ids=tuple(payload.host_ids),
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
        await _check_pool_hosts(repo, payload)
        try:
            event_type_id = await create_event_type(repo, member.user.id, _event_type_in(payload))
        except InvalidEventType as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreatedOut(id=event_type_id)


async def _check_pool_hosts(repo: SqlEventTypesRepository, payload: EventTypeIn) -> None:
    if payload.kind not in ("round_robin", "collective"):
        return
    if await repo.non_member_hosts(tuple(payload.host_ids)):
        raise HTTPException(status_code=422, detail="all team hosts must be organization members")


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
        await _check_pool_hosts(repo, payload)
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


@router.post("/meetings/{booking_id}/cancel", status_code=204)
async def cancel_my_meeting(
    booking_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        repo = SqlMeetingsRepository(session, member.organization_id)
        try:
            cancelled = await cancel_meeting(repo, booking_id, member.user.id)
        except MeetingNotFound as exc:
            raise HTTPException(status_code=404, detail="meeting not found") from exc

    # Best-effort, after commit: notify the invitee that their meeting was cancelled.
    try:
        await send_booking_cancellation(
            _mailer,
            invitee_email=cancelled.invitee_email,
            invitee_timezone=cancelled.invitee_timezone,
            event_title=cancelled.event_title,
            host_name=member.user.name,
            start_at=cancelled.start_at,
        )
    except Exception:
        _logger.exception("failed to send cancellation for booking %s", booking_id)

    # Best-effort: remove the mirrored event from the host's external calendar.
    try:
        async with org_session(member.organization_id) as session:
            await unmirror_booking(
                SqlCaldavConnectionRepository(session, member.organization_id),
                _cipher,
                _calendar_client,
                host_id=member.user.id,
                external_event_uid=cancelled.external_event_uid,
            )
    except Exception:
        _logger.exception("failed to unmirror booking %s from calendar", booking_id)


# --- Organization profile (handle) -----------------------------------------------------------


def _organization_out(org: OrganizationData) -> OrganizationOut:
    return OrganizationOut(id=org.id, name=org.name, slug=org.slug)


@router.get("/organization", response_model=OrganizationOut)
async def get_my_organization(member: Member = Depends(current_member)) -> OrganizationOut:
    async with org_session(member.organization_id) as session:
        repo = SqlOrganizationRepository(session, member.organization_id)
        org = await get_organization(repo)
    return _organization_out(org)


@router.put("/organization", response_model=OrganizationOut)
async def update_my_organization(
    payload: OrganizationIn, member: Member = Depends(current_member)
) -> OrganizationOut:
    async with org_session(member.organization_id) as session:
        repo = SqlOrganizationRepository(session, member.organization_id)
        try:
            org = await update_organization(repo, name=payload.name, slug=payload.slug)
        except InvalidHandle as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HandleTaken as exc:
            raise HTTPException(status_code=409, detail="handle already taken") from exc
    return _organization_out(org)


# --- CalDAV calendar connection --------------------------------------------------------------


def _calendar_status(record: object) -> CalendarStatusOut:
    if record is None:
        return CalendarStatusOut(connected=False)
    return CalendarStatusOut(
        connected=True,
        server_url=record.server_url,  # type: ignore[attr-defined]
        username=record.username,  # type: ignore[attr-defined]
        calendar_name=record.calendar_name,  # type: ignore[attr-defined]
        status=record.status,  # type: ignore[attr-defined]
        last_synced_at=record.last_synced_at,  # type: ignore[attr-defined]
    )


@router.get("/calendar", response_model=CalendarStatusOut)
async def get_calendar(member: Member = Depends(current_member)) -> CalendarStatusOut:
    async with org_session(member.organization_id) as session:
        repo = SqlCaldavConnectionRepository(session, member.organization_id)
        record = await repo.get(member.user.id)
    return _calendar_status(record)


@router.post("/calendar/calendars", response_model=list[CalendarInfoOut])
async def list_caldav_calendars(
    payload: CalendarCredentialsIn, member: Member = Depends(current_member)
) -> list[CalendarInfoOut]:
    try:
        calendars = await list_available_calendars(
            _calendar_client,
            server_url=payload.server_url,
            username=payload.username,
            password=payload.password,
        )
    except CalendarAuthError as exc:
        raise HTTPException(status_code=401, detail="invalid calendar credentials") from exc
    except CalendarError as exc:
        raise HTTPException(status_code=502, detail="could not reach the calendar server") from exc
    return [CalendarInfoOut(name=c.name, url=c.url) for c in calendars]


@router.post("/calendar", response_model=CalendarStatusOut)
async def connect_calendar_endpoint(
    payload: CalendarConnectIn, member: Member = Depends(current_member)
) -> CalendarStatusOut:
    async with org_session(member.organization_id) as session:
        repo = SqlCaldavConnectionRepository(session, member.organization_id)
        try:
            await connect_calendar(
                repo,
                _cipher,
                user_id=member.user.id,
                server_url=payload.server_url,
                username=payload.username,
                password=payload.password,
                calendar_url=payload.calendar_url,
                calendar_name=payload.calendar_name,
            )
            await sync_calendar(repo, _cipher, _calendar_client, _clock, user_id=member.user.id)
            record = await repo.get(member.user.id)
        except CalendarAuthError as exc:
            raise HTTPException(status_code=401, detail="invalid calendar credentials") from exc
        except CalendarError as exc:
            raise HTTPException(
                status_code=502, detail="could not reach the calendar server"
            ) from exc
    return _calendar_status(record)


@router.post("/calendar/sync", response_model=SyncResultOut)
async def sync_calendar_endpoint(
    member: Member = Depends(current_member),
) -> SyncResultOut:
    async with org_session(member.organization_id) as session:
        repo = SqlCaldavConnectionRepository(session, member.organization_id)
        try:
            count = await sync_calendar(
                repo, _cipher, _calendar_client, _clock, user_id=member.user.id
            )
        except NotConnected as exc:
            raise HTTPException(status_code=404, detail="no calendar connected") from exc
        except CalendarAuthError as exc:
            raise HTTPException(status_code=401, detail="calendar needs re-authentication") from exc
        except CalendarError as exc:
            raise HTTPException(
                status_code=502, detail="could not reach the calendar server"
            ) from exc
    return SyncResultOut(synced=count)


@router.delete("/calendar", status_code=204)
async def disconnect_calendar_endpoint(member: Member = Depends(current_member)) -> None:
    async with org_session(member.organization_id) as session:
        repo = SqlCaldavConnectionRepository(session, member.organization_id)
        await disconnect_calendar(repo, member.user.id)
