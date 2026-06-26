"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ghostcal import __version__
from ghostcal.config import get_settings
from ghostcal.presentation.auth_routes import router as auth_router
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
        """Liveness probe — process is up. No dependency checks (see /readyz later)."""
        return {"status": "ok", "version": __version__}

    app.include_router(auth_router)
    app.include_router(scheduling_router)
    return app


app = create_app()
