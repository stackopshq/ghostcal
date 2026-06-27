"""Invitee self-service: view, cancel and reschedule a booking via a signed token (no account)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from ghostcal.application.ports.clock import Clock
from ghostcal.application.scheduling import (
    BookingConfirmation,
    BookingRequest,
    SchedulingRepository,
    create_booking,
)


class ManageError(Exception):
    pass


class BookingNotFound(ManageError):
    pass


class BookingNotActive(ManageError):
    """The booking is already cancelled or rescheduled."""


@dataclass(frozen=True, slots=True)
class BookingDetail:
    booking_id: uuid.UUID
    event_type_id: uuid.UUID
    event_title: str
    host_name: str
    host_email: str
    host_timezone: str
    organization_slug: str
    event_slug: str
    invitee_name: str
    invitee_email: str
    invitee_timezone: str
    duration_min: int
    location_type: str
    start_at: datetime
    end_at: datetime
    status: str


class ManageRepository:
    async def get_detail(self, booking_id: uuid.UUID) -> BookingDetail | None:
        raise NotImplementedError

    async def cancel(self, booking_id: uuid.UUID) -> BookingDetail | None:
        """Cancel a confirmed booking and return its detail; None if not found/not confirmed."""
        raise NotImplementedError


async def get_booking(repo: ManageRepository, booking_id: uuid.UUID) -> BookingDetail:
    detail = await repo.get_detail(booking_id)
    if detail is None:
        raise BookingNotFound(str(booking_id))
    return detail


async def cancel_booking(repo: ManageRepository, booking_id: uuid.UUID) -> BookingDetail:
    detail = await repo.cancel(booking_id)
    if detail is None:
        raise BookingNotFound(str(booking_id))
    return detail


async def reschedule_booking(
    manage_repo: ManageRepository,
    scheduling_repo: SchedulingRepository,
    clock: Clock,
    *,
    booking_id: uuid.UUID,
    new_start: datetime,
) -> tuple[BookingDetail, BookingConfirmation]:
    """Cancel the old booking and create a new one at ``new_start`` for the same event/invitee.

    Runs in one transaction: if the new slot is unavailable, ``create_booking`` raises and the
    cancellation is rolled back, so nothing changes.
    """
    detail = await manage_repo.get_detail(booking_id)
    if detail is None:
        raise BookingNotFound(str(booking_id))
    if detail.status != "confirmed":
        raise BookingNotActive(str(booking_id))

    await manage_repo.cancel(booking_id)
    confirmation = await create_booking(
        scheduling_repo,
        clock,
        BookingRequest(
            event_type_id=detail.event_type_id,
            start_at=new_start,
            invitee_name=detail.invitee_name,
            invitee_email=detail.invitee_email,
            invitee_timezone=detail.invitee_timezone,
        ),
    )
    return detail, confirmation
