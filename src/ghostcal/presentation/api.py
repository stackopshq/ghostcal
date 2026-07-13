"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from ghostcal import __version__
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.session import get_engine
from ghostcal.infrastructure.logging import configure_logging, request_id_var
from ghostcal.presentation.account_routes import router as account_router
from ghostcal.presentation.auth_routes import router as auth_router
from ghostcal.presentation.calendar_routes import router as calendar_router
from ghostcal.presentation.dashboard_routes import router as dashboard_router
from ghostcal.presentation.event_invite_routes import router as event_invite_router
from ghostcal.presentation.export_routes import router as export_router
from ghostcal.presentation.invitations_routes import router as invitations_router
from ghostcal.presentation.keypair_routes import router as keypair_router
from ghostcal.presentation.manage_routes import router as manage_router
from ghostcal.presentation.org_routes import router as org_router
from ghostcal.presentation.poll_routes import router as poll_router
from ghostcal.presentation.portal_routes import router as portal_router
from ghostcal.presentation.profile_routes import router as profile_router
from ghostcal.presentation.public_poll_routes import router as public_poll_router
from ghostcal.presentation.push_routes import router as push_router
from ghostcal.presentation.reseal_routes import router as reseal_router
from ghostcal.presentation.routes import router as scheduling_router
from ghostcal.presentation.tasks_routes import router as tasks_router
from ghostcal.presentation.weather_routes import router as weather_router
from ghostcal.presentation.webhook_routes import router as webhook_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    access_logger = logging.getLogger("ghostcal.access")

    # Don't expose the interactive API docs / schema in production.
    _docs = (
        {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.is_production else {}
    )
    app = FastAPI(
        title="GhostCal",
        version=__version__,
        description="Fast, correct scheduling.",
        **_docs,  # type: ignore[arg-type]
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: object) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)  # type: ignore[operator]
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            access_logger.info(
                "%s %s -> %s (%sms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_allow_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    # Authlib stashes the OIDC state/nonce in a signed session cookie during the redirect handshake.
    # SameSite=Lax so it survives the top-level GET redirect back from the identity provider.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        same_site="lax",
        https_only=settings.is_production,
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness probe — the process is up. No dependency checks (see /readyz)."""
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", tags=["meta"])
    async def readyz() -> JSONResponse:
        """Readiness probe — verifies PostgreSQL and Redis are reachable."""
        checks = {"postgres": await _check_postgres(), "redis": await _check_redis()}
        ready = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "degraded", "checks": checks},
        )

    app.include_router(auth_router)
    app.include_router(profile_router)
    app.include_router(account_router)
    app.include_router(export_router)
    app.include_router(keypair_router)
    app.include_router(reseal_router)
    app.include_router(portal_router)
    app.include_router(push_router)
    app.include_router(org_router)
    app.include_router(invitations_router)
    app.include_router(poll_router)
    app.include_router(public_poll_router)
    app.include_router(webhook_router)
    app.include_router(dashboard_router)
    app.include_router(calendar_router)
    app.include_router(weather_router)
    app.include_router(tasks_router)
    app.include_router(event_invite_router)
    app.include_router(scheduling_router)
    app.include_router(manage_router)
    return app


async def _check_postgres() -> str:
    # Readiness checks must never raise — any failure means "not ready".
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return "error"
    return "ok"


async def _check_redis() -> str:
    client = redis_from_url(str(get_settings().redis_url))  # type: ignore[no-untyped-call]
    try:
        await client.ping()
    except Exception:
        return "error"
    finally:
        await client.aclose()
    return "ok"


app = create_app()
