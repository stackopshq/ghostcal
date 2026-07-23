"""Correlation IDs and metrics for Celery tasks.

Two gaps this closes.

**A task could not be traced back to the request that queued it.** The API stamps every request
with an ``X-Request-ID`` and logs under it, but nothing carried that across the queue — so a
webhook delivery, a reminder or a sync appeared in the logs as an unrelated event, and answering
"which booking caused this?" meant guessing from timestamps. The id now rides in the task's message
headers and is restored into the same ContextVar the API uses, so worker log lines carry it too.

**The worker had no metrics endpoint.** Counters incremented in a worker process are invisible to
the API's ``/metrics`` — a different process with a different registry. So the worker serves its
own, on its own port. Without this the Celery metrics would exist and be unscrapeable, which is
worse than not having them.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from celery.signals import (
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
    worker_ready,
)
from prometheus_client import start_http_server

from ghostcal.config import get_settings
from ghostcal.infrastructure.logging import request_id_var
from ghostcal.infrastructure.metrics import REGISTRY, celery_duration, celery_tasks

logger = logging.getLogger("ghostcal.celery")

_HEADER = "ghostcal_request_id"
_started: dict[str, float] = {}


@before_task_publish.connect  # type: ignore[untyped-decorator]
def _carry_request_id(headers: dict[str, Any] | None = None, **_: object) -> None:
    """Stamp the queueing request's id onto the message, if there is one."""
    rid = request_id_var.get()
    if rid and headers is not None:
        headers[_HEADER] = rid


@task_prerun.connect  # type: ignore[untyped-decorator]
def _adopt_request_id(task_id: str | None = None, task: Any = None, **_: object) -> None:
    request = getattr(task, "request", None)
    rid = getattr(request, _HEADER, None) if request is not None else None
    # Fall back to the task id: a scheduled task has no originating request, and a log line with
    # some correlation key beats one with none.
    request_id_var.set(rid or (task_id or ""))
    if task_id:
        _started[task_id] = time.perf_counter()


@task_postrun.connect  # type: ignore[untyped-decorator]
def _record_completion(
    task_id: str | None = None, task: Any = None, state: str | None = None, **_: object
) -> None:
    name = getattr(task, "name", "unknown")
    started = _started.pop(task_id, None) if task_id else None
    if started is not None:
        celery_duration.labels(task=name).observe(time.perf_counter() - started)
    celery_tasks.labels(task=name, outcome=(state or "unknown").lower()).inc()
    request_id_var.set("")


@task_failure.connect  # type: ignore[untyped-decorator]
def _log_failure(task_id: str | None = None, sender: Any = None, **_: object) -> None:
    # Celery logs failures itself, but not under our correlation id and not as structured JSON.
    logger.exception("celery task failed: %s", getattr(sender, "name", "unknown"))


@worker_ready.connect  # type: ignore[untyped-decorator]
def _serve_metrics(**_: object) -> None:
    port = get_settings().metrics_port
    if port <= 0:
        return
    try:
        start_http_server(port, registry=REGISTRY)
        logger.info("worker metrics listening on :%s", port)
    except OSError:
        # Several workers on one host would collide. Losing metrics must never stop a worker from
        # doing its job.
        logger.warning("could not bind worker metrics port %s (continuing)", port)
