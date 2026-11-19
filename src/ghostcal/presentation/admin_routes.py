"""Instance administration endpoints. See ``application/administration.py``.

A caller who is not an instance administrator gets 404 on every route, not 403: the view does not
need to tell an ordinary account that it exists.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.account import AccountService, ConfirmationMismatch, SoleOwner
from ghostcal.application.administration import (
    AdministrationService,
    NotInstanceAdmin,
    RegistrationFixed,
    TargetIsAdmin,
    UnknownAccount,
)
from ghostcal.application.audit import AuditLog
from ghostcal.application.ports.clock import SystemClock
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.account_repository import SqlAccountRepository
from ghostcal.infrastructure.db.administration_repository import SqlAdministrationRepository
from ghostcal.infrastructure.db.audit_repository import SqlAuditSink
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.presentation.account_routes import _notify_cancellation
from ghostcal.presentation.auth_routes import CurrentUser
from ghostcal.presentation.schemas import (
    AdminAccountDeleteIn,
    AdminAccountOut,
    RegistrationIn,
    RegistrationOut,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])
logger = logging.getLogger("ghostcal.admin")

_settings = get_settings()
_hasher = Argon2PasswordHasher()
_clock = SystemClock()


def _service(session: AsyncSession) -> AdministrationService:
    auth_repo = SqlAuthRepository(session)
    return AdministrationService(
        SqlAdministrationRepository(session),
        auth_repo,
        AccountService(SqlAccountRepository(session), auth_repo, _hasher),
        AuditLog(SqlAuditSink(session)),
        _clock,
        admin_emails=_settings.instance_admin_emails,
        registration_fixed=_settings.registration_fixed,
    )


def _error(status: int, message: str, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"detail": message, "code": code})


@asynccontextmanager
async def _admin() -> AsyncIterator[AdministrationService]:
    """One transaction, and the error mapping every route shares."""
    try:
        async with db_session() as session:
            yield _service(session)
    except NotInstanceAdmin as exc:
        raise HTTPException(status_code=404, detail="Not Found") from exc
    except UnknownAccount as exc:
        raise _error(404, "unknown account", "unknown_account") from exc
    except TargetIsAdmin as exc:
        raise _error(
            409,
            "an instance administrator cannot be suspended or deleted here; "
            "remove the address from GHOSTCAL_ADMIN_EMAILS",
            "account_is_admin",
        ) from exc
    except RegistrationFixed as exc:
        raise _error(
            409, "registration is fixed by GHOSTCAL_REGISTRATION", "registration_fixed"
        ) from exc
    except ConfirmationMismatch as exc:
        raise _error(400, str(exc), "confirmation_mismatch") from exc
    except SoleOwner as exc:
        raise _error(
            409,
            "this account is the last owner of an organization that has other members",
            "sole_owner",
        ) from exc


async def _run[T](action: Callable[[AdministrationService], Awaitable[T]]) -> T:
    async with _admin() as service:
        return await action(service)


@router.get("/registration", response_model=RegistrationOut)
async def get_registration(user: CurrentUser) -> RegistrationOut:
    status = await _run(lambda s: s.registration(user))
    return RegistrationOut(open=status.open, fixed=status.fixed)


@router.put("/registration", response_model=RegistrationOut)
async def set_registration(payload: RegistrationIn, user: CurrentUser) -> RegistrationOut:
    status = await _run(lambda s: s.set_registration(user, open_=payload.open))
    return RegistrationOut(open=status.open, fixed=status.fixed)


@router.get("/accounts", response_model=list[AdminAccountOut])
async def list_accounts(user: CurrentUser) -> list[AdminAccountOut]:
    accounts = await _run(lambda s: s.list_accounts(user))
    return [
        AdminAccountOut(
            id=a.summary.id,
            email=a.summary.email,
            name=a.summary.name,
            created_at=a.summary.created_at,
            email_verified=a.summary.email_verified,
            last_login_at=a.summary.last_login_at,
            two_factor_enabled=a.summary.two_factor_enabled,
            suspended_at=a.summary.suspended_at,
            is_admin=a.is_admin,
        )
        for a in accounts
    ]


@router.post("/accounts/{user_id}/suspend", status_code=204)
async def suspend_account(user_id: uuid.UUID, user: CurrentUser) -> None:
    await _run(lambda s: s.suspend(user, user_id))


@router.post("/accounts/{user_id}/reactivate", status_code=204)
async def reactivate_account(user_id: uuid.UUID, user: CurrentUser) -> None:
    await _run(lambda s: s.reactivate(user, user_id))


@router.delete("/accounts/{user_id}", status_code=204)
async def delete_account(
    user_id: uuid.UUID, payload: AdminAccountDeleteIn, user: CurrentUser
) -> None:
    cancelled = await _run(
        lambda s: s.delete(user, user_id, email_confirmation=payload.email_confirmation)
    )
    # After the commit, as for a self-service erasure: a failing mail server must not undo it.
    for booking in cancelled:
        await _notify_cancellation(booking)
