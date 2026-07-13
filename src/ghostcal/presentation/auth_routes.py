"""Authentication endpoints (email/password) and the ``current_user`` dependency."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
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
    ZkKeyMaterial,
    ZkKeysAlreadySet,
)
from ghostcal.application.ports.clock import SystemClock
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.ratelimit import rate_limit
from ghostcal.infrastructure.security.oidc import OIDCNotConfigured, oidc_client
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
    ZkKeyMaterialIn,
    ZkKeysOut,
    ZkRewrapIn,
)

logger = logging.getLogger("ghostcal.auth")

router = APIRouter(prefix="/v1/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

# Stateless collaborators, built once from settings.
_settings = get_settings()
# Per-IP throttle on the auth surface (brute-force + Argon2 CPU-DoS guard).
_AUTH_RL = [Depends(rate_limit("auth", _settings.auth_rate_limit_per_minute))]
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


@router.get("/config")
async def auth_config() -> dict[str, bool]:
    """Public auth capabilities the frontend needs at load time (e.g. whether to show SSO)."""
    return {"oidc_enabled": _settings.oidc_enabled}


@router.post("/register", response_model=RegisteredOut, status_code=201, dependencies=_AUTH_RL)
async def register(payload: RegisterIn) -> RegisteredOut:
    zk_keys = ZkKeyMaterial(
        public_key=payload.zk_keys.public_key,
        wrapped_private_key=payload.zk_keys.wrapped_private_key,
        wrap_salt=payload.zk_keys.wrap_salt,
        recovery_wrapped_private_key=payload.zk_keys.recovery_wrapped_private_key,
        recovery_salt=payload.zk_keys.recovery_salt,
    )
    async with db_session() as session:
        try:
            user_id = await _service(session).register(
                email=payload.email,
                name=payload.name,
                password=payload.password,
                zk_keys=zk_keys,
            )
        except EmailAlreadyRegistered as exc:
            raise HTTPException(status_code=409, detail="email already registered") from exc
    return RegisteredOut(user_id=user_id)


@router.get("/zk-keys", response_model=list[ZkKeysOut])
async def zk_keys(user: CurrentUser) -> list[ZkKeysOut]:
    """Every org key the user holds — one row per (org, generation), newest first (ADR-0007).

    More than one generation per org after a rotation: records sealed under an older generation and
    not yet re-sealed still need it.
    """
    async with db_session() as session:
        bundles = await _service(session).get_zk_keys(user.id)
    return [
        ZkKeysOut(
            organization_id=b.organization_id,
            public_key=b.public_key,
            generation=b.generation,
            sealed_org_key=b.sealed_org_key,
            wrapped_private_key=b.wrapped_private_key,
            wrap_salt=b.wrap_salt,
            recovery_wrapped_private_key=b.recovery_wrapped_private_key,
            recovery_salt=b.recovery_salt,
        )
        for b in bundles
    ]


@router.post("/zk-keys", status_code=204, dependencies=_AUTH_RL)
async def setup_zk_keys(payload: ZkKeyMaterialIn, user: CurrentUser) -> None:
    """First-time zero-knowledge key setup — an SSO user choosing their encryption passphrase.
    Refuses to overwrite existing keys (409)."""
    material = ZkKeyMaterial(
        public_key=payload.public_key,
        wrapped_private_key=payload.wrapped_private_key,
        wrap_salt=payload.wrap_salt,
        recovery_wrapped_private_key=payload.recovery_wrapped_private_key,
        recovery_salt=payload.recovery_salt,
    )
    async with db_session() as session:
        try:
            await _service(session).setup_zk_keys(user.id, material)
        except ZkKeysAlreadySet as exc:
            raise HTTPException(status_code=409, detail="keys already set") from exc


@router.post("/zk-rewrap", status_code=204, dependencies=_AUTH_RL)
async def zk_rewrap(payload: ZkRewrapIn, user: CurrentUser) -> None:
    """Store an org key re-wrapped under a new password (called after a password change)."""
    async with db_session() as session:
        await _service(session).rewrap_zk_key(
            user.id,
            payload.organization_id,
            wrapped_private_key=payload.wrapped_private_key,
            wrap_salt=payload.wrap_salt,
        )


# --- SSO / OIDC (single provider; authentication only — the zk passphrase is separate) ---------


def _require_oidc_enabled() -> None:
    # When OIDC is off, the routes behave as if they don't exist.
    if not _settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="not found")


@router.get("/oidc/login")
async def oidc_login(request: Request) -> RedirectResponse:
    """Begin the OIDC flow: 302 to the provider's authorization endpoint (state/nonce/PKCE set)."""
    _require_oidc_enabled()
    redirect_uri = _settings.oidc_redirect_uri or str(request.url_for("oidc_callback"))
    try:
        response: RedirectResponse = await oidc_client().authorize_redirect(request, redirect_uri)
    except OIDCNotConfigured as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    return response


