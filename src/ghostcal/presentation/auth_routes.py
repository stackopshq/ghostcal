"""Authentication endpoints (email/password) and the ``current_user`` dependency."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ghostcal.application.audit import Action, AuditLog
from ghostcal.application.auth import (
    AuthConfig,
    AuthenticatedUser,
    AuthService,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidToken,
    OidcIdentityRefused,
    TokenPair,
    ZkKeyMaterial,
    ZkKeysAlreadySet,
    ZkRewrap,
)
from ghostcal.application.passwords import PasswordRejected
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.ports.email import EmailSender
from ghostcal.application.two_factor import (
    TwoFactorAlreadyEnabled,
    TwoFactorInvalid,
    TwoFactorLocked,
    TwoFactorNotEnrolled,
    TwoFactorRequired,
    TwoFactorService,
)
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.audit_repository import SqlAuditSink
from ghostcal.infrastructure.db.auth_repository import SqlAuthRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.db.two_factor_repository import SqlTwoFactorRepository
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.email.outbox import DeferredEmailSender
from ghostcal.infrastructure.ratelimit import rate_limit
from ghostcal.infrastructure.security.hibp import HibpBreachedPasswordChecker
from ghostcal.infrastructure.security.oidc import OIDCNotConfigured, oidc_client
from ghostcal.infrastructure.security.passwords import Argon2PasswordHasher
from ghostcal.infrastructure.security.tokens import JwtAccessTokenCodec
from ghostcal.infrastructure.security.totp import PyotpEngine
from ghostcal.infrastructure.tasks import enqueue_email
from ghostcal.presentation.schemas import (
    ForgotPasswordIn,
    LoginIn,
    RecoveryCodesOut,
    RefreshIn,
    RegisteredOut,
    RegisterIn,
    ResendVerificationIn,
    ResetPasswordIn,
    TokenOut,
    TwoFactorCodeIn,
    TwoFactorDisableIn,
    TwoFactorSetupIn,
    TwoFactorSetupOut,
    TwoFactorStatusOut,
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
_totp_engine = PyotpEngine()
_breach_checker = HibpBreachedPasswordChecker(enabled=_settings.password_breach_check_enabled)
_config = AuthConfig(
    access_ttl=timedelta(seconds=_settings.access_token_ttl_seconds),
    refresh_ttl=timedelta(seconds=_settings.refresh_token_ttl_seconds),
    email_verification_ttl=timedelta(seconds=_settings.email_verification_ttl_seconds),
    password_reset_ttl=timedelta(seconds=_settings.password_reset_ttl_seconds),
    frontend_base_url=_settings.frontend_base_url,
)


def _token_out(tokens: TokenPair) -> TokenOut:
    return TokenOut(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


def _service(session: object, mailer: EmailSender | None = None) -> AuthService:
    """Build the service for one request.

    `mailer` defaults to the direct sender because most routes here send nothing at all. A route
    that *does* send passes a `DeferredEmailSender` and drains it after its transaction commits --
    which is the whole of the fix for the 500s of 2026-09-25. The default is the old synchronous
    sender rather than a second outbox on purpose: if a future route sends and forgets to drain,
    it sends the slow way, which is visible. An undrained outbox would drop the mail in silence.
    """
    return AuthService(
        SqlAuthRepository(session),  # type: ignore[arg-type]
        _hasher,
        _codec,
        mailer or _mailer,
        _clock,
        _config,
        _two_factor(session),
        _breach_checker,
    )


def _audit(session: object) -> AuditLog:
    """Le journal de compte : `organization_id` reste nul, le second facteur n'appartient
    à aucune organisation."""
    return AuditLog(SqlAuditSink(session))  # type: ignore[arg-type]


def _two_factor(session: object) -> TwoFactorService:
    return TwoFactorService(
        SqlTwoFactorRepository(session),  # type: ignore[arg-type]
        _totp_engine,
        _clock,
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
async def auth_config() -> dict[str, bool | str | None]:
    """Public capabilities the frontend needs at load time.

    Auth first -- whether to show the SSO button -- and now the sibling app's
    address, which belongs here for the same reason: a per-deployment fact the
    browser cannot know, answered at runtime.

    It emphatically cannot be a NEXT_PUBLIC_ variable. Next inlines those at
    BUILD time, so one published image would carry one deployment's URLs in its
    bundle. Measured 2026-08-16: the "email these guests" button opened
    `http://localhost:3002` on the user's own machine, and setting the variable
    on the host changed nothing, because the bundle had already been written.
    """
    return {
        "oidc_enabled": _settings.oidc_enabled,
        "ghostmail_url": _settings.ghostmail_url,
        "privacy_url": _settings.privacy_url,
    }


@router.post("/register", response_model=RegisteredOut, status_code=201, dependencies=_AUTH_RL)
async def register(payload: RegisterIn) -> RegisteredOut:
    zk_keys = ZkKeyMaterial(
        public_key=payload.zk_keys.public_key,
        wrapped_private_key=payload.zk_keys.wrapped_private_key,
        wrap_salt=payload.zk_keys.wrap_salt,
        recovery_wrapped_private_key=payload.zk_keys.recovery_wrapped_private_key,
        recovery_salt=payload.zk_keys.recovery_salt,
    )
    # The verification token is written inside the transaction below; the email that carries it
    # leaves this process afterwards, through the worker. Buffering it here is what keeps the two
    # apart -- see infrastructure/email/outbox.py for the 500s that taught us the difference.
    outbox = DeferredEmailSender(enqueue_email)
    async with db_session() as session:
        try:
            user_id = await _service(session, outbox).register(
                email=payload.email,
                name=payload.name,
                password=payload.password,
                zk_keys=zk_keys,
            )
        except PasswordRejected as exc:
            # 422, not 400: this is the request body failing a rule, same class as the Pydantic
            # length check that runs just before it. The message is written to be shown as-is.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except EmailAlreadyRegistered as exc:
            raise HTTPException(status_code=409, detail="email already registered") from exc
    # Committed: the account and its verification row exist. Only now may a worker be told, and
    # only now can it read what it will be asked to mail about. `hand_off` never raises, so an
    # unreachable Redis costs this user an email and not an account.
    outbox.hand_off()
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


@router.post("/resend-verification", status_code=202, dependencies=_AUTH_RL)
async def resend_verification(payload: ResendVerificationIn) -> None:
    """Renvoie le courriel de vérification. Toujours 202, adresse connue ou non.

    C'est la SORTIE d'un cul-de-sac : un compte dont le courriel de vérification s'est perdu
    ne pouvait plus ni se connecter (403), ni se réinscrire (409), ni demander un nouveau mot
    de passe — cette dernière route ne s'adresse volontairement pas aux adresses non vérifiées.
    Trois portes fermées, aucune réparable sans accès à la base.

    Le 202 est inconditionnel pour la même raison que sur `forgot-password` : répondre
    différemment pour une adresse connue et une inconnue en ferait un oracle d'énumération, et
    l'appelant n'est pas authentifié. Voir `AuthService.resend_verification`.
    """
    outbox = DeferredEmailSender(enqueue_email)
    async with db_session() as session:
        await _service(session, outbox).resend_verification(email=payload.email)
    outbox.hand_off()


@router.post("/forgot-password", status_code=202, dependencies=_AUTH_RL)
async def forgot_password(payload: ForgotPasswordIn) -> None:
    """Start a password reset. Always 202, whether or not the address is known.

    Answering differently for a known and an unknown address would turn this into an
    account-enumeration oracle, and the caller is unauthenticated.
    """
    outbox = DeferredEmailSender(enqueue_email)
    async with db_session() as session:
        await _service(session, outbox).request_password_reset(email=payload.email)
    # Same two-step as `register`, and here it is what makes the docstring above true. Sending
    # inside the transaction meant a provider refusal answered 500 for an address that exists and
    # is verified, and 202 for one that does not -- an enumeration oracle built out of an outage.
    outbox.hand_off()


@router.get(
    "/reset-password/{token}/zk-keys", response_model=list[ZkKeysOut], dependencies=_AUTH_RL
)
async def reset_password_zk_keys(token: str) -> list[ZkKeysOut]:
    """The key envelopes for a live reset token, so the browser can open them with the phrase.

    Unauthenticated by necessity: the whole point is that the caller cannot log in. Safe because
    every envelope returned is sealed under the recovery phrase — 24 random bytes, 192 bits, behind
    Argon2id — so the link alone yields ciphertext.

    A read, not a spend: a wrong recovery phrase must not burn the link.
    """
    async with db_session() as session:
        try:
            bundles = await _service(session).zk_keys_for_reset(token=token)
        except InvalidToken as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.post("/reset-password", status_code=204, dependencies=_AUTH_RL)
async def reset_password(payload: ResetPasswordIn) -> None:
    """Finish a reset: the new password and the re-wrapped envelopes, together."""
    async with db_session() as session:
        try:
            await _service(session).reset_password(
                token=payload.token,
                new_password=payload.new_password,
                envelopes=[
                    ZkRewrap(
                        organization_id=e.organization_id,
                        wrapped_private_key=e.wrapped_private_key,
                        wrap_salt=e.wrap_salt,
                    )
                    for e in payload.envelopes
                ],
            )
        except PasswordRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except InvalidToken as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def email_is_vouched_for(userinfo: dict[str, object], issuer: str) -> bool:
    """Whether the provider has asserted that the caller owns this address.

    The email is treated downstream as proof of who this is — it links an SSO login to an existing
    account, and `accept_organization_invitation` accepts it as ownership of an invited address. So
    an address the provider has not vouched for is worth nothing here, and an **absent claim counts
    as unverified**: a provider that omits it has not made the assertion.

    Some providers never make it while guaranteeing the identity another way. Cloudflare Access is
    one — its discovery advertises no `claims_supported`, yet the identity comes from Google
    Workspace and an Access policy decides who may even reach the consent screen. Measured on
    2026-08-13: no first SSO login could succeed, for anyone, and the refusal was indistinguishable
    from OIDC being deliberately off.

    `oidc_trust_issuer_email` moves the proof from the claim to the issuer, and is scoped to
    `oidc_issuer` on purpose: an identity arriving with some other `iss` inherits none of that
    trust, so a swapped or misconfigured provider cannot walk in on it.
    """
    if userinfo.get("email_verified") is True:
        return True
    if _settings.oidc_trust_issuer_email and issuer and issuer == str(_settings.oidc_issuer or ""):
        logger.info("OIDC email accepted on issuer trust (provider emits no email_verified)")
        return True
    return False


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
    email_verified = email_is_vouched_for(userinfo, issuer)
    try:
        async with db_session() as session:
            tokens = await _service(session).authenticate_oidc(
                provider="oidc",
                issuer=issuer,
                subject=str(subject),
                email=str(email),
                name=str(userinfo.get("name") or ""),
                email_verified=email_verified,
            )
    except OidcIdentityRefused:
        # Unverified address, or an unverified local account already holds it. Both are refusals
        # to link, and the redirect says no more than that: distinguishing them here would tell a
        # stranger whether an account exists on an address they do not control.
        logger.warning("OIDC identity refused for a %s reason", "linking/verification")
        return RedirectResponse(f"{_settings.frontend_base_url}/login?sso_error=1")

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
    """Connexion. Si le compte a un second facteur, un premier appel sans code le réclame.

    Le corps de la réponse 401 reprend la forme de GhostPass — `mfa_required`,
    `mfa_type` — pour qu'un client de la suite reconnaisse la demande au même
    endroit, sous le même nom, dans les deux applications.
    """
    async with db_session() as session:
        try:
            tokens = await _service(session).login(
                email=payload.email, password=payload.password, totp_code=payload.totp_code
            )
        except InvalidCredentials as exc:
            raise HTTPException(status_code=401, detail="invalid email or password") from exc
        except EmailNotVerified as exc:
            raise HTTPException(status_code=403, detail="email not verified") from exc
        except TwoFactorLocked as exc:
            # 429 et non 401 : ce n'est pas « mauvais code », c'est « trop
            # d'essais ». Les confondre ferait tourner un client légitime en
            # boucle sur une saisie qui ne peut pas aboutir avant l'échéance.
            raise HTTPException(
                status_code=429,
                detail={
                    "detail": "too many two-factor attempts",
                    "mfa_required": True,
                    "mfa_type": "totp",
                    "locked_until": exc.until.isoformat(),
                },
            ) from exc
        except TwoFactorRequired as exc:
            raise HTTPException(
                status_code=401,
                detail={
                    "detail": "two-factor code required",
                    "mfa_required": True,
                    "mfa_type": "totp",
                },
            ) from exc
        except TwoFactorInvalid as exc:
            # Même message pour un code faux et pour un code rejoué : distinguer
            # les deux dirait à qui vient de capter un code qu'il a bien capté
            # un code.
            raise HTTPException(
                status_code=401,
                detail={
                    "detail": "invalid two-factor code",
                    "mfa_required": True,
                    "mfa_type": "totp",
                },
            ) from exc
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


# ---------------------------------------------------------------------------
# Second facteur (TOTP)
#
# Le chemin et le vocabulaire reprennent ceux de GhostPass (`/api/mfa`,
# `setup` / `activate` / `disable`) : la même suite, le même utilisateur, et
# rien à réapprendre en passant d'une application à l'autre. Ce qui s'y ajoute
# — les codes de récupération — est ce qui manque à GhostPass, pas une
# divergence de plus.
# ---------------------------------------------------------------------------


def _mfa_invalid() -> HTTPException:
    return HTTPException(status_code=401, detail="invalid two-factor code")


def _mfa_locked(exc: TwoFactorLocked) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={"detail": "too many two-factor attempts", "locked_until": exc.until.isoformat()},
    )


@router.get("/mfa", response_model=TwoFactorStatusOut)
async def mfa_status(user: CurrentUser) -> TwoFactorStatusOut:
    """L'état du second facteur.

    Sans cette question, un client ne peut pas distinguer « activer » de
    « désactiver », et proposer « activer » à quelqu'un qui l'a déjà remettrait
    son secret à zéro sans prévenir. `recovery_codes_remaining` est là pour que
    l'interface puisse alerter avant que la réserve soit vide — le moment où
    l'utilisateur se croit protégé et n'a plus de porte de sortie.
    """
    async with db_session() as session:
        status = await _two_factor(session).status(user.id)
    return TwoFactorStatusOut(
        enabled=status.enabled,
        pending=status.pending,
        recovery_codes_remaining=status.recovery_codes_remaining,
    )


@router.post("/mfa/setup", response_model=TwoFactorSetupOut, dependencies=_AUTH_RL)
async def mfa_setup(payload: TwoFactorSetupIn, user: CurrentUser) -> TwoFactorSetupOut:
    """Démarre l'enrôlement : rend le secret et l'URI du QR code.

    Le mot de passe est redemandé alors que la session est déjà ouverte, parce
    que l'opération remet le secret à zéro : une session laissée ouverte sur un
    poste partagé ne doit pas suffire à déplacer le second facteur d'un compte
    vers un autre téléphone.

    Rien n'est protégé à ce stade — la ligne écrite ici ne garde aucune porte
    tant que `/mfa/activate` n'a pas reçu un premier code juste.
    """
    async with db_session() as session:
        if not await _service(session).verify_password(user.id, payload.password):
            raise HTTPException(status_code=401, detail="invalid password")
        try:
            enrolment = await _two_factor(session).begin_enrolment(user.id, account=user.email)
        except TwoFactorAlreadyEnabled as exc:
            raise HTTPException(status_code=409, detail="two-factor is already enabled") from exc
    return TwoFactorSetupOut(secret=enrolment.secret, otpauth_uri=enrolment.otpauth_uri)


@router.post("/mfa/activate", response_model=RecoveryCodesOut, dependencies=_AUTH_RL)
async def mfa_activate(payload: TwoFactorCodeIn, user: CurrentUser) -> RecoveryCodesOut:
    """Active le second facteur contre un premier code, et rend les codes de récupération.

    C'est le seul moment où ils sont lisibles : seules leurs empreintes sont
    gardées, donc ni le support ni nous ne pourrons les réafficher.
    """
    async with db_session() as session:
        try:
            codes = await _two_factor(session).activate(user.id, code=payload.code)
        except TwoFactorNotEnrolled as exc:
            raise HTTPException(status_code=409, detail="no two-factor setup in progress") from exc
        except TwoFactorAlreadyEnabled as exc:
            raise HTTPException(status_code=409, detail="two-factor is already enabled") from exc
        except TwoFactorInvalid as exc:
            raise _mfa_invalid() from exc
        await _audit(session).record(Action.MFA_ENABLED, actor_user_id=user.id, target=str(user.id))
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/mfa/disable", status_code=204, dependencies=_AUTH_RL)
async def mfa_disable(payload: TwoFactorDisableIn, user: CurrentUser) -> None:
    """Retire le second facteur. Exige le mot de passe ET un code encore valide."""
    async with db_session() as session:
        if not await _service(session).verify_password(user.id, payload.password):
            raise HTTPException(status_code=401, detail="invalid password")
        try:
            await _two_factor(session).disable(user.id, code=payload.code)
        except TwoFactorNotEnrolled as exc:
            raise HTTPException(status_code=409, detail="two-factor is not enabled") from exc
        except TwoFactorLocked as exc:
            raise _mfa_locked(exc) from exc
        except TwoFactorInvalid as exc:
            raise _mfa_invalid() from exc
        await _audit(session).record(
            Action.MFA_DISABLED, actor_user_id=user.id, target=str(user.id)
        )


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesOut, dependencies=_AUTH_RL)
async def mfa_regenerate_recovery_codes(
    payload: TwoFactorDisableIn, user: CurrentUser
) -> RecoveryCodesOut:
    """Refait la réserve de codes de récupération. Les anciens cessent de valoir aussitôt."""
    async with db_session() as session:
        if not await _service(session).verify_password(user.id, payload.password):
            raise HTTPException(status_code=401, detail="invalid password")
        try:
            codes = await _two_factor(session).regenerate_recovery_codes(user.id, code=payload.code)
        except TwoFactorNotEnrolled as exc:
            raise HTTPException(status_code=409, detail="two-factor is not enabled") from exc
        except TwoFactorLocked as exc:
            raise _mfa_locked(exc) from exc
        except TwoFactorInvalid as exc:
            raise _mfa_invalid() from exc
        await _audit(session).record(
            Action.MFA_RECOVERY_CODES_REGENERATED, actor_user_id=user.id, target=str(user.id)
        )
    return RecoveryCodesOut(recovery_codes=codes)
