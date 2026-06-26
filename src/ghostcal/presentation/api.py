"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from ghostcal import __version__
from ghostcal.presentation.routes import router as scheduling_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="GhostCal",
        version=__version__,
        description="Fast, correct scheduling.",
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness probe — process is up. No dependency checks (see /readyz later)."""
        return {"status": "ok", "version": __version__}

    app.include_router(scheduling_router)
    return app


app = create_app()
