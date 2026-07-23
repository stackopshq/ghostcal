"""User profile endpoints: read profile, update name/timezone, change password."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ghostcal.application.auth import AuthUserRecord, InvalidCredentials
from ghostcal.application.passwords import PasswordRejected
from ghostcal.application.profile import (
    InvalidTimezone,
    ProfileError,
    ProfileService,
    UnknownUser,
)
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.security.hibp import HibpBreachedPasswordChecker
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.presentation.auth_routes import CurrentUser
from ghostcal.presentation.schemas import PasswordChangeIn, ProfileOut, ProfileUpdateIn

router = APIRouter(prefix="/v1/me/profile", tags=["profile"])
_hasher = Argon2PasswordHasher()


_breach_checker = HibpBreachedPasswordChecker(enabled=get_settings().password_breach_check_enabled)


def _service(session: object) -> ProfileService:
    return ProfileService(SqlAuthRepository(session), _hasher, _breach_checker)  # type: ignore[arg-type]


def _out(record: AuthUserRecord) -> ProfileOut:
    return ProfileOut(
        id=record.id,
        email=record.email,
        name=record.name,
        timezone=record.timezone,
        email_verified=record.email_verified,
        avatar_url=record.avatar_url,
    )


@router.get("", response_model=ProfileOut)
async def get_profile(user: CurrentUser) -> ProfileOut:
    async with db_session() as session:
        return _out(await _service(session).get(user.id))


@router.put("", response_model=ProfileOut)
async def update_profile(payload: ProfileUpdateIn, user: CurrentUser) -> ProfileOut:
    async with db_session() as session:
        try:
            record = await _service(session).update(
                user.id,
                name=payload.name,
                timezone=payload.timezone,
                avatar_url=payload.avatar_url,
            )
        except InvalidTimezone as exc:
            raise HTTPException(status_code=422, detail="unknown timezone") from exc
        except (ProfileError, UnknownUser) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _out(record)


@router.post("/password", status_code=204)
async def change_password(payload: PasswordChangeIn, user: CurrentUser) -> None:
    async with db_session() as session:
        try:
            await _service(session).change_password(
                user.id,
                current_password=payload.current_password,
                new_password=payload.new_password,
            )
        except PasswordRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except InvalidCredentials as exc:
            raise HTTPException(status_code=403, detail="current password is incorrect") from exc
