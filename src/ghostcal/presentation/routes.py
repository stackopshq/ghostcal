"""Public scheduling endpoints: read availability and create a booking.

Each request opens an organization-scoped session (RLS), builds the SQL repository, and runs the
use case. Domain errors are translated to HTTP status codes.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.scheduling import (
    BookingRequest,
    EventTypeNotFound,
    OrganizationNotFound,
    SlotUnavailable,
    create_booking,
    get_availability,
    get_booking_page,
    get_event_type,
)
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import org_session
from ghostcal.presentation.schemas import (
    AvailabilityOut,
    BookingIn,
    BookingOut,
    BookingPageOut,
    EventTypeOut,
    PublicEventTypeOut,
    SlotOut,
)

router = APIRouter(prefix="/v1/orgs/{organization_id}", tags=["scheduling"])
_clock = SystemClock()


@router.get("/event-types", response_model=BookingPageOut)
async def read_booking_page(organization_id: uuid.UUID) -> BookingPageOut:
    async with org_session(organization_id) as session:
        repo = SqlSchedulingRepository(session, organization_id)
        try:
            page = await get_booking_page(repo)
        except OrganizationNotFound as exc:
            raise HTTPException(status_code=404, detail="organization not found") from exc
    return BookingPageOut(
        organization_name=page.organization_name,
        event_types=[PublicEventTypeOut(**asdict(e)) for e in page.event_types],
    )


@router.get("/event-types/{event_type_id}", response_model=EventTypeOut)
async def read_event_type(
    organization_id: uuid.UUID,
    event_type_id: uuid.UUID,
) -> EventTypeOut:
    async with org_session(organization_id) as session:
        repo = SqlSchedulingRepository(session, organization_id)
        try:
            context = await get_event_type(repo, event_type_id=event_type_id)
        except EventTypeNotFound as exc:
            raise HTTPException(status_code=404, detail="event type not found") from exc
    return EventTypeOut(
        id=context.event_type_id,
        title=context.title,
        duration_min=int(context.event.duration.total_seconds() // 60),
        location_type=context.location_type,
        host_name=context.host_name,
    )


@router.get(
    "/event-types/{event_type_id}/availability",
    response_model=AvailabilityOut,
)
async def read_availability(
    organization_id: uuid.UUID,
    event_type_id: uuid.UUID,
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
) -> AvailabilityOut:
    async with org_session(organization_id) as session:
        repo = SqlSchedulingRepository(session, organization_id)
        try:
            slots = await get_availability(
                repo,
                _clock,
                event_type_id=event_type_id,
                from_date=from_date,
                to_date=to_date,
            )
        except EventTypeNotFound as exc:
            raise HTTPException(status_code=404, detail="event type not found") from exc
    return AvailabilityOut(
        event_type_id=event_type_id,
        slots=[SlotOut(start=s.start, end=s.end) for s in slots],
    )


@router.post(
    "/event-types/{event_type_id}/bookings",
    response_model=BookingOut,
    status_code=201,
)
async def create_booking_endpoint(
    organization_id: uuid.UUID,
    event_type_id: uuid.UUID,
    payload: BookingIn,
) -> BookingOut:
    async with org_session(organization_id) as session:
        repo = SqlSchedulingRepository(session, organization_id)
        request = BookingRequest(
            event_type_id=event_type_id,
            start_at=payload.start_at,
            invitee_name=payload.invitee_name,
            invitee_email=payload.invitee_email,
            invitee_timezone=payload.invitee_timezone,
        )
        try:
            confirmation = await create_booking(repo, _clock, request)
        except EventTypeNotFound as exc:
            raise HTTPException(status_code=404, detail="event type not found") from exc
        except SlotUnavailable as exc:
            raise HTTPException(status_code=409, detail="slot is no longer available") from exc
    return BookingOut(
        id=confirmation.booking_id,
        start_at=confirmation.start_at,
        end_at=confirmation.end_at,
    )
