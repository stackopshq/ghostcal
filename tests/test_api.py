"""Smoke test for the FastAPI app wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ghostcal import __version__
from ghostcal.presentation.api import app


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
