"""Meeting polls against a live PostgreSQL: create, vote, re-vote, finalize, close."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.polls import (
    PollNotOpen,
    cancel_poll,
    cast_votes,
    create_poll,
    finalize_poll,
    get_poll,
    get_public_poll,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.polls_repository import SqlPollsRepository
from ghostcal.infrastructure.db.session import org_session

pytestmark = pytest.mark.integration


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, *, to: str, subject: str, html: str, attachments: object = None) -> None:
        self.sent.append(to)


def _repo(session: object, org_id: uuid.UUID) -> SqlPollsRepository:
    return SqlPollsRepository(session, org_id)  # type: ignore[arg-type]


async def test_poll_vote_finalize_flow(admin_engine: AsyncEngine) -> None:
    org_id = owner = None
    try:
        async with async_sessionmaker(admin_engine, expire_on_commit=False)() as db:
            org = models.Organization(name="Poll Org", slug=f"pl-{uuid.uuid4().hex[:8]}")
            owner_user = models.User(
                email=f"owner-{uuid.uuid4().hex[:8]}@example.com", name="Host", timezone="UTC"
            )
            db.add_all([org, owner_user])
            await db.flush()
            org_id, owner = org.id, owner_user.id
            db.add(models.Membership(organization_id=org_id, user_id=owner, role="owner"))
            await db.commit()

        base = datetime.now(UTC) + timedelta(days=3)
        starts = [base, base + timedelta(hours=1), base + timedelta(hours=2)]

        async with org_session(org_id) as session:
            poll_id = await create_poll(
                _repo(session, org_id),
                owner,
                title="Team Sync",
                duration_min=30,
                location_type="google_meet",
                option_starts=starts,
            )

        async with org_session(org_id) as session:
            poll = await get_poll(_repo(session, org_id), poll_id, owner)
        assert poll.status == "open"
        assert len(poll.options) == 3
        slug = poll.slug
        opt = {i: o.id for i, o in enumerate(poll.options)}

        # Two voters; option 0 gets both, option 1 gets one.
        async with org_session(org_id) as session:
            await cast_votes(
                _repo(session, org_id),
                slug,
                voter_name="Ann",
                voter_email="ann@example.com",
                option_ids=[opt[0], opt[1]],
            )
        async with org_session(org_id) as session:
            await cast_votes(
                _repo(session, org_id),
                slug,
                voter_name="Ben",
                voter_email="ben@example.com",
                option_ids=[opt[0]],
            )

        async with org_session(org_id) as session:
            public = await get_public_poll(_repo(session, org_id), slug)
        tally = {o.id: o.votes for o in public.options}
        assert tally[opt[0]] == 2
        assert tally[opt[1]] == 1
        assert tally[opt[2]] == 0

        # Ann changes her vote to option 2 only (replace).
        async with org_session(org_id) as session:
            await cast_votes(
                _repo(session, org_id),
                slug,
                voter_name="Ann",
                voter_email="ann@example.com",
                option_ids=[opt[2]],
            )
        async with org_session(org_id) as session:
            poll = await get_poll(_repo(session, org_id), poll_id, owner)
        tally = {o.id: o.votes for o in poll.options}
        assert tally[opt[0]] == 1  # only Ben now
        assert tally[opt[2]] == 1  # Ann moved here
        assert len(poll.voters) == 2

        # Finalize option 0; both voters are notified.
        mailer = CapturingMailer()
        async with org_session(org_id) as session:
            finalized = await finalize_poll(_repo(session, org_id), mailer, poll_id, owner, opt[0])
        assert finalized.status == "finalized"
        assert finalized.finalized_option_id == opt[0]
        assert set(mailer.sent) == {"ann@example.com", "ben@example.com"}

        # Voting on a finalized poll is rejected.
        with pytest.raises(PollNotOpen):
            async with org_session(org_id) as session:
                await cast_votes(
                    _repo(session, org_id),
                    slug,
                    voter_name="Late",
                    voter_email="late@example.com",
                    option_ids=[opt[1]],
                )

        # Cancelling removes it from the open set.
        async with org_session(org_id) as session:
            await cancel_poll(_repo(session, org_id), poll_id, owner)
        async with org_session(org_id) as session:
            poll = await get_poll(_repo(session, org_id), poll_id, owner)
        assert poll.status == "cancelled"
    finally:
        if org_id is not None:
            async with async_sessionmaker(admin_engine)() as db:
                await db.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                if owner is not None:
                    await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": owner})
                await db.commit()
