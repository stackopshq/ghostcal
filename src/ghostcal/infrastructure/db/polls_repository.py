"""SQL implementation of the polls repository (org-scoped; RLS via org_session)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.polls import (
    PollData,
    PollOptionData,
    PollsRepository,
    PollSummary,
    Voter,
)
from ghostcal.infrastructure.db import models


class SqlPollsRepository(PollsRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def create(
        self,
        owner_id: uuid.UUID,
        *,
        slug: str,
        title: str,
        duration_min: int,
        location_type: str,
        options: list[tuple[datetime, datetime]],
    ) -> uuid.UUID:
        poll_id = (
            await self._session.execute(
                insert(models.Poll)
                .values(
                    organization_id=self._org_id,
                    owner_id=owner_id,
                    slug=slug,
                    title=title,
                    duration_min=duration_min,
                    location_type=location_type,
                    status="open",
                )
                .returning(models.Poll.id)
            )
        ).scalar_one()
        for start_at, end_at in options:
            await self._session.execute(
                insert(models.PollOption).values(
                    organization_id=self._org_id,
                    poll_id=poll_id,
                    start_at=start_at,
                    end_at=end_at,
                )
            )
        return poll_id

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[PollSummary]:
        option_count = (
            select(func.count())
            .where(models.PollOption.poll_id == models.Poll.id)
            .scalar_subquery()
        )
        vote_count = (
            select(func.count()).where(models.PollVote.poll_id == models.Poll.id).scalar_subquery()
        )
        rows = (
            await self._session.execute(
                select(models.Poll, option_count, vote_count)
                .where(models.Poll.owner_id == owner_id)
                .order_by(models.Poll.created_at.desc())
            )
        ).all()
        return [
            PollSummary(
                id=poll.id,
                slug=poll.slug,
                title=poll.title,
                status=poll.status,
                option_count=opts,
                vote_count=votes,
            )
            for poll, opts, votes in rows
        ]

    async def get_for_owner(self, poll_id: uuid.UUID, owner_id: uuid.UUID) -> PollData | None:
        poll = (
            await self._session.execute(
                select(models.Poll).where(
                    models.Poll.id == poll_id, models.Poll.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if poll is None:
            return None
        return await self._build(poll, include_voters=True)

    async def get_by_slug(self, slug: str) -> PollData | None:
        poll = (
            await self._session.execute(select(models.Poll).where(models.Poll.slug == slug))
        ).scalar_one_or_none()
        if poll is None:
            return None
        return await self._build(poll, include_voters=False)

    async def _build(self, poll: models.Poll, *, include_voters: bool) -> PollData:
        option_rows = (
            (
                await self._session.execute(
                    select(models.PollOption)
                    .where(models.PollOption.poll_id == poll.id)
                    .order_by(models.PollOption.start_at)
                )
            )
            .scalars()
            .all()
        )
        tally_rows = (
            await self._session.execute(
                select(models.PollVote.option_id, func.count())
                .where(models.PollVote.poll_id == poll.id)
                .group_by(models.PollVote.option_id)
            )
        ).all()
        tallies: dict[uuid.UUID, int] = {oid: count for oid, count in tally_rows}  # noqa: C416
        owner_name = (
            await self._session.execute(
                select(models.User.name).where(models.User.id == poll.owner_id)
            )
        ).scalar_one()
        options = tuple(
            PollOptionData(
                id=o.id, start_at=o.start_at, end_at=o.end_at, votes=tallies.get(o.id, 0)
            )
            for o in option_rows
        )
        voters: tuple[Voter, ...] = ()
        if include_voters:
            vote_rows = (
                await self._session.execute(
                    select(
                        models.PollVote.voter_name,
                        models.PollVote.voter_email,
                        models.PollVote.option_id,
                    ).where(models.PollVote.poll_id == poll.id)
                )
            ).all()
            by_email: dict[str, tuple[str, list[uuid.UUID]]] = {}
            for name, email, option_id in vote_rows:
                by_email.setdefault(email, (name, []))[1].append(option_id)
            voters = tuple(
                Voter(name=name, email=email, option_ids=tuple(option_ids))
                for email, (name, option_ids) in by_email.items()
            )
        return PollData(
            id=poll.id,
            slug=poll.slug,
            title=poll.title,
            duration_min=poll.duration_min,
            location_type=poll.location_type,
            status=poll.status,
            owner_name=owner_name,
            finalized_option_id=poll.finalized_option_id,
            options=options,
            voters=voters,
        )

    async def cancel(self, poll_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            update(models.Poll)
            .where(models.Poll.id == poll_id, models.Poll.owner_id == owner_id)
            .values(status="cancelled")
            .returning(models.Poll.id)
        )
        return result.first() is not None

    async def finalize(self, poll_id: uuid.UUID, owner_id: uuid.UUID, option_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            update(models.Poll)
            .where(
                models.Poll.id == poll_id,
                models.Poll.owner_id == owner_id,
                models.Poll.status != "cancelled",
            )
            .values(status="finalized", finalized_option_id=option_id)
            .returning(models.Poll.id)
        )
        return result.first() is not None

    async def replace_votes(
        self,
        poll_id: uuid.UUID,
        *,
        voter_name: str,
        voter_email: str,
        option_ids: tuple[uuid.UUID, ...],
    ) -> None:
        await self._session.execute(
            delete(models.PollVote).where(
                models.PollVote.poll_id == poll_id,
                func.lower(models.PollVote.voter_email) == voter_email.lower(),
            )
        )
        for option_id in option_ids:
            await self._session.execute(
                insert(models.PollVote).values(
                    organization_id=self._org_id,
                    poll_id=poll_id,
                    option_id=option_id,
                    voter_name=voter_name,
                    voter_email=voter_email,
                )
            )
