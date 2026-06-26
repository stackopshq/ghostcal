"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from ghostcal import __version__


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

    return app


app = create_app()
