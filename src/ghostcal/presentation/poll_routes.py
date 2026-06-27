"""Host endpoints for meeting polls (create, list, view tallies, finalize, cancel)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from ghostcal.application.polls import (
    InvalidPoll,
    OptionNotInPoll,
    PollData,
    PollNotFound,
    PollNotOpen,
    cancel_poll,
    create_poll,
    finalize_poll,
    get_poll,
    list_polls,
)
from ghostcal.config import get_settings
from ghostcal.infrastructure.db.polls_repository import SqlPollsRepository
from ghostcal.infrastructure.db.session import org_session
from ghostcal.infrastructure.email import build_email_sender
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    FinalizeIn,
    PollCreateIn,
    PollOptionOut,
    PollOut,
    PollSummaryOut,
    VoterOut,
)

router = APIRouter(prefix="/v1/me/polls", tags=["polls"])
_settings = get_settings()
_mailer = build_email_sender(_settings)


def _poll_out(poll: PollData) -> PollOut:
    return PollOut(
        id=poll.id,
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
        voters=[
            VoterOut(name=v.name, email=v.email, option_ids=list(v.option_ids)) for v in poll.voters
        ],
    )


@router.post("", response_model=PollOut, status_code=201)
async def create_my_poll(
    payload: PollCreateIn, member: Member = Depends(current_member)
) -> PollOut:
    async with org_session(member.organization_id) as session:
        repo = SqlPollsRepository(session, member.organization_id)
        try:
            poll_id = await create_poll(
                repo,
                member.user.id,
                title=payload.title,
                duration_min=payload.duration_min,
                location_type=payload.location_type,
                option_starts=payload.option_starts,
            )
        except InvalidPoll as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        poll = await get_poll(repo, poll_id, member.user.id)
    return _poll_out(poll)


@router.get("", response_model=list[PollSummaryOut])
async def list_my_polls(member: Member = Depends(current_member)) -> list[PollSummaryOut]:
    async with org_session(member.organization_id) as session:
        polls = await list_polls(
            SqlPollsRepository(session, member.organization_id), member.user.id
        )
    return [
        PollSummaryOut(
            id=p.id,
            slug=p.slug,
            title=p.title,
            status=p.status,
            option_count=p.option_count,
            vote_count=p.vote_count,
        )
        for p in polls
    ]


@router.get("/{poll_id}", response_model=PollOut)
async def get_my_poll(poll_id: uuid.UUID, member: Member = Depends(current_member)) -> PollOut:
    async with org_session(member.organization_id) as session:
        try:
            poll = await get_poll(
                SqlPollsRepository(session, member.organization_id), poll_id, member.user.id
            )
        except PollNotFound as exc:
            raise HTTPException(status_code=404, detail="poll not found") from exc
    return _poll_out(poll)


@router.post("/{poll_id}/finalize", response_model=PollOut)
async def finalize_my_poll(
    poll_id: uuid.UUID, payload: FinalizeIn, member: Member = Depends(current_member)
) -> PollOut:
    async with org_session(member.organization_id) as session:
        repo = SqlPollsRepository(session, member.organization_id)
        try:
            poll = await finalize_poll(repo, _mailer, poll_id, member.user.id, payload.option_id)
        except PollNotFound as exc:
            raise HTTPException(status_code=404, detail="poll not found") from exc
        except OptionNotInPoll as exc:
            raise HTTPException(status_code=422, detail="unknown option") from exc
        except PollNotOpen as exc:
            raise HTTPException(status_code=409, detail="poll is cancelled") from exc
    return _poll_out(poll)


@router.delete("/{poll_id}", status_code=204)
async def cancel_my_poll(poll_id: uuid.UUID, member: Member = Depends(current_member)) -> None:
    async with org_session(member.organization_id) as session:
        try:
            await cancel_poll(
                SqlPollsRepository(session, member.organization_id), poll_id, member.user.id
            )
        except PollNotFound as exc:
            raise HTTPException(status_code=404, detail="poll not found") from exc
