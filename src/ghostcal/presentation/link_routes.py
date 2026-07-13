"""Public calendar links (ADR-0009): the owner's side, and the visitor's.

The visitor has no account, no organization and no RLS context. They present a token and get back
one calendar's **sealed copies** — ciphertext that opens only with the key in their URL fragment,
which never reached this server and never will.

The owner's side is the interesting half. Creating a link does not, on its own, share anything: the
sealed copies do not exist yet. The owner's browser makes them, because it is the only thing that
can open an event at all. Until it has, the link shows an empty calendar — so the count of what is
left to seal is surfaced, rather than leaving a half-made link looking like a broken one.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.links import (
    PendingSeal,
    SealedCopy,
    hash_token,
    new_token,
)
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.links_repository import SqlLinkRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.ratelimit import rate_limit
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    LinkCreatedOut,
    LinkCreateIn,
    LinkOut,
    PendingSealOut,
    PublicCalendarOut,
    PublicEventOut,
    SealCopiesIn,
)

router = APIRouter(tags=["calendar-links"])
_settings = get_settings()

# How many events the owner's browser is handed to re-seal at once.
BATCH = 100


@router.get("/v1/me/calendars/{calendar_id}/links", response_model=list[LinkOut])
async def list_links(
    calendar_id: uuid.UUID, member: Member = Depends(current_member)
) -> list[LinkOut]:
    async with org_session(member.organization_id) as session:
        links = await SqlLinkRepository(session, member.organization_id).list_for_calendar(
            member.user.id, calendar_id
        )
    return [
        LinkOut(
            id=link.id,
            name=link.name,
            public_key=link.public_key,
            created_at=link.created_at,
            pending=link.pending,
        )
        for link in links
    ]


@router.post("/v1/me/calendars/{calendar_id}/links", response_model=LinkCreatedOut, status_code=201)
async def create_link(
    calendar_id: uuid.UUID, payload: LinkCreateIn, member: Member = Depends(current_member)
) -> LinkCreatedOut:
    """Mint a link. The browser generated its keypair and sends only the PUBLIC half.

    The token comes back once, here, and is never retrievable again — only its hash is kept. The
    private key is not in this request at all: it stays in the browser, and goes into the fragment.
    """
    token = new_token()
    async with org_session(member.organization_id) as session:
        link_id = await SqlLinkRepository(session, member.organization_id).create(
            member.user.id,
            calendar_id,
            token_hash=hash_token(token),
            public_key=payload.public_key,
            name=payload.name,
        )
    if link_id is None:
        raise HTTPException(status_code=404, detail="calendar not found")
    return LinkCreatedOut(id=link_id, token=token)


@router.get("/v1/me/links/{link_id}/pending", response_model=list[PendingSealOut])
async def pending_seals(
    link_id: uuid.UUID, member: Member = Depends(current_member)
) -> list[PendingSealOut]:
    """Events this link has no readable copy of yet. Content comes back sealed to the ORG key — the
    owner's browser opens it with that, and re-seals it to the link's public key."""
    async with org_session(member.organization_id) as session:
        pending: list[PendingSeal] = await SqlLinkRepository(
            session, member.organization_id
        ).pending_seals(member.user.id, link_id, limit=BATCH)
    return [PendingSealOut(event_id=p.event_id, content_sealed=p.content) for p in pending]


@router.post("/v1/me/links/{link_id}/seal", status_code=204)
async def store_copies(
    link_id: uuid.UUID, payload: SealCopiesIn, member: Member = Depends(current_member)
) -> None:
    """Store copies the browser re-sealed to the link's key. All ciphertext; the server reads none
    of it, and could not."""
    async with org_session(member.organization_id) as session:
        await SqlLinkRepository(session, member.organization_id).store_copies(
            member.user.id,
            link_id,
            [
                SealedCopy(event_id=c.event_id, content_sealed=c.content_sealed)
                for c in payload.copies
            ],
        )


@router.delete("/v1/me/links/{link_id}", status_code=204)
async def revoke_link(link_id: uuid.UUID, member: Member = Depends(current_member)) -> None:
    """Revocation is deletion. Whoever held the link keeps whatever they already read — that is true
    of anything anyone has ever been shown, and pretending otherwise would be the lie."""
    async with org_session(member.organization_id) as session:
        if not await SqlLinkRepository(session, member.organization_id).delete(
            member.user.id, link_id
        ):
            raise HTTPException(status_code=404, detail="link not found")


@router.get(
    "/v1/public/calendar/{token}",
    response_model=PublicCalendarOut,
    dependencies=[Depends(rate_limit("public-calendar", _settings.booking_rate_limit_per_minute))],
)
async def public_calendar(token: str) -> PublicCalendarOut:
    """A visitor's view of a shared calendar. No account, no session, no organization.

    Everything here is ciphertext. It opens with the key in the URL fragment — which this server has
    never seen, because browsers do not send fragments.
    """
    async with db_session() as session:
        # No org context: the visitor belongs to none. The SECURITY DEFINER function is the one door
        # they get, and it leads to exactly one calendar.
        calendar = await SqlLinkRepository(session, uuid.UUID(int=0)).public_calendar(
            hash_token(token)
        )
    if calendar is None:
        raise HTTPException(status_code=404, detail="no such calendar link")
    return PublicCalendarOut(
        calendar_name=calendar.calendar_name,
        owner_name=calendar.owner_name,
        events=[
            PublicEventOut(
                start_at=e.start_at,
                end_at=e.end_at,
                all_day=e.all_day,
                timezone=e.timezone,
                rrule=e.rrule,
                exdates=e.exdates,
                content_sealed=e.content_sealed,
            )
            for e in calendar.events
        ],
    )
