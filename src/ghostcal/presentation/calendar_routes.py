"""Calendar endpoints: calendars CRUD, events CRUD, and the unified agenda read (ADR-0004)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.attendees import (
    EventNotOwned,
    add_attendee,
    list_attendees,
    remove_attendee,
    send_invitation,
)
from ghostcal.application.calendar import (
    CalendarError,
    CalendarNotFound,
    EventInput,
    EventNotFound,
    create_event,
    delete_event,
    get_agenda,
    get_event,
    list_calendars,
    list_shares,
    share_calendar,
    unshare_calendar,
    update_event,
)
from ghostcal.application.subscriptions import (
    FeedUnreachable,
    SubscriptionInput,
    SubscriptionNotFound,
    add_subscription,
    delete_subscription,
    list_subscriptions,
    refresh_subscription,
)
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.attendees_repository import SqlAttendeeRepository
from ghostcal.infrastructure.db.calendar_repository import SqlCalendarRepository
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.db.subscriptions_repository import SqlSubscriptionRepository
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    AgendaItemOut,
    AttendeeAddedOut,
    AttendeeIn,
    AttendeeOut,
    CalendarIn,
    CalendarOut,
    CreatedOut,
    EventIn,
    EventOut,
    SendInvitationIn,
    ShareIn,
    ShareOut,
    SubscriptionIn,
    SubscriptionOut,
)

router = APIRouter(prefix="/v1/me", tags=["calendar"])
_settings = get_settings()
_mailer = build_email_sender(_settings)


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
        CalendarOut(
            id=c.id,
            name=c.name,
            color=c.color,
            is_default=c.is_default,
            is_shared=c.is_shared,
            owner_name=c.owner_name,
        )
        for c in calendars
    ]


@router.get("/calendars/{calendar_id}/shares", response_model=list[ShareOut])
async def list_calendar_shares(
    calendar_id: uuid.UUID, member: Member = Depends(current_member)
) -> list[ShareOut]:
    async with org_session(member.organization_id) as session:
        shares = await list_shares(
            _repo(session, member.organization_id), member.user.id, calendar_id
        )
    return [ShareOut(user_id=s.user_id, name=s.name) for s in shares]


@router.post("/calendars/{calendar_id}/shares", status_code=204)
async def share_my_calendar(
    calendar_id: uuid.UUID, payload: ShareIn, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await share_calendar(
                _repo(session, member.organization_id), member.user.id, calendar_id, payload.user_id
            )
        except CalendarNotFound as exc:
            raise HTTPException(status_code=404, detail="calendar not found") from exc


@router.delete("/calendars/{calendar_id}/shares/{user_id}", status_code=204)
async def unshare_my_calendar(
    calendar_id: uuid.UUID, user_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await unshare_calendar(
                _repo(session, member.organization_id), member.user.id, calendar_id, user_id
            )
        except CalendarNotFound as exc:
            raise HTTPException(status_code=404, detail="calendar not found") from exc


@router.post("/calendars", response_model=CalendarOut, status_code=201)
async def create_my_calendar(
    payload: CalendarIn, member: Member = Depends(current_member)
) -> CalendarOut:
    async with org_session(member.organization_id) as session:
        c = await _repo(session, member.organization_id).create_calendar(
            member.user.id, name=payload.name, color=payload.color
        )
    return CalendarOut(id=c.id, name=c.name, color=c.color, is_default=c.is_default)


_MAX_AGENDA_WINDOW = timedelta(days=366)


@router.get("/calendar/agenda", response_model=list[AgendaItemOut])
async def read_agenda(
    member: Member = Depends(current_member),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(alias="to"),
) -> list[AgendaItemOut]:
    # Bound the window so a recurring event can't be asked to expand over an unbounded range (DoS).
    if to < from_ or (to - from_) > _MAX_AGENDA_WINDOW:
        raise HTTPException(status_code=422, detail="agenda window must be within 366 days")
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
            read_only=i.read_only,
            reminder_minutes=i.reminder_minutes,
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


# --- Event attendees (personal-calendar invitations + RSVP) ----------------------------------


@router.get("/calendar/events/{event_id}/attendees", response_model=list[AttendeeOut])
async def list_event_attendees(
    event_id: uuid.UUID, member: Member = Depends(current_member)
) -> list[AttendeeOut]:
    async with org_session(member.organization_id) as session:
        try:
            rows = await list_attendees(
                SqlAttendeeRepository(session, member.organization_id), member.user.id, event_id
            )
        except EventNotOwned as exc:
            raise HTTPException(status_code=404, detail="event not found") from exc
    return [AttendeeOut(id=r.id, email=r.email, name=r.name, status=r.status) for r in rows]


@router.post(
    "/calendar/events/{event_id}/attendees", response_model=AttendeeAddedOut, status_code=201
)
async def add_event_attendee(
    event_id: uuid.UUID, payload: AttendeeIn, member: Member = Depends(current_member)
) -> AttendeeAddedOut:
    async with org_session(member.organization_id) as session:
        try:
            added = await add_attendee(
                SqlAttendeeRepository(session, member.organization_id),
                member.user.id,
                event_id,
                email=payload.email,
                name=payload.name,
            )
        except EventNotOwned as exc:
            raise HTTPException(status_code=404, detail="event not found") from exc
    return AttendeeAddedOut(id=added.id, email=added.email, token=added.token)


@router.delete("/calendar/events/{event_id}/attendees/{attendee_id}", status_code=204)
async def remove_event_attendee(
    event_id: uuid.UUID, attendee_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await remove_attendee(
                SqlAttendeeRepository(session, member.organization_id),
                member.user.id,
                event_id,
                attendee_id,
            )
        except EventNotOwned as exc:
            raise HTTPException(status_code=404, detail="event not found") from exc


@router.post("/calendar/events/{event_id}/invite", status_code=202)
async def send_event_invitation_email(
    event_id: uuid.UUID, payload: SendInvitationIn, member: Member = Depends(current_member)
) -> dict[str, str]:
    # The organiser owns the event (checked when the attendee was added); here we only relay the
    # invitation email built from browser-supplied cleartext (never persisted).
    rsvp_url = f"{_settings.frontend_base_url}/invite/{payload.token}"
    await send_invitation(
        _mailer,
        to=payload.email,
        title=payload.title,
        location=payload.location,
        organizer_name=payload.organizer_name,
        start_at=payload.start_at,
        end_at=payload.end_at,
        all_day=payload.all_day,
        rsvp_url=rsvp_url,
    )
    return {"status": "sent"}


# --- Public calendar subscriptions (ICS) -----------------------------------------------------


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_my_subscriptions(member: Member = Depends(current_member)) -> list[SubscriptionOut]:
    async with org_session(member.organization_id) as session:
        subs = await list_subscriptions(
            SqlSubscriptionRepository(session, member.organization_id), member.user.id
        )
    return [SubscriptionOut.model_validate(s, from_attributes=True) for s in subs]


@router.post("/subscriptions", response_model=CreatedOut, status_code=201)
async def add_my_subscription(
    payload: SubscriptionIn, member: Member = Depends(current_member)
) -> CreatedOut:
    async with org_session(member.organization_id) as session:
        repo = SqlSubscriptionRepository(session, member.organization_id)
        try:
            sub_id = await add_subscription(
                repo,
                member.user.id,
                SubscriptionInput(name=payload.name, url=payload.url, color=payload.color),
            )
        except FeedUnreachable as exc:
            raise HTTPException(status_code=422, detail=f"could not fetch feed: {exc}") from exc
        # Populate its events right away so it shows without waiting for the worker.
        await refresh_subscription(repo, sub_id)
    return CreatedOut(id=sub_id)


@router.post("/subscriptions/{subscription_id}/refresh", status_code=204)
async def refresh_my_subscription(
    subscription_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await refresh_subscription(
                SqlSubscriptionRepository(session, member.organization_id), subscription_id
            )
        except SubscriptionNotFound as exc:
            raise HTTPException(status_code=404, detail="subscription not found") from exc
        except FeedUnreachable as exc:
            raise HTTPException(status_code=502, detail=f"feed error: {exc}") from exc


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def delete_my_subscription(
    subscription_id: uuid.UUID, member: Member = Depends(current_member)
) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await delete_subscription(
                SqlSubscriptionRepository(session, member.organization_id),
                subscription_id,
                member.user.id,
            )
        except SubscriptionNotFound as exc:
            raise HTTPException(status_code=404, detail="subscription not found") from exc
