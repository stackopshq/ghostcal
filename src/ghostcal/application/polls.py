"""Meeting-poll use cases: the host proposes times, invitees vote, the host finalizes one.

Polls are a standalone async-scheduling artifact (no Booking is created on finalize in this slice;
finalizing notifies every voter of the chosen time). Persistence is the ``PollsRepository`` port.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ghostcal.application.ports.email import EmailSender

MIN_OPTIONS = 2
MAX_OPTIONS = 25


class PollError(Exception):
    """Base class for poll errors."""


class PollNotFound(PollError):
    pass


class InvalidPoll(PollError):
    pass


class PollNotOpen(PollError):
    pass


class OptionNotInPoll(PollError):
    pass


@dataclass(frozen=True, slots=True)
class PollOptionData:
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    votes: int = 0


@dataclass(frozen=True, slots=True)
class Voter:
    name: str
    email: str
    option_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class PollData:
    id: uuid.UUID
    slug: str
    title: str
    duration_min: int
    location_type: str
    status: str
    owner_name: str
    finalized_option_id: uuid.UUID | None
    options: tuple[PollOptionData, ...]
    voters: tuple[Voter, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PollSummary:
    id: uuid.UUID
    slug: str
    title: str
    status: str
    option_count: int
    vote_count: int


class PollsRepository:
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
        raise NotImplementedError

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[PollSummary]:
        raise NotImplementedError

    async def get_for_owner(self, poll_id: uuid.UUID, owner_id: uuid.UUID) -> PollData | None:
        raise NotImplementedError

    async def get_by_slug(self, slug: str) -> PollData | None:
        raise NotImplementedError

    async def cancel(self, poll_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def finalize(self, poll_id: uuid.UUID, owner_id: uuid.UUID, option_id: uuid.UUID) -> bool:
        """Mark the poll finalized with the winning option. False if poll/option not found."""
        raise NotImplementedError

    async def replace_votes(
        self,
        poll_id: uuid.UUID,
        *,
        voter_name: str,
        voter_email: str,
        option_ids: tuple[uuid.UUID, ...],
    ) -> None:
        raise NotImplementedError


def _slugify(title: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
    base = "-".join(filter(None, base.split("-")))[:60] or "poll"
    return f"{base}-{secrets.token_hex(3)}"


async def create_poll(
    repo: PollsRepository,
    owner_id: uuid.UUID,
    *,
    title: str,
    duration_min: int,
    location_type: str,
    option_starts: list[datetime],
) -> uuid.UUID:
    if not title.strip():
        raise InvalidPoll("title is required")
    if duration_min <= 0:
        raise InvalidPoll("duration must be positive")
    if not (MIN_OPTIONS <= len(option_starts) <= MAX_OPTIONS):
        raise InvalidPoll(f"a poll needs between {MIN_OPTIONS} and {MAX_OPTIONS} options")
    if any(start.tzinfo is None for start in option_starts):
        raise InvalidPoll("option times must be timezone-aware")
    if len(set(option_starts)) != len(option_starts):
        raise InvalidPoll("option times must be distinct")
    delta = timedelta(minutes=duration_min)
    options = [(start, start + delta) for start in sorted(option_starts)]
    return await repo.create(
        owner_id,
        slug=_slugify(title),
        title=title.strip(),
        duration_min=duration_min,
        location_type=location_type,
        options=options,
    )


async def list_polls(repo: PollsRepository, owner_id: uuid.UUID) -> list[PollSummary]:
    return await repo.list_for_owner(owner_id)


async def get_poll(repo: PollsRepository, poll_id: uuid.UUID, owner_id: uuid.UUID) -> PollData:
    poll = await repo.get_for_owner(poll_id, owner_id)
    if poll is None:
        raise PollNotFound(str(poll_id))
    return poll


async def cancel_poll(repo: PollsRepository, poll_id: uuid.UUID, owner_id: uuid.UUID) -> None:
    if not await repo.cancel(poll_id, owner_id):
        raise PollNotFound(str(poll_id))


async def get_public_poll(repo: PollsRepository, slug: str) -> PollData:
    poll = await repo.get_by_slug(slug)
    if poll is None:
        raise PollNotFound(slug)
    return poll


async def cast_votes(
    repo: PollsRepository,
    slug: str,
    *,
    voter_name: str,
    voter_email: str,
    option_ids: list[uuid.UUID],
) -> None:
    poll = await repo.get_by_slug(slug)
    if poll is None:
        raise PollNotFound(slug)
    if poll.status != "open":
        raise PollNotOpen(slug)
    if not voter_name.strip() or not voter_email.strip():
        raise InvalidPoll("voter name and email are required")
    valid_ids = {o.id for o in poll.options}
    chosen = {oid for oid in option_ids if oid in valid_ids}
    if not chosen or len(chosen) != len(set(option_ids)):
        raise OptionNotInPoll("votes reference unknown options")
    await repo.replace_votes(
        poll.id,
        voter_name=voter_name.strip(),
        voter_email=voter_email.strip().lower(),
        option_ids=tuple(chosen),
    )


async def finalize_poll(
    repo: PollsRepository,
    mailer: EmailSender,
    poll_id: uuid.UUID,
    owner_id: uuid.UUID,
    option_id: uuid.UUID,
    *,
    notify: bool = True,
) -> PollData:
    poll = await repo.get_for_owner(poll_id, owner_id)
    if poll is None:
        raise PollNotFound(str(poll_id))
    if poll.status == "cancelled":
        raise PollNotOpen(str(poll_id))
    option = next((o for o in poll.options if o.id == option_id), None)
    if option is None:
        raise OptionNotInPoll(str(option_id))
    if not await repo.finalize(poll_id, owner_id, option_id):
        raise PollNotFound(str(poll_id))

    if notify:
        from ghostcal.application.notifications import send_poll_result

        for voter in poll.voters:
            await send_poll_result(
                mailer,
                to_email=voter.email,
                attendee_name=voter.name,
                poll_title=poll.title,
                owner_name=poll.owner_name,
                start_at=option.start_at,
                end_at=option.end_at,
                location_type=poll.location_type,
            )
    return await get_poll(repo, poll_id, owner_id)
