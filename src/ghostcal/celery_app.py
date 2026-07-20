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
        # Nothing here should run for minutes. `sync_all_calendars` walks every connection in one
        # task, so a handful of unresponsive CalDAV servers at 15s apiece could otherwise stall a
        # worker past the next beat tick and quietly stop all scheduled work. The soft limit
        # raises an exception the task can unwind from; the hard limit kills it shortly after.
        task_soft_time_limit=settings.task_soft_time_limit_seconds,
        task_time_limit=settings.task_time_limit_seconds,
        # A worker that starts before Redis is up should wait for it rather than exit — the
        # ordinary case on a cold `compose up`.
        broker_connection_retry_on_startup=True,
        # Cap what one worker takes at a time. With acks_late, a crash re-delivers everything
        # prefetched, and a long queue behind a dead worker is worse than a slightly idle one.
        worker_prefetch_multiplier=1,
        beat_schedule={
            "caldav-busy-sync": {
                "task": "ghostcal.sync_all_calendars",
                "schedule": float(settings.caldav_sync_interval_seconds),
            },
            "booking-reminders": {
                "task": "ghostcal.send_due_reminders",
                "schedule": float(settings.reminder_scan_interval_seconds),
            },
            "event-reminders": {
                "task": "ghostcal.send_due_event_reminders",
                "schedule": float(settings.reminder_scan_interval_seconds),
            },
            "task-reminders": {
                "task": "ghostcal.send_due_task_reminders",
                "schedule": float(settings.reminder_scan_interval_seconds),
            },
            "subscription-sync": {
                "task": "ghostcal.sync_all_subscriptions",
                "schedule": float(settings.subscription_sync_interval_seconds),
            },
            "retention-purge": {
                "task": "ghostcal.purge_expired_bookings",
                "schedule": float(settings.retention_purge_interval_seconds),
            },
        },
    )
    app.autodiscover_tasks(["ghostcal.infrastructure"])
    return app


celery_app = create_celery()
