"""Free-busy links: the owner's side, and the visitor's.

The visitor's side is four lines of real work, and that is the point. There is no key to hand over,
no ciphertext to relay and no fragment to protect, because a free-busy link discloses only what the
server already knows: *when* this person is occupied, never *what* occupies them.

The busy intervals come from ``busy_for`` — the same function the booking page uses to decide which
slots to offer. Not a copy of it. If the two ever disagreed, one of them would be lying to someone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ghostcal.application.busy_links import BusyLinkOwner
from ghostcal.application.links import hash_token, new_token
from ghostcal.application.scheduling import busy_for
from ghostcal.config import get_settings
from ghostcal.domain.time import TimeRange, merge
from ghostcal.infrastructure.calendars.busy_ics import render_busy_calendar
from ghostcal.infrastructure.db.busy_links_repository import SqlBusyLinkRepository
from ghostcal.infrastructure.db.repository import SqlSchedulingRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.infrastructure.ratelimit import rate_limit
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    BusyBlockOut,
    BusyLinkCreatedOut,
    BusyLinkCreateIn,
    BusyLinkOut,
    PublicBusyOut,
)

router = APIRouter(tags=["busy-links"])
_settings = get_settings()

# How far ahead a visitor may look. Long enough to plan a meeting, short enough that the answer says
# "here is my next fortnight" rather than handing over a map of someone's year.
DEFAULT_DAYS = 14
MAX_DAYS = 62


@router.get("/v1/me/busy-links", response_model=list[BusyLinkOut])
async def list_busy_links(member: Member = Depends(current_member)) -> list[BusyLinkOut]:
    async with org_session(member.organization_id) as session:
        links = await SqlBusyLinkRepository(session, member.organization_id).list_for_user(
            member.user.id
        )
    return [BusyLinkOut(id=x.id, name=x.name, created_at=x.created_at) for x in links]


@router.post("/v1/me/busy-links", response_model=BusyLinkCreatedOut, status_code=201)
async def create_busy_link(
    payload: BusyLinkCreateIn, member: Member = Depends(current_member)
) -> BusyLinkCreatedOut:
    """Mint a link. The token comes back once, here, and only its hash is kept.

    Unlike an ADR-0009 calendar link, there is no keypair to generate: nothing about this link is
    encrypted, because nothing it shows was ever secret from the server.
    """
    token = new_token()
    async with org_session(member.organization_id) as session:
        link_id = await SqlBusyLinkRepository(session, member.organization_id).create(
            member.user.id, token_hash=hash_token(token), name=payload.name
        )
    return BusyLinkCreatedOut(id=link_id, token=token)


@router.delete("/v1/me/busy-links/{link_id}", status_code=204)
async def revoke_busy_link(link_id: uuid.UUID, member: Member = Depends(current_member)) -> None:
    async with org_session(member.organization_id) as session:
        if not await SqlBusyLinkRepository(session, member.organization_id).delete(
            member.user.id, link_id
        ):
            raise HTTPException(status_code=404, detail="link not found")


@router.get(
    "/v1/public/busy/{token}",
    response_model=PublicBusyOut,
    dependencies=[Depends(rate_limit("public-busy", _settings.booking_rate_limit_per_minute))],
)
async def public_busy(
    token: str,
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS),
) -> PublicBusyOut:
    """When this person is occupied. No account, no session, no organization — and no titles.

    The blocks are **merged** before they leave. Unmerged, their shape is itself information: three
    meetings stacked on one hour say something about how in demand someone is that a single "busy"
    does not. What goes out is "occupied from 09:00 to 12:00", and nothing beyond it.
    """
    owner, busy = await _resolve_and_compute(token, days)
    return PublicBusyOut(
        owner_name=owner.owner_name,
        owner_timezone=owner.owner_timezone,
        busy=[BusyBlockOut(start_at=b.start, end_at=b.end) for b in busy],
    )


async def _resolve_and_compute(token: str, days: int) -> tuple[BusyLinkOwner, list[TimeRange]]:
    """The token, the person behind it, and their merged busy time.

    Extracted the day the calendar feed arrived: two representations of one link must
    not each carry their own copy of this, or the day somebody changes what "busy"
    means, one of the two starts lying — and it would be the one nobody looks at.
    """
    async with db_session() as session:
        # No org context: the visitor belongs to none. This one SECURITY DEFINER door resolves the
        # token to a person, and to nothing else — it returns no times at all.
        owner: BusyLinkOwner | None = await SqlBusyLinkRepository(
            session, uuid.UUID(int=0)
        ).resolve(hash_token(token))
    if owner is None:
        raise HTTPException(status_code=404, detail="no such availability link")

    start = datetime.combine(date.today(), time.min, tzinfo=UTC)
    end = start + timedelta(days=days)

    async with org_session(owner.organization_id) as session:
        # Now inside the owner's organization, so RLS applies again — and the query below is the
        # scheduler's own. There is one definition of "busy" in this system, and this is it.
        busy = await busy_for(
            SqlSchedulingRepository(session, owner.organization_id), owner.user_id, start, end
        )
    return owner, merge(busy)


@router.get(
    "/v1/public/busy/{token}/calendar.ics",
    response_class=Response,
    dependencies=[Depends(rate_limit("public-busy", _settings.booking_rate_limit_per_minute))],
)
async def public_busy_ics(
    token: str,
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS),
) -> Response:
    """The same link, as a calendar a phone can subscribe to.

    The path puts the token in its own segment rather than suffixing it
    (``…/{token}.ics``). That form matched nothing: FastAPI tries routes in
    declaration order, the JSON route above declares ``{token}`` as a whole segment,
    and it happily swallowed ``abc.ics`` as a token — answering 404 for a link that
    exists. Declaring this route first would fix it and leave a trap, since reordering
    the file would silently break the feed again. A distinct path cannot be shadowed by
    anything.

    Same token, same blocks, same ceiling on how far ahead a visitor may look — only the
    representation differs. A subscription is the right shape here where it was the wrong
    one for tasks: a subscribed calendar carries ``VEVENT`` happily, and busy time *is*
    a set of events.

    The URL is the credential, so it is handed out exactly like the JSON one: revoking
    the link stops the feed on every device that holds it, without touching anything
    else.
    """
    owner, busy = await _resolve_and_compute(token, days)
    body = render_busy_calendar(
        calendar_name=owner.owner_name,
        blocks=[(b.start, b.end) for b in busy],
        # Scoped to this link: two links published by the same person for the same hour
        # must not produce the same UID, or a holder of one could confirm what the other
        # publishes.
        uid_secret=hash_token(token).encode(),
    )
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            # A calendar client that follows a link expects a file, and some refuse to
            # subscribe to something the browser would rather render.
            "Content-Disposition": 'inline; filename="disponibilites.ics"',
            # Never store this on a shared hop: the URL is a bearer credential, and a
            # cached copy outlives the revocation that was supposed to end it.
            "Cache-Control": "no-store, private",
        },
    )
