"""What the metrics endpoint is allowed to contain (no DB).

Metrics stores are not built to hold secrets: they are often less protected than the database and
frequently shipped to a third party. GhostCal's URLs carry organization slugs, invitation tokens
and booking-management tokens, so labelling by request path would quietly file those there.

These tests pin the rule that prevents it, and the cardinality bound that comes with it.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from ghostcal.presentation.api import create_app

_SECRET_TOKEN = "tok-abcdef0123456789-secret"


def test_a_token_in_the_url_never_reaches_a_metric_label() -> None:
    with TestClient(create_app()) as client:
        # A real, tokenised route. It will 404 or 401 — irrelevant; what matters is what the
        # request leaves behind in the registry.
        client.get(f"/v1/bookings/manage/{_SECRET_TOKEN}")
        body = client.get("/metrics").text

    assert _SECRET_TOKEN not in body
    # The template is what should appear, so the series is still useful.
    assert "/v1/bookings/manage/{token}" in body


def test_a_token_in_the_url_never_reaches_the_access_log() -> None:
    """The same rule as above, for the other sink that sees every request.

    The rule was written for both — the comment above `route_template()` names
    booking-management tokens explicitly — but only the metrics half was pinned by a
    test, and the access log went on writing `request.url.path` verbatim. A token
    there is a live capability: `/v1/bookings/manage/{token}` cancels and reschedules
    on the token alone, so anyone who can read the log can act on the booking.

    `caplog` is deliberately not used: `configure_logging()` sets `propagate = False`
    on this logger, so the fixture's root handler never sees these records and every
    assertion below would pass against an empty list. The handler is attached to the
    logger itself instead, and the first assertion fails loudly if nothing was
    captured — an empty log must never read as a clean result.
    """
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    access_logger = logging.getLogger("ghostcal.access")
    handler = _Capture(level=logging.INFO)
    access_logger.addHandler(handler)
    try:
        with TestClient(create_app()) as client:
            client.get(f"/v1/bookings/manage/{_SECRET_TOKEN}")
    finally:
        access_logger.removeHandler(handler)

    lines = [r.getMessage() for r in records]
    assert lines, "the access log recorded nothing, so this test proves nothing"
    assert not any(_SECRET_TOKEN in line for line in lines)
    # The template still appears, so the log stays useful for reading traffic.
    assert any("/v1/bookings/manage/{token}" in line for line in lines)


def test_unmatched_paths_collapse_to_one_series() -> None:
    """Otherwise anyone can create unbounded time series by requesting random URLs."""
    with TestClient(create_app()) as client:
        for i in range(5):
            client.get(f"/definitely-not-a-route-{i}")
        body = client.get("/metrics").text

    assert "definitely-not-a-route" not in body
    assert "<unmatched>" in body


def test_the_endpoint_reports_request_counts_and_latency() -> None:
    with TestClient(create_app()) as client:
        client.get("/health")
        body = client.get("/metrics").text

    assert "ghostcal_http_requests_total" in body
    assert "ghostcal_http_request_duration_seconds" in body
    assert 'route="/health"' in body


def test_an_unhandled_exception_becomes_a_logged_500_with_a_request_id() -> None:
    """Previously the exception propagated past the middleware, so the access-log line never ran
    and 500s were the one class of request missing from the log entirely."""
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
        body = client.get("/metrics").text

    assert response.status_code == 500
    assert response.headers["X-Request-ID"]
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    # The message never leaks to the caller...
    assert "kaboom" not in response.text
    # ...but the failure is counted, so it is visible to whoever is watching.
    assert "ghostcal_unhandled_exceptions_total" in body
