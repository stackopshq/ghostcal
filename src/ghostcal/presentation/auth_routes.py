"""Authentication endpoints (email/password) and the ``current_user`` dependency."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ghostcal.application.auth import (
    AuthConfig,
    AuthenticatedUser,
    AuthService,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidToken,
    TokenPair,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec
from ghostcal.presentation.schemas import (
    LoginIn,
    RefreshIn,
    RegisteredOut,
    RegisterIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

# Stateless collaborators, built once from settings.
_settings = get_settings()
_hasher = Argon2PasswordHasher()
_codec = JwtAccessTokenCodec(
    _settings.secret_key.get_secret_value(),
    timedelta(seconds=_settings.access_token_ttl_seconds),
)
_mailer = build_email_sender(_settings)
_clock = SystemClock()
_config = AuthConfig(
    access_ttl=timedelta(seconds=_settings.access_token_ttl_seconds),
    refresh_ttl=timedelta(seconds=_settings.refresh_token_ttl_seconds),
    email_verification_ttl=timedelta(seconds=_settings.email_verification_ttl_seconds),
    frontend_base_url=_settings.frontend_base_url,
)


def _token_out(tokens: TokenPair) -> TokenOut:
    return TokenOut(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


def _service(session: object) -> AuthService:
    return AuthService(
        SqlAuthRepository(session),  # type: ignore[arg-type]
        _hasher,
        _codec,
        _mailer,
        _clock,
        _config,
    )


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    async with db_session() as session:
        try:
            return await _service(session).current_user(access_token=credentials.credentials)
        except InvalidToken as exc:
            raise HTTPException(status_code=401, detail="invalid token") from exc


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]


@router.post("/register", response_model=RegisteredOut, status_code=201)
async def register(payload: RegisterIn) -> RegisteredOut:
    async with db_session() as session:
        try:
            user_id = await _service(session).register(
                email=payload.email, name=payload.name, password=payload.password
            )
        except EmailAlreadyRegistered as exc:
            raise HTTPException(status_code=409, detail="email already registered") from exc
    return RegisteredOut(user_id=user_id)


@router.post("/verify-email", status_code=204)
async def verify_email(payload: VerifyEmailIn) -> None:
    async with db_session() as session:
        try:
            await _service(session).verify_email(token=payload.token)
        except InvalidToken as exc:
            raise HTTPException(status_code=400, detail="invalid or expired token") from exc


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn) -> TokenOut:
    async with db_session() as session:
        try:
            tokens = await _service(session).login(email=payload.email, password=payload.password)
        except InvalidCredentials as exc:
            raise HTTPException(status_code=401, detail="invalid email or password") from exc
        except EmailNotVerified as exc:
            raise HTTPException(status_code=403, detail="email not verified") from exc
    return _token_out(tokens)


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn) -> TokenOut:
    async with db_session() as session:
        try:
            tokens = await _service(session).refresh(refresh_token=payload.refresh_token)
        except InvalidToken as exc:
            raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    return _token_out(tokens)


@router.post("/logout", status_code=204)
async def logout(payload: RefreshIn) -> None:
    async with db_session() as session:
        await _service(session).logout(refresh_token=payload.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, email_verified=user.email_verified)
