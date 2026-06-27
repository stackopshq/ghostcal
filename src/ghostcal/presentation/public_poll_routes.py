"""Public poll endpoints reached by slug: view options/tallies and cast a vote."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from ghostcal.application.polls import (
    InvalidPoll,
    OptionNotInPoll,
    PollNotFound,
    PollNotOpen,
    cast_votes,
    get_public_poll,
)
from ghostcal.infrastructure.db.membership import poll_organization_by_slug
from ghostcal.infrastructure.db.polls_repository import SqlPollsRepository
from ghostcal.infrastructure.db.session import db_session, org_session
from ghostcal.presentation.schemas import PollOptionOut, PublicPollOut, VoteIn

router = APIRouter(prefix="/v1/polls", tags=["polls"])


async def _resolve_org(slug: str) -> uuid.UUID:
    async with db_session() as session:
        org_id = await poll_organization_by_slug(session, slug)
    if org_id is None:
        raise HTTPException(status_code=404, detail="poll not found")
    return org_id


@router.get("/{slug}", response_model=PublicPollOut)
async def view_poll(slug: str) -> PublicPollOut:
    org_id = await _resolve_org(slug)
    async with org_session(org_id) as session:
        try:
            poll = await get_public_poll(SqlPollsRepository(session, org_id), slug)
        except PollNotFound as exc:
            raise HTTPException(status_code=404, detail="poll not found") from exc
    return PublicPollOut(
        slug=poll.slug,
        title=poll.title,
        duration_min=poll.duration_min,
        location_type=poll.location_type,
        status=poll.status,
        owner_name=poll.owner_name,
        finalized_option_id=poll.finalized_option_id,
        options=[
            PollOptionOut(id=o.id, start_at=o.start_at, end_at=o.end_at, votes=o.votes)
            for o in poll.options
        ],
    )


@router.post("/{slug}/votes", status_code=204)
async def vote(slug: str, payload: VoteIn) -> None:
    org_id = await _resolve_org(slug)
    async with org_session(org_id) as session:
        try:
            await cast_votes(
                SqlPollsRepository(session, org_id),
                slug,
                voter_name=payload.voter_name,
                voter_email=str(payload.voter_email),
                option_ids=payload.option_ids,
            )
        except PollNotFound as exc:
            raise HTTPException(status_code=404, detail="poll not found") from exc
        except PollNotOpen as exc:
            raise HTTPException(status_code=409, detail="poll is closed") from exc
        except (OptionNotInPoll, InvalidPoll) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
