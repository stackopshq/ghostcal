"""Celery tasks. Periodic CalDAV busy-sync runs here (the worker; see celery_app beat schedule)."""

from __future__ import annotations

import asyncio
import logging

from ghostcal.application.calendars import NotConnected, sync_calendar
from ghostcal.application.ports.calendar import CalendarError
from ghostcal.application.ports.clock import SystemClock
from ghostcal.celery_app import celery_app
from ghostcal.config import get_settings
from ghostcal.infrastructure.calendars import CaldavCalendarClient
from ghostcal.infrastructure.db.caldav_repository import SqlCaldavConnectionRepository
from ghostcal.infrastructure.db.membership import active_caldav_connections
from ghostcal.infrastructure.db.session import db_session, org_session, reset_engine
from ghostcal.infrastructure.security.encryption import SecretBox

logger = logging.getLogger("ghostcal.tasks")

_settings = get_settings()
_cipher = SecretBox(_settings.token_encryption_key.get_secret_value())
_client = CaldavCalendarClient()
_clock = SystemClock()


@celery_app.task(name="ghostcal.sync_all_calendars")  # type: ignore[untyped-decorator]
def sync_all_calendars() -> int:
    """Sync every active CalDAV connection. Returns how many synced successfully."""
    return asyncio.run(_sync_all())


async def _sync_all() -> int:
    synced = 0
    try:
        async with db_session() as session:
            connections = await active_caldav_connections(session)

        for organization_id, user_id in connections:
            try:
                async with org_session(organization_id) as session:
                    repo = SqlCaldavConnectionRepository(session, organization_id)
                    await sync_calendar(repo, _cipher, _client, _clock, user_id=user_id)
                synced += 1
            except CalendarError, NotConnected:
                logger.warning("calendar sync failed for org=%s user=%s", organization_id, user_id)
            except Exception:
                logger.exception("error syncing org=%s user=%s", organization_id, user_id)

        logger.info("calendar sync complete: %d/%d ok", synced, len(connections))
    finally:
        # The next task invocation runs on a fresh event loop; drop the engine bound to this one.
        await reset_engine()
    return synced
