"""Invitee self-service endpoints (no account): view, cancel, reschedule via a signed token."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from ghostcal.application.manage import (
    BookingDetail,
    BookingNotActive,
    BookingNotFound,
    cancel_booking,
    get_booking,
    reschedule_booking,
)
from ghostcal.application.mirror import mirror_booking, unmirror_booking
from ghostcal.application.notifications import (
    send_booking_cancellation,
    send_booking_confirmation,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.scheduling import BookingConfirmation, SlotUnavailable
from ghostcal.config import get_settings
from ghostcal.infrastructure.calendars import CaldavCalendarClient
from ghostcal.infrastructure.db.caldav_repository import SqlCaldavConnectionRepository
from ghostcal.infrastructure.db.manage_repository import SqlBookingManageRepository
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.security.encryption import SecretBox
from ghostcal.infrastructure.security.tokens import BookingManagementCodec
from ghostcal.presentation.schemas import BookingOut, ManageBookingOut, RescheduleIn

_settings = get_settings()
router = APIRouter(prefix="/v1/bookings/manage", tags=["manage"])
_clock = SystemClock()
_mailer = build_email_sender(_settings)
_codec = BookingManagementCodec(_settings.secret_key.get_secret_value())
_cipher = SecretBox(_settings.token_encryption_key.get_secret_value())
_calendar_client = CaldavCalendarClient()
_logger = logging.getLogger("ghostcal.manage")

_NOT_FOUND = "booking not found"
_LOCATION_LABELS = {
    "google_meet": "Google Meet",
    "ms_teams": "Microsoft Teams",
    "zoom": "Zoom",
    "in_person": "In person",
    "phone": "Phone",
    "custom": "Custom",
}


async def _unmirror(org_id: uuid.UUID, host_id: uuid.UUID, external_event_uid: str | None) -> None:
    async with org_session(org_id) as session:
        await unmirror_booking(
            SqlCaldavConnectionRepository(session, org_id),
            _cipher,
            _calendar_client,
            host_id=host_id,
            external_event_uid=external_event_uid,
        )


async def _mirror(org_id: uuid.UUID, conf: BookingConfirmation) -> None:
    async with org_session(org_id) as session:
        await mirror_booking(
            SqlCaldavConnectionRepository(session, org_id),
            SqlSchedulingRepository(session, org_id),
            _cipher,
            _calendar_client,
            host_id=conf.host_id,
            booking_id=conf.booking_id,
            summary=f"{conf.event_title} with {conf.invitee_name}",
            description=f"Booked via GhostCal — {conf.invitee_email}",
            location=_LOCATION_LABELS.get(conf.location_type, conf.location_type),
            start=conf.start_at,
            end=conf.end_at,
        )


def _decode(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    try:
        return _codec.decode(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc


def _manage_url(booking_id: uuid.UUID, organization_id: uuid.UUID) -> str:
    return f"{_settings.frontend_base_url}/manage/{_codec.encode(booking_id, organization_id)}"


def _detail_out(detail: BookingDetail) -> ManageBookingOut:
    return ManageBookingOut(
        event_title=detail.event_title,
        host_name=detail.host_name,
        organization_slug=detail.organization_slug,
        event_slug=detail.event_slug,
        invitee_name=detail.invitee_name,
        invitee_timezone=detail.invitee_timezone,
        duration_min=detail.duration_min,
        location_type=detail.location_type,
        start_at=detail.start_at,
        end_at=detail.end_at,
        status=detail.status,
    )


async def _notify_cancellation(detail: BookingDetail) -> None:
    # Invitee (confirmation of their cancellation) and host (a heads-up).
    await send_booking_cancellation(
        _mailer,
        invitee_email=detail.invitee_email,
        invitee_timezone=detail.invitee_timezone,
        event_title=detail.event_title,
        host_name=detail.host_name,
        start_at=detail.start_at,
    )
    await send_booking_cancellation(
        _mailer,
        invitee_email=detail.host_email,
        invitee_timezone=detail.host_timezone,
        event_title=detail.event_title,
        host_name=detail.invitee_name,
        start_at=detail.start_at,
    )


@router.get("/{token}", response_model=ManageBookingOut)
async def view_booking(token: str) -> ManageBookingOut:
    booking_id, org_id = _decode(token)
    async with org_session(org_id) as session:
        repo = SqlBookingManageRepository(session, org_id)
        try:
            detail = await get_booking(repo, booking_id)
        except BookingNotFound as exc:
            raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    return _detail_out(detail)


@router.post("/{token}/cancel", status_code=204)
async def cancel(token: str) -> None:
    booking_id, org_id = _decode(token)
    async with org_session(org_id) as session:
        repo = SqlBookingManageRepository(session, org_id)
        try:
            detail = await cancel_booking(repo, booking_id)
        except BookingNotFound as exc:
            raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    try:
        await _notify_cancellation(detail)
    except Exception:
        _logger.exception("failed to send cancellation for booking %s", detail.booking_id)
    try:
        await _unmirror(org_id, detail.host_id, detail.external_event_uid)
    except Exception:
        _logger.exception("failed to unmirror booking %s from calendar", detail.booking_id)


@router.post("/{token}/reschedule", response_model=BookingOut)
async def reschedule(token: str, payload: RescheduleIn) -> BookingOut:
    booking_id, org_id = _decode(token)
    async with org_session(org_id) as session:
        manage_repo = SqlBookingManageRepository(session, org_id)
        scheduling_repo = SqlSchedulingRepository(session, org_id)
        try:
            old_detail, confirmation = await reschedule_booking(
                manage_repo,
                scheduling_repo,
                _clock,
                booking_id=booking_id,
                new_start=payload.start_at,
            )
        except BookingNotFound as exc:
            raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
        except BookingNotActive as exc:
            raise HTTPException(status_code=409, detail="booking is no longer active") from exc
        except SlotUnavailable as exc:
            raise HTTPException(status_code=409, detail="that time is no longer available") from exc

    try:
        await send_booking_confirmation(
            _mailer, confirmation, manage_url=_manage_url(confirmation.booking_id, org_id)
        )
    except Exception:
        _logger.exception("failed to send reschedule confirmation for %s", confirmation.booking_id)
    # Move the mirrored event: remove the old, create the new.
    try:
        await _unmirror(org_id, old_detail.host_id, old_detail.external_event_uid)
        await _mirror(org_id, confirmation)
    except Exception:
        _logger.exception("failed to move mirrored event for %s", confirmation.booking_id)

    return BookingOut(
        id=confirmation.booking_id, start_at=confirmation.start_at, end_at=confirmation.end_at
    )
