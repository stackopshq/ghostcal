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


def test_scheduling_routes_are_mounted() -> None:
    paths = app.openapi()["paths"]
    base = "/v1/orgs/{organization_id}/event-types/{event_type_id}"
    assert f"{base}/availability" in paths
    assert "get" in paths[f"{base}/availability"]
    assert f"{base}/bookings" in paths
    assert "post" in paths[f"{base}/bookings"]
