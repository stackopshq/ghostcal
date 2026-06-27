"""Availability-schedule management use cases (host dashboard).

Framework-free. A schedule belongs to a host (owner) inside an organization; the repository is
already organization-scoped (RLS), and every operation is additionally filtered by ``owner_id``
so a member only manages their own schedules.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ScheduleError(Exception):
    """Base class for schedule use-case errors."""


class ScheduleNotFound(ScheduleError):
    pass


class InvalidSchedule(ScheduleError):
    pass


@dataclass(frozen=True, slots=True)
class RuleData:
    weekday: int  # 0 = Monday
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class OverrideData:
    day: date
    is_available: bool
    start: time | None = None
    end: time | None = None


@dataclass(frozen=True, slots=True)
class ScheduleData:
    id: uuid.UUID
    name: str
    timezone: str
    rules: tuple[RuleData, ...]
    overrides: tuple[OverrideData, ...]


class SchedulesRepository:
    async def list_for_owner(self, owner_id: uuid.UUID) -> list[ScheduleData]:
        raise NotImplementedError

    async def get(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> ScheduleData | None:
        raise NotImplementedError

    async def create(
        self,
        owner_id: uuid.UUID,
        name: str,
        timezone: str,
        rules: Sequence[RuleData],
        overrides: Sequence[OverrideData],
    ) -> uuid.UUID:
        raise NotImplementedError

    async def update(
        self,
        schedule_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
        timezone: str,
        rules: Sequence[RuleData],
        overrides: Sequence[OverrideData],
    ) -> bool:
        """Return False if no schedule with that id belongs to the owner."""
        raise NotImplementedError

    async def delete(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        raise NotImplementedError


def _validate(timezone: str, rules: Sequence[RuleData], overrides: Sequence[OverrideData]) -> None:
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidSchedule(f"unknown timezone: {timezone}") from exc
    for rule in rules:
        if not 0 <= rule.weekday <= 6:
            raise InvalidSchedule("weekday must be between 0 (Monday) and 6 (Sunday)")
        if rule.start >= rule.end:
            raise InvalidSchedule("rule start must be before end")
    for override in overrides:
        if (
            override.is_available
            and override.start is not None
            and override.end is not None
            and override.start >= override.end
        ):
            raise InvalidSchedule("override start must be before end")


async def list_schedules(repo: SchedulesRepository, owner_id: uuid.UUID) -> list[ScheduleData]:
    return await repo.list_for_owner(owner_id)


async def get_schedule(
    repo: SchedulesRepository, schedule_id: uuid.UUID, owner_id: uuid.UUID
) -> ScheduleData:
    schedule = await repo.get(schedule_id, owner_id)
    if schedule is None:
        raise ScheduleNotFound(str(schedule_id))
    return schedule


async def create_schedule(
    repo: SchedulesRepository,
    owner_id: uuid.UUID,
    *,
    name: str,
    timezone: str,
    rules: Sequence[RuleData],
    overrides: Sequence[OverrideData],
) -> uuid.UUID:
    _validate(timezone, rules, overrides)
    return await repo.create(owner_id, name, timezone, rules, overrides)


async def update_schedule(
    repo: SchedulesRepository,
    schedule_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    name: str,
    timezone: str,
    rules: Sequence[RuleData],
    overrides: Sequence[OverrideData],
) -> None:
    _validate(timezone, rules, overrides)
    if not await repo.update(schedule_id, owner_id, name, timezone, rules, overrides):
        raise ScheduleNotFound(str(schedule_id))


async def delete_schedule(
    repo: SchedulesRepository, schedule_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    if not await repo.delete(schedule_id, owner_id):
        raise ScheduleNotFound(str(schedule_id))
