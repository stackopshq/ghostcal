"""Prometheus metrics.

Self-hosted and pull-based: the app exposes ``/metrics``, a scraper comes and reads it, and
nothing leaves the server on its own. That fits a product whose promise is that the operator holds
their own data — no vendor, no DSN, no egress.

**Labels are route templates, never request paths.** This is a correctness *and* a privacy rule.
GhostCal's URLs carry organization slugs, event slugs, invitation tokens and booking-management
tokens; labelling by raw path would write those into a metrics store — a place nobody thinks of as
holding secrets, that is often less protected than the database, and that is frequently shipped to
a third party. It would also blow up cardinality, one time series per booking, until the scraper
falls over. `/v1/bookings/manage/{token}` is one series; the token never appears.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry()

# Buckets tuned to this app: availability computation and the booking write are the slow paths,
# and everything else should sit in the low tens of milliseconds.
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

http_requests = Counter(
    "ghostcal_http_requests_total",
    "HTTP requests by route template, method and status.",
    ("method", "route", "status"),
    registry=REGISTRY,
)

http_latency = Histogram(
    "ghostcal_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ("method", "route"),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)

# Unhandled exceptions, separate from 5xx: a handled 503 from /readyz is expected operationally,
# a crash is not, and conflating them hides the one that means someone should look.
unhandled_exceptions = Counter(
    "ghostcal_unhandled_exceptions_total",
    "Requests that ended in an unhandled exception, by route template.",
    ("route",),
    registry=REGISTRY,
)

celery_tasks = Counter(
    "ghostcal_celery_tasks_total",
    "Celery task outcomes by task name.",
    ("task", "outcome"),
    registry=REGISTRY,
)

celery_duration = Histogram(
    "ghostcal_celery_task_duration_seconds",
    "Celery task duration by task name.",
    ("task",),
    buckets=(0.1, 0.5, 1.0, 5.0, 15.0, 60.0, 300.0),
    registry=REGISTRY,
)


def route_template(scope: MutableMapping[str, Any]) -> str:
    """The matched route's path template, or a constant for unmatched requests.

    Unmatched requests must collapse to one label. Reporting their real path would let anyone
    create unbounded time series by requesting random URLs — a metrics-store denial of service
    from an unauthenticated endpoint.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "<unmatched>"
