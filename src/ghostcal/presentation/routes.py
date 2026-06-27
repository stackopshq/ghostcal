"""Public scheduling endpoints, addressed by slugs: /v1/orgs/{org_slug}/event-types[/{event_slug}].

Each request resolves the org slug to its id (RLS-bypassing SECURITY DEFINER function), then opens
an organization-scoped session (RLS) and resolves the event slug within it. Domain errors map to
HTTP status codes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.notifications import send_booking_confirmation
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
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.membership import organization_id_by_slug
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.security.tokens import BookingManagementCodec
from ghostcal.presentation.schemas import (
    AvailabilityOut,
    BookingIn,
    BookingOut,
    BookingPageOut,
    EventTypeOut,
    PublicEventTypeOut,
    SlotOut,
)

_settings = get_settings()
router = APIRouter(prefix="/v1/orgs/{org_slug}", tags=["scheduling"])
_clock = SystemClock()
_mailer = build_email_sender(_settings)
_manage_codec = BookingManagementCodec(_settings.secret_key.get_secret_value())
_logger = logging.getLogger("ghostcal.booking")


def _manage_url(booking_id: uuid.UUID, organization_id: uuid.UUID) -> str:
    token = _manage_codec.encode(booking_id, organization_id)
    return f"{_settings.frontend_base_url}/manage/{token}"


async def resolve_org(org_slug: str) -> uuid.UUID:
    async with db_session() as session:
        org_id = await organization_id_by_slug(session, org_slug)
    if org_id is None:
        raise HTTPException(status_code=404, detail="organization not found")
    return org_id


OrgId = Annotated[uuid.UUID, Depends(resolve_org)]


async def _event_type_id(repo: SqlSchedulingRepository, event_slug: str) -> uuid.UUID:
    event_type_id = await repo.get_event_type_id_by_slug(event_slug)
    if event_type_id is None:
        raise HTTPException(status_code=404, detail="event type not found")
    return event_type_id


def _repo(session: AsyncSession, org_id: uuid.UUID) -> SqlSchedulingRepository:
    return SqlSchedulingRepository(session, org_id)


@router.get("/event-types", response_model=BookingPageOut)
async def read_booking_page(org_id: OrgId) -> BookingPageOut:
    async with org_session(org_id) as session:
        try:
            page = await get_booking_page(_repo(session, org_id))
        except OrganizationNotFound as exc:
            raise HTTPException(status_code=404, detail="organization not found") from exc
    return BookingPageOut(
        organization_name=page.organization_name,
        event_types=[PublicEventTypeOut(**asdict(e)) for e in page.event_types],
    )


@router.get("/event-types/{event_slug}", response_model=EventTypeOut)
async def read_event_type(org_id: OrgId, event_slug: str) -> EventTypeOut:
    async with org_session(org_id) as session:
        repo = _repo(session, org_id)
        event_type_id = await _event_type_id(repo, event_slug)
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


@router.get("/event-types/{event_slug}/availability", response_model=AvailabilityOut)
async def read_availability(
    org_id: OrgId,
    event_slug: str,
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
) -> AvailabilityOut:
    async with org_session(org_id) as session:
        repo = _repo(session, org_id)
        event_type_id = await _event_type_id(repo, event_slug)
        try:
            slots = await get_availability(
                repo, _clock, event_type_id=event_type_id, from_date=from_date, to_date=to_date
            )
        except EventTypeNotFound as exc:
            raise HTTPException(status_code=404, detail="event type not found") from exc
    return AvailabilityOut(
        event_type_id=event_type_id,
        slots=[SlotOut(start=s.start, end=s.end) for s in slots],
    )


@router.post("/event-types/{event_slug}/bookings", response_model=BookingOut, status_code=201)
async def create_booking_endpoint(org_id: OrgId, event_slug: str, payload: BookingIn) -> BookingOut:
    async with org_session(org_id) as session:
        repo = _repo(session, org_id)
        event_type_id = await _event_type_id(repo, event_slug)
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

    # Best-effort, after commit: an email failure must not undo a confirmed booking.
    try:
        await send_booking_confirmation(
            _mailer, confirmation, manage_url=_manage_url(confirmation.booking_id, org_id)
        )
    except Exception:
        _logger.exception("failed to send confirmation for booking %s", confirmation.booking_id)

    return BookingOut(
        id=confirmation.booking_id,
        start_at=confirmation.start_at,
        end_at=confirmation.end_at,
    )
