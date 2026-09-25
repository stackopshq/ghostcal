"""Celery tasks. Periodic CalDAV busy-sync runs here (the worker; see celery_app beat schedule)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from datetime import timedelta

import httpx

from ghostcal.application.calendars import NotConnected, sync_connection
from ghostcal.application.event_reminders import dispatch_event_reminders
from ghostcal.application.ports.calendar import CalendarError
from ghostcal.application.ports.clock import SystemClock
from ghostcal.application.ports.email import Attachment
from ghostcal.application.reminders import DueReminder, dispatch_reminders
from ghostcal.application.retention import PurgeResult, purge_one_organization
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
from ghostcal.infrastructure.db.retention_repository import SqlRetentionRepository
from ghostcal.infrastructure.db.session import db_session, org_session, reset_engine
from ghostcal.infrastructure.db.subscriptions_repository import SqlSubscriptionRepository
from ghostcal.infrastructure.db.task_reminders_repository import SqlTaskReminderGateway
from ghostcal.infrastructure.db.webhooks_repository import SqlWebhookRepository
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.infrastructure.email.outbox import PendingEmail
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


class WebhookDeliveryIncomplete(Exception):
    """At least one endpoint failed in a way worth retrying."""


class EmailDeferred(Exception):
    """The provider could not take the message this time, but might in a minute."""


class EmailRefused(Exception):
    """The provider said no, and would say no again. Retrying only multiplies the log lines."""


@celery_app.task(name="ghostcal.sync_all_calendars")  # type: ignore[untyped-decorator]
def sync_all_calendars() -> int:
    """Sync every active CalDAV connection. Returns how many synced successfully."""
    return asyncio.run(_sync_all())


async def _sync_all() -> int:
    synced = 0
    try:
        async with db_session() as session:
            connections = await active_caldav_connections(session)

        for organization_id, user_id, connection_id in connections:
            try:
                async with org_session(organization_id) as session:
                    repo = SqlCaldavConnectionRepository(session, organization_id)
                    await sync_connection(
                        repo,
                        _cipher,
                        _client,
                        _clock,
                        connection_id=connection_id,
                        user_id=user_id,
                    )
                synced += 1
            except CalendarError, NotConnected:
                logger.warning("calendar sync failed for connection=%s", connection_id)
            except Exception:
                logger.exception("error syncing connection=%s", connection_id)

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


@celery_app.task(  # type: ignore[untyped-decorator]
    name="ghostcal.deliver_webhooks",
    bind=True,
    autoretry_for=(WebhookDeliveryIncomplete,),
    retry_backoff=_settings.task_retry_backoff_seconds,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=_settings.task_max_retries,
)
def deliver_webhooks(
    self: object,
    organization_id: str,
    event_type: str,
    payload: dict[str, object],
    event_id: str | None = None,
) -> int:
    """POST a signed event payload to every active endpoint subscribed to it.

    Retries when at least one endpoint failed transiently. Previously a 500 from a subscriber was
    logged once and the event was gone forever, which made webhooks unreliable in exactly the
    situation subscribers most need them to be reliable.
    """
    return asyncio.run(
        _deliver_webhooks(uuid.UUID(organization_id), event_type, payload, event_id or "")
    )


async def _deliver_webhooks(
    organization_id: uuid.UUID, event_type: str, payload: dict[str, object], event_id: str = ""
) -> int:
    delivered = 0
    try:
        async with org_session(organization_id) as session:
            targets = await SqlWebhookRepository(session, organization_id).targets_for_event(
                event_type
            )
        if not targets:
            return 0
        body = json.dumps(
            {"event": event_type, "id": event_id, "data": payload}, default=str
        ).encode()
        retryable = 0
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
                    # Stable across retries, so a subscriber can discard duplicates. Delivery is
                    # at-least-once by construction and no amount of retry logic changes that;
                    # what we owe consumers is the means to deduplicate.
                    "X-GhostCal-Event-Id": event_id,
                    "X-GhostCal-Signature": f"sha256={sign_payload(target.secret, body)}",
                }
                try:
                    response = await http.post(target.url, content=body, headers=headers)
                    if response.status_code < 400:
                        delivered += 1
                    elif response.status_code >= 500 or response.status_code == 429:
                        # The subscriber is down or throttling us — worth trying again. A 4xx is
                        # the subscriber saying no, and retrying it just repeats the argument.
                        retryable += 1
                        logger.warning("webhook %s returned %s", target.url, response.status_code)
                    else:
                        logger.warning("webhook %s returned %s", target.url, response.status_code)
                except httpx.HTTPError:
                    retryable += 1
                    logger.warning("webhook delivery to %s failed", target.url)
        if retryable:
            raise WebhookDeliveryIncomplete(f"{retryable} endpoint(s) failed transiently")
    finally:
        await reset_engine()
    return delivered


def emit_event(organization_id: uuid.UUID, event_type: str, payload: dict[str, object]) -> None:
    """Enqueue webhook delivery for an event. Best-effort: never fails the caller."""
    try:
        deliver_webhooks.delay(str(organization_id), event_type, payload, str(uuid.uuid4()))
    except Exception:
        logger.warning("could not enqueue webhook event %s", event_type)


def _is_worth_retrying(status_code: int) -> bool:
    """Whether a provider's refusal is about this moment or about us.

    A 401 or a 403 is the API key, the sending domain or the caller's egress address being wrong --
    the exact 401 that took sign-ups down on 2026-09-25. None of that changes in ten seconds, so
    three retries would produce three identical failures, delay the giving-up by a minute and bury
    the one log line an operator needs under four. A 429 is the provider asking us to come back
    later, and a 5xx is the provider being briefly unwell; both are what backoff is for. 408 joins
    them: the request never landed.
    """
    return status_code in (408, 429) or status_code >= 500


@celery_app.task(  # type: ignore[untyped-decorator]
    name="ghostcal.send_email",
    bind=True,
    autoretry_for=(EmailDeferred,),
    retry_backoff=_settings.task_retry_backoff_seconds,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=_settings.task_max_retries,
)
def send_email(
    self: object,
    to: str,
    subject: str,
    html: str,
    attachments: list[dict[str, str]] | None = None,
) -> None:
    """Send one transactional email, off the request path.

    Lives here so that a provider outage costs a user their *email*, not their account. The caller
    that queued this has already committed; see `infrastructure/email/outbox.py` for why the order
    matters.

    No `reset_engine()` in a `finally` unlike its neighbours: this task opens no session, and
    calling it would build an engine purely to dispose of it.
    """
    asyncio.run(_send_email(to, subject, html, attachments or []))


async def _send_email(to: str, subject: str, html: str, attachments: list[dict[str, str]]) -> None:
    domain = PendingEmail(to=to, subject=subject, html=html).recipient_domain
    decoded = tuple(
        Attachment(
            filename=a["filename"],
            content=base64.b64decode(a["content"]),
            content_type=a.get("content_type", "application/octet-stream"),
        )
        for a in attachments
    )
    try:
        await _mailer.send(to=to, subject=subject, html=html, attachments=decoded or None)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if _is_worth_retrying(status):
            logger.warning(
                "email provider returned %s, will retry: subject=%r recipient_domain=%s",
                status,
                subject,
                domain,
            )
            raise EmailDeferred(f"provider returned {status}") from exc
        # Raised, not swallowed: the task ends in FAILURE, which is what puts it on the worker's
        # `celery_tasks{outcome="failure"}` counter and through `_log_failure`. A best-effort send
        # that returned quietly here would leave the user with no email and the estate with no
        # sign that anything happened -- the same invisible breakage as the verification links
        # that pointed at localhost.
        logger.error(
            "email refused by the provider and dropped: status=%s subject=%r recipient_domain=%s",
            status,
            subject,
            domain,
        )
        raise EmailRefused(f"provider returned {status}") from exc
    except httpx.HTTPError as exc:
        # Timeouts, DNS, connection resets: the provider never got to answer. Always transient.
        logger.warning(
            "email provider unreachable, will retry: subject=%r recipient_domain=%s",
            subject,
            domain,
        )
        raise EmailDeferred(str(exc)) from exc
    logger.info("email sent: subject=%r recipient_domain=%s", subject, domain)


def enqueue_email(message: PendingEmail) -> None:
    """Put one message on the queue. Raises if the broker will not take it.

    Deliberately *not* best-effort, unlike `emit_event` above: the swallowing happens one layer up,
    in `DeferredEmailSender.hand_off`, so exactly one place decides that a lost email must not cost
    a user their account -- and so a future caller of this function gets an exception rather than a
    silence it did not ask for.
    """
    send_email.delay(
        message.to,
        message.subject,
        message.html,
        [
            {
                "filename": a.filename,
                "content": base64.b64encode(a.content).decode("ascii"),
                "content_type": a.content_type,
            }
            for a in message.attachments
        ],
    )


@celery_app.task(name="ghostcal.purge_expired_bookings")  # type: ignore[untyped-decorator]
def purge_expired_bookings() -> int:
    """Purge bookings past their org's retention window. Returns how many were destroyed."""
    return asyncio.run(_purge_expired_bookings())


async def _purge_expired_bookings() -> int:
    total = 0
    try:
        results = await _purge_every_organization()
        # Irreversible, so never silent: say which organization lost how many rows.
        for result in results:
            logger.info(
                "purged %d expired bookings in organization %s",
                result.purged,
                result.organization_id,
            )
            total += result.purged
    finally:
        await reset_engine()
    return total


async def _purge_every_organization() -> list[PurgeResult]:
    """Enumerate, then bind, then delete — one organization at a time.

    The same shape as `sync_all_calendars` above, and for the same reason: each organization needs
    its own bound session. The enumeration is the only cross-tenant step, it goes through a function
    whose return type is an id and a number of days, and the deletion that follows runs under the
    ordinary policy.

    One organization failing must not stop the others: a purge that abandons the rest of the estate
    because one tenant errored is a retention window quietly unhonoured for everyone after it.
    """
    async with db_session() as session:
        windows = await SqlRetentionRepository(session).retention_windows()

    results: list[PurgeResult] = []
    for window in windows:
        try:
            async with org_session(window.organization_id) as session:
                results.append(
                    await purge_one_organization(SqlRetentionRepository(session), window)
                )
        except Exception:
            logger.exception("purge failed for organization=%s", window.organization_id)
    return results
