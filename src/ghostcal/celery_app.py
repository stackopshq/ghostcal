"""Celery application.

Background work: calendar delta-sync, OAuth token refresh, reminder workflows, reconciliation.
Workers are synchronous; async calendar/email adapters are invoked via ``asgiref.async_to_sync``
inside tasks. Tasks are autodiscovered from ``ghostcal.infrastructure.tasks`` as it grows.
"""

from __future__ import annotations

from celery import Celery

from ghostcal.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    redis_url = str(settings.redis_url)
    app = Celery("ghostcal", broker=redis_url, backend=redis_url)
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "caldav-busy-sync": {
                "task": "ghostcal.sync_all_calendars",
                "schedule": float(settings.caldav_sync_interval_seconds),
            },
            "booking-reminders": {
                "task": "ghostcal.send_due_reminders",
                "schedule": float(settings.reminder_scan_interval_seconds),
            },
        },
    )
    app.autodiscover_tasks(["ghostcal.infrastructure"])
    return app


celery_app = create_celery()
