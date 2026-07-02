"""Public RSVP endpoints for personal-event invitations (no authentication).

The invitee opens a tokenised link; these read/update only the RSVP status and the event's time
(via SECURITY DEFINER functions, no org context). The event title/notes stay sealed — the invitee
saw them in the ICS they were emailed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.attendees import preview_invitation, respond_invitation
from ghostcal.infrastructure.db.attendees_repository import SqlInvitationGateway
from ghostcal.infrastructure.db.session import db_session
from ghostcal.infrastructure.ratelimit import rate_limit
from ghostcal.presentation.schemas import EventInvitePreviewOut, EventInviteRespondIn

router = APIRouter(prefix="/v1/invitations/event", tags=["invitations"])
_RL = [Depends(rate_limit("event_invite", 30))]


@router.get("/{token}", response_model=EventInvitePreviewOut, dependencies=_RL)
async def preview_event_invitation(token: str) -> EventInvitePreviewOut:
    async with db_session() as session:
        preview = await preview_invitation(SqlInvitationGateway(session), token=token)
    if preview is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    return EventInvitePreviewOut(
        start_at=preview.start_at,
        end_at=preview.end_at,
        timezone=preview.timezone,
        all_day=preview.all_day,
        status=preview.status,
    )


@router.post("/{token}/respond", status_code=204, dependencies=_RL)
async def respond_event_invitation(token: str, payload: EventInviteRespondIn) -> None:
    async with db_session() as session:
        ok = await respond_invitation(
            SqlInvitationGateway(session), token=token, status=payload.status
        )
    if not ok:
        raise HTTPException(status_code=404, detail="invitation not found")
