"""Account lifecycle endpoints: erasure (GDPR art. 17). See ADR-0006."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ghostcal.application.account import (
    AccountService,
    CancelledBooking,
    ConfirmationMismatch,
    InvalidPassword,
    SoleOwner,
    UnknownUser,
)
from ghostcal.application.notifications import send_booking_cancellation
from ghostcal.application.ports.clock import SystemClock
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.account_repository import SqlAccountRepository
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.presentation.auth_routes import CurrentUser
from ghostcal.presentation.schemas import AccountDeleteIn

router = APIRouter(prefix="/v1/me/account", tags=["account"])
logger = logging.getLogger(__name__)

_settings = get_settings()
_hasher = Argon2PasswordHasher()
_clock = SystemClock()
_mailer = build_email_sender(_settings)


@router.delete("", status_code=204)
async def delete_account(payload: AccountDeleteIn, user: CurrentUser) -> None:
    """Erase the account. Irreversible.

    Organizations the user is the sole member of are deleted outright; in shared organizations the
    user is anonymized out of the co-owned records. Refused (409) when the user is the last owner of
    a shared organization — someone has to stay able to administer it.
    """
    async with db_session() as session:
        service = AccountService(
            SqlAccountRepository(session),
            SqlAuthRepository(session),
            _hasher,
        )
        try:
            cancelled = await service.delete(
                user.id,
                email_confirmation=payload.email_confirmation,
                password=payload.password,
                now=_clock.now(),
            )
        except ConfirmationMismatch as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except InvalidPassword as exc:
            raise HTTPException(status_code=403, detail="password is incorrect") from exc
        except SoleOwner as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "you are the last owner of an organization that has other members — "
                    "promote another owner before deleting your account"
                ),
            ) from exc
        except UnknownUser as exc:
            raise HTTPException(status_code=404, detail="unknown user") from exc

    # After the commit, deliberately: the erasure must not be rolled back by a failing SMTP server.
    # The account is already gone, so a bounced notice is logged, never raised.
    for booking in cancelled:
        await _notify_cancellation(booking)


async def _notify_cancellation(booking: CancelledBooking) -> None:
    try:
        await send_booking_cancellation(
            _mailer,
            invitee_email=booking.invitee_email,
            invitee_timezone=booking.invitee_timezone,
            event_title=booking.event_title,
            host_name=None,  # The host no longer exists — naming them would be a fresh disclosure.
            start_at=booking.start_at,
        )
    except Exception:
        logger.exception("failed to notify an invitee that their meeting was cancelled")
