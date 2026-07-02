"""Celery tasks. Periodic CalDAV busy-sync runs here (the worker; see celery_app beat schedule)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import timedelta

import httpx

from ghostcal.application.calendars import NotConnected, sync_calendar
from ghostcal.application.event_reminders import dispatch_event_reminders
from ghostcal.application.ports.calendar import CalendarError
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.reminders import DueReminder, dispatch_reminders
from ghostcal.application.subscriptions import FeedUnreachable, refresh_subscription
from ghostcal.application.task_reminders import dispatch_task_reminders
from ghostcal.application.webhooks import sign_payload
from ghostcal.celery_app import celery_app
from ghostcal.config import get_settings
from ghostcal.infrastructure.calendars import CaldavCalendarClient
from ghostcal.infrastructure.db.caldav_repository import SqlCaldavConnectionRepository
from ghostcal.infrastructure.db.event_reminders_repository import SqlEventReminderGateway
from ghostcal.infrastructure.db.membership import active_caldav_connections, active_subscriptions
from ghostcal.infrastructure.db.reminders_repository import SqlReminderGateway
from ghostcal.infrastructure.db.session import db_session, org_session, reset_engine
from ghostcal.infrastructure.db.subscriptions_repository import SqlSubscriptionRepository
from ghostcal.infrastructure.db.task_reminders_repository import SqlTaskReminderGateway
from ghostcal.infrastructure.db.webhooks_repository import SqlWebhookRepository
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.security.egress import BlockedOutboundURL, assert_public_url
from ghostcal.infrastructure.security.encryption import SecretBox
from ghostcal.infrastructure.security.tokens import BookingManagementCodec

logger = logging.getLogger("ghostcal.tasks")

_settings = get_settings()
_cipher = SecretBox(_settings.token_encryption_key.get_secret_value())
_client = CaldavCalendarClient()
_clock = SystemClock()
_mailer = build_email_sender(_settings)
_manage_codec = BookingManagementCodec(_settings.secret_key.get_secret_value())


def _manage_url(reminder: DueReminder) -> str:
    token = _manage_codec.encode(reminder.booking_id, reminder.organization_id)
    return f"{_settings.frontend_base_url}/manage/{token}"


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


@celery_app.task(name="ghostcal.send_due_reminders")  # type: ignore[untyped-decorator]
def send_due_reminders() -> int:
    """Send all due booking reminders. Returns how many were sent."""
    return asyncio.run(_send_due_reminders())


async def _send_due_reminders() -> int:
    offsets = tuple(_settings.reminder_offsets_minutes)
    try:
        async with db_session() as session:
            sent = await dispatch_reminders(
                SqlReminderGateway(session),
                _mailer,
                offsets=offsets,
                manage_url=_manage_url,
            )
        logger.info("reminders dispatched: %d", sent)
    finally:
        await reset_engine()
    return sent


@celery_app.task(name="ghostcal.send_due_event_reminders")  # type: ignore[untyped-decorator]
def send_due_event_reminders() -> int:
    """Send all due calendar-event reminders. Returns how many were sent."""
    return asyncio.run(_send_due_event_reminders())


async def _send_due_event_reminders() -> int:
    window = timedelta(seconds=_settings.reminder_scan_interval_seconds)
    try:
        async with db_session() as session:
            sent = await dispatch_event_reminders(
                SqlEventReminderGateway(session), _mailer, now=_clock.now(), scan_window=window
            )
        logger.info("event reminders dispatched: %d", sent)
    finally:
        await reset_engine()
    return sent


@celery_app.task(name="ghostcal.send_due_task_reminders")  # type: ignore[untyped-decorator]
def send_due_task_reminders() -> int:
    """Send all due task reminders. Returns how many were sent."""
    return asyncio.run(_send_due_task_reminders())


async def _send_due_task_reminders() -> int:
    try:
        async with db_session() as session:
            sent = await dispatch_task_reminders(SqlTaskReminderGateway(session), _mailer)
        logger.info("task reminders dispatched: %d", sent)
    finally:
        await reset_engine()
    return sent


@celery_app.task(name="ghostcal.sync_all_subscriptions")  # type: ignore[untyped-decorator]
def sync_all_subscriptions() -> int:
    """Refresh every active ICS subscription. Returns how many refreshed without error."""
    return asyncio.run(_sync_all_subscriptions())


async def _sync_all_subscriptions() -> int:
    refreshed = 0
    try:
        async with db_session() as session:
            subs = await active_subscriptions(session)
        for organization_id, subscription_id in subs:
            try:
                async with org_session(organization_id) as session:
                    await refresh_subscription(
                        SqlSubscriptionRepository(session, organization_id), subscription_id
                    )
                refreshed += 1
            except FeedUnreachable:
                logger.warning("subscription refresh failed for %s", subscription_id)
        logger.info("subscriptions refreshed: %d/%d ok", refreshed, len(subs))
    finally:
        await reset_engine()
    return refreshed


@celery_app.task(name="ghostcal.deliver_webhooks")  # type: ignore[untyped-decorator]
def deliver_webhooks(organization_id: str, event_type: str, payload: dict[str, object]) -> int:
    """POST a signed event payload to every active endpoint subscribed to it."""
    return asyncio.run(_deliver_webhooks(uuid.UUID(organization_id), event_type, payload))


async def _deliver_webhooks(
    organization_id: uuid.UUID, event_type: str, payload: dict[str, object]
) -> int:
    delivered = 0
    try:
        async with org_session(organization_id) as session:
            targets = await SqlWebhookRepository(session, organization_id).targets_for_event(
                event_type
            )
        if not targets:
            return 0
        body = json.dumps({"event": event_type, "data": payload}, default=str).encode()
        # follow_redirects=False (the default) so a 30x can't bounce us to an internal address.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as http:
            for target in targets:
                # Re-check at send time too: the URL was validated at creation, but DNS can rebind.
                try:
                    assert_public_url(target.url)
                except BlockedOutboundURL:
                    logger.warning("webhook target %s blocked by SSRF guard", target.url)
                    continue
                headers = {
                    "content-type": "application/json",
                    "user-agent": "GhostCal-Webhook/1.0",
                    "X-GhostCal-Event": event_type,
                    "X-GhostCal-Signature": f"sha256={sign_payload(target.secret, body)}",
                }
                try:
                    response = await http.post(target.url, content=body, headers=headers)
                    if response.status_code < 400:
                        delivered += 1
                    else:
                        logger.warning("webhook %s returned %s", target.url, response.status_code)
                except httpx.HTTPError:
                    logger.warning("webhook delivery to %s failed", target.url)
    finally:
        await reset_engine()
    return delivered


def emit_event(organization_id: uuid.UUID, event_type: str, payload: dict[str, object]) -> None:
    """Enqueue webhook delivery for an event. Best-effort: never fails the caller."""
    try:
        deliver_webhooks.delay(str(organization_id), event_type, payload)
    except Exception:
        logger.warning("could not enqueue webhook event %s", event_type)
