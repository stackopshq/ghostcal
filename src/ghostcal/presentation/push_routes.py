"""Publish a calendar to an external CalDAV server.

The endpoint that matters is ``POST /push``. It receives cleartext, forwards it to somebody else's
CalDAV server, and **writes none of it down**. That is the whole design: the server cannot read a
sealed event, so the browser opens it and hands over the result at push time. The pattern is already
here — ``send_event_invitation_email`` builds its ICS from browser-supplied cleartext and persists
nothing.

The honest cost: a push waits for a browser. There is no worker doing this on a schedule, because a
worker cannot read an event. The queue is what makes that bearable — a change is remembered until
some tab, at some later point, is open with the key unlocked.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.ports.calendar import (
    CalendarAuthError,
    CalendarCredentials,
    CalendarError,
)
from ghostcal.application.push import BATCH, ResolvedPush
from ghostcal.config import get_settings
from ghostcal.infrastructure.calendars import CaldavCalendarClient
from ghostcal.infrastructure.db.push_repository import SqlPushRepository
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.security.encryption import SecretBox
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    PendingPushOut,
    PublishIn,
    PushIn,
    PushResultOut,
)

router = APIRouter(prefix="/v1/me/calendar", tags=["calendar-push"])
logger = logging.getLogger(__name__)

_settings = get_settings()
_cipher = SecretBox(_settings.token_encryption_key.get_secret_value())
_client = CaldavCalendarClient()


@router.put("/calendars/{calendar_id}/publish", status_code=204)
async def publish_calendar(
    calendar_id: uuid.UUID, payload: PublishIn, member: Member = Depends(current_member)
) -> None:
    """Publish this calendar to one of your connected CalDAV calendars, or to nowhere (null).

    Turning it on queues everything already on the calendar, not just what changes next — a calendar
    that only publishes its future is not published.
    """
    async with org_session(member.organization_id) as session:
        repo = SqlPushRepository(session, member.organization_id)
        if not await repo.set_target(member.user.id, calendar_id, payload.connection_id):
            raise HTTPException(status_code=404, detail="calendar not found")
        if payload.connection_id is not None:
            queued = await repo.backfill(calendar_id)
            logger.info("queued %d events to publish for calendar %s", queued, calendar_id)


@router.get("/push/pending", response_model=list[PendingPushOut])
async def pending_pushes(
    limit: int = Query(default=BATCH, ge=1, le=100),
    member: Member = Depends(current_member),
) -> list[PendingPushOut]:
    """What is waiting to be published. Event content comes back SEALED — the browser opens it."""
    async with org_session(member.organization_id) as session:
        pending = await SqlPushRepository(session, member.organization_id).pending(
            member.user.id, limit=limit
        )
    return [
        PendingPushOut(
            id=p.id,
            op=p.op,
            external_uid=p.external_uid,
            content_sealed=p.content,
            start_at=p.start_at,
            end_at=p.end_at,
            all_day=p.all_day,
            rrule=p.rrule,
        )
        for p in pending
    ]


@router.post("/push", response_model=PushResultOut)
async def push(payload: PushIn, member: Member = Depends(current_member)) -> PushResultOut:
    """Relay opened events to the CalDAV server. Nothing here is written down.

    The cleartext exists in this process for exactly as long as the CalDAV request takes, and is
    never persisted, logged or cached. That is what keeps the zero-knowledge property intact while
    still putting your events on your phone.

    A queue row is dropped only *after* its write lands — a failed push stays queued, which is the
    entire point of having a queue.
    """
    pushed = 0
    failed = 0

    for item in payload.items:
        resolved = ResolvedPush(
            id=item.id,
            op=item.op,
            external_uid=item.external_uid,
            summary=item.summary,
            description=item.description,
            location=item.location,
            start_at=item.start_at,
            end_at=item.end_at,
            rrule=item.rrule,
        )
        async with org_session(member.organization_id) as session:
            repo = SqlPushRepository(session, member.organization_id)
            target = await repo.target_for(member.user.id, resolved.id)
            if target is None:
                # Queued for a calendar that stopped publishing, or is not theirs. Drop it.
                await repo.done(member.user.id, resolved.id)
                continue
            creds = CalendarCredentials(
                server_url=target.server_url,
                username=target.username,
                password=_cipher.decrypt(target.password_encrypted),
            )
            calendar_url = target.calendar_url

        try:
            if resolved.op == "delete":
                await _client.delete_event(creds, calendar_url, resolved.external_uid)
            else:
                if resolved.start_at is None or resolved.end_at is None:
                    raise CalendarError("an upsert needs a start and an end")
                await _client.create_event(
                    creds,
                    calendar_url,
                    uid=resolved.external_uid,
                    summary=resolved.summary,
                    description=resolved.description,
                    location=resolved.location,
                    start=resolved.start_at,
                    end=resolved.end_at,
                    rrule=resolved.rrule,
                )
        except CalendarAuthError, CalendarError:
            # Left in the queue on purpose: a stale password or an unreachable server is a reason to
            # try again later, not a reason to forget the change.
            logger.warning("could not publish %s to CalDAV", resolved.external_uid)
            failed += 1
            continue

        async with org_session(member.organization_id) as session:
            await SqlPushRepository(session, member.organization_id).done(
                member.user.id, resolved.id
            )
        pushed += 1

    return PushResultOut(pushed=pushed, failed=failed)
