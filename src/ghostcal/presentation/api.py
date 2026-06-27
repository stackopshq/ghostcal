"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text

from ghostcal import __version__
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.session import get_engine
from ghostcal.presentation.auth_routes import router as auth_router
from ghostcal.presentation.dashboard_routes import router as dashboard_router
from ghostcal.presentation.routes import router as scheduling_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="GhostCal",
        version=__version__,
        description="Fast, correct scheduling.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_allow_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
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
    app.include_router(dashboard_router)
    app.include_router(scheduling_router)
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
