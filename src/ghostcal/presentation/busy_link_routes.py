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

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.busy_links import BusyLinkOwner
from ghostcal.application.links import hash_token, new_token
from ghostcal.application.scheduling import busy_for
from ghostcal.config import get_settings
from ghostcal.domain.time import merge
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

    return PublicBusyOut(
        owner_name=owner.owner_name,
        owner_timezone=owner.owner_timezone,
        busy=[BusyBlockOut(start_at=b.start, end_at=b.end) for b in merge(busy)],
    )
