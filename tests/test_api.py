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
    base = "/v1/orgs/{org_slug}/event-types/{event_slug}"
    assert f"{base}/availability" in paths
    assert "get" in paths[f"{base}/availability"]
    assert f"{base}/bookings" in paths
    assert "post" in paths[f"{base}/bookings"]


def test_calendar_subscription_routes_are_mounted() -> None:
    # Subscriptions live under /v1/me/calendar/* like the rest of the calendar API — the frontend
    # client calls these exact paths, so a prefix drift here is a silent 404 in the browser.
    paths = app.openapi()["paths"]
    assert "get" in paths["/v1/me/calendar/subscriptions"]
    assert "post" in paths["/v1/me/calendar/subscriptions"]
    assert "post" in paths["/v1/me/calendar/subscriptions/{subscription_id}/refresh"]
    assert "delete" in paths["/v1/me/calendar/subscriptions/{subscription_id}"]


def test_weather_routes_are_mounted() -> None:
    paths = app.openapi()["paths"]
    assert "get" in paths["/v1/me/weather"]
    assert "get" in paths["/v1/me/weather/geocode"]


def test_oidc_routes_are_mounted() -> None:
    paths = app.openapi()["paths"]
    assert "get" in paths["/v1/auth/oidc/login"]
    assert "get" in paths["/v1/auth/oidc/callback"]
    assert "get" in paths["/v1/auth/config"]
    assert "post" in paths["/v1/auth/zk-keys"]  # first-time SSO key setup


def test_oidc_routes_404_when_disabled() -> None:
    # OIDC is off by default; the routes must behave as if absent (no info leak, no 500).
    client = TestClient(app)
    assert client.get("/v1/auth/oidc/login", follow_redirects=False).status_code == 404
    # The field, not the whole body. Asserting the entire payload made this test fail the day an
    # unrelated capability joined it, which says nothing about OIDC being off.
    assert client.get("/v1/auth/config").json()["oidc_enabled"] is False