@router.get("/oidc/callback", name="oidc_callback")
async def oidc_callback(request: Request) -> RedirectResponse:
    """Provider redirect target: validate the ID token, resolve the user, hand tokens to the SPA."""
    _require_oidc_enabled()
    try:
        token = await oidc_client().authorize_access_token(request)
    except Exception:
        # Never leak IdP/library internals (nonce mismatch, etc.) — just fail the sign-in.
        logger.warning("OIDC token exchange failed", exc_info=True)
        return RedirectResponse(f"{_settings.frontend_base_url}/login?sso_error=1")

    userinfo = token.get("userinfo") or {}
    subject = userinfo.get("sub")
    email = userinfo.get("email")
    if not subject or not email:
        logger.warning("OIDC userinfo missing sub/email")
        return RedirectResponse(f"{_settings.frontend_base_url}/login?sso_error=1")

    issuer = str(_settings.oidc_issuer or userinfo.get("iss") or "")
    async with db_session() as session:
        tokens = await _service(session).authenticate_oidc(
            provider="oidc",
            issuer=issuer,
            subject=str(subject),
            email=str(email),
            name=str(userinfo.get("name") or ""),
        )
    # Tokens go in the URL fragment (never sent to a server, not in Referer); the SPA reads them and
    # immediately strips the fragment. This matches the app's existing localStorage token model.
    fragment = urlencode(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_in": tokens.expires_in,
        }
    )
    return RedirectResponse(f"{_settings.frontend_base_url}/auth/callback#{fragment}")


@router.post("/verify-email", status_code=204, dependencies=_AUTH_RL)
async def verify_email(payload: VerifyEmailIn) -> None:
    async with db_session() as session:
        try:
            await _service(session).verify_email(token=payload.token)
        except InvalidToken as exc:
            raise HTTPException(status_code=400, detail="invalid or expired token") from exc


@router.post("/login", response_model=TokenOut, dependencies=_AUTH_RL)
async def login(payload: LoginIn) -> TokenOut:
    async with db_session() as session:
        try:
            tokens = await _service(session).login(email=payload.email, password=payload.password)
        except InvalidCredentials as exc:
            raise HTTPException(status_code=401, detail="invalid email or password") from exc
        except EmailNotVerified as exc:
            raise HTTPException(status_code=403, detail="email not verified") from exc
    return _token_out(tokens)


@router.post("/refresh", response_model=TokenOut, dependencies=_AUTH_RL)
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
    # The access token carries identity but not whether a password exists, so this reads the record.
    # ``has_password`` is what lets the UI ask an SSO-only account to confirm a deletion with its
    # email address alone — it has no password, and offering the field would be nonsense.
    async with db_session() as session:
        record = await SqlAuthRepository(session).get_by_id(user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown user")
    return UserOut(
        id=record.id,
        email=record.email,
        name=record.name,
        email_verified=record.email_verified,
        has_password=record.password_hash is not None,
    )
