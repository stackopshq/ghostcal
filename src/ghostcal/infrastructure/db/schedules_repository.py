"""SQL implementation of the schedules repository port.

Bound to an organization-scoped session (RLS) and that org's id. Operations are additionally
filtered by ``owner_id`` so a member only ever touches their own schedules.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.schedules import (
    OverrideData,
    RuleData,
    ScheduleData,
    SchedulesRepository,
)
from ghostcal.infrastructure.db import models


class SqlSchedulesRepository(SchedulesRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[ScheduleData]:
        schedule_rows = (
            (
                await self._session.execute(
                    select(models.AvailabilitySchedule)
                    .where(models.AvailabilitySchedule.owner_id == owner_id)
                    .order_by(models.AvailabilitySchedule.created_at)
                )
            )
            .scalars()
            .all()
        )
        ids = [s.id for s in schedule_rows]
        rules_by_schedule = await self._rules_for(ids)
        overrides_by_schedule = await self._overrides_for(ids)
        return [
            _to_data(s, rules_by_schedule.get(s.id, []), overrides_by_schedule.get(s.id, []))
            for s in schedule_rows
        ]

    async def get(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> ScheduleData | None:
        schedule_row = (
            await self._session.execute(
                select(models.AvailabilitySchedule).where(
                    models.AvailabilitySchedule.id == schedule_id,
                    models.AvailabilitySchedule.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if schedule_row is None:
            return None
        rules = (await self._rules_for([schedule_id])).get(schedule_id, [])
        overrides = (await self._overrides_for([schedule_id])).get(schedule_id, [])
        return _to_data(schedule_row, rules, overrides)

    async def create(
        self,
        owner_id: uuid.UUID,
        name: str,
        timezone: str,
        rules: Sequence[RuleData],
        overrides: Sequence[OverrideData],
    ) -> uuid.UUID:
        schedule_id = (
            await self._session.execute(
                insert(models.AvailabilitySchedule)
                .values(
                    organization_id=self._org_id,
                    owner_id=owner_id,
                    name=name,
                    timezone=timezone,
                )
                .returning(models.AvailabilitySchedule.id)
            )
        ).scalar_one()
        await self._insert_children(schedule_id, rules, overrides)
        return schedule_id

    async def update(
        self,
        schedule_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
        timezone: str,
        rules: Sequence[RuleData],
        overrides: Sequence[OverrideData],
    ) -> bool:
        owns = (
            await self._session.execute(
                select(models.AvailabilitySchedule.id).where(
                    models.AvailabilitySchedule.id == schedule_id,
                    models.AvailabilitySchedule.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if owns is None:
            return False

        schedule = await self._session.get(models.AvailabilitySchedule, schedule_id)
        assert schedule is not None
        schedule.name = name
        schedule.timezone = timezone
        # Replace rules and overrides wholesale (the editor sends the full set).
        await self._session.execute(
            delete(models.AvailabilityRule).where(
                models.AvailabilityRule.schedule_id == schedule_id
            )
        )
        await self._session.execute(
            delete(models.AvailabilityOverride).where(
                models.AvailabilityOverride.schedule_id == schedule_id
            )
        )
        await self._insert_children(schedule_id, rules, overrides)
        return True

    async def delete(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        deleted = (
            await self._session.execute(
                delete(models.AvailabilitySchedule)
                .where(
                    models.AvailabilitySchedule.id == schedule_id,
                    models.AvailabilitySchedule.owner_id == owner_id,
                )
                .returning(models.AvailabilitySchedule.id)
            )
        ).scalar_one_or_none()
        return deleted is not None

    async def _insert_children(
        self,
        schedule_id: uuid.UUID,
        rules: Sequence[RuleData],
        overrides: Sequence[OverrideData],
    ) -> None:
        if rules:
            await self._session.execute(
                insert(models.AvailabilityRule),
                [
                    {
                        "organization_id": self._org_id,
                        "schedule_id": schedule_id,
                        "weekday": r.weekday,
                        "start_time": r.start,
                        "end_time": r.end,
                    }
                    for r in rules
                ],
            )
        if overrides:
            await self._session.execute(
                insert(models.AvailabilityOverride),
                [
                    {
                        "organization_id": self._org_id,
                        "schedule_id": schedule_id,
                        "date": o.day,
                        "is_available": o.is_available,
                        "start_time": o.start,
                        "end_time": o.end,
                    }
                    for o in overrides
                ],
            )

    async def _rules_for(
        self, schedule_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[RuleData]]:
        if not schedule_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    select(models.AvailabilityRule).where(
                        models.AvailabilityRule.schedule_id.in_(schedule_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[uuid.UUID, list[RuleData]] = {}
        for row in rows:
            grouped.setdefault(row.schedule_id, []).append(
                RuleData(weekday=row.weekday, start=row.start_time, end=row.end_time)
            )
        return grouped

    async def _overrides_for(
        self, schedule_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[OverrideData]]:
        if not schedule_ids:
            return {}
        rows = (
            (
                await self._session.execute(
                    select(models.AvailabilityOverride).where(
                        models.AvailabilityOverride.schedule_id.in_(schedule_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[uuid.UUID, list[OverrideData]] = {}
        for row in rows:
            grouped.setdefault(row.schedule_id, []).append(
                OverrideData(
                    day=row.date,
                    is_available=row.is_available,
                    start=row.start_time,
                    end=row.end_time,
                )
            )
        return grouped


def _to_data(
    schedule: models.AvailabilitySchedule,
    rules: list[RuleData],
    overrides: list[OverrideData],
) -> ScheduleData:
    return ScheduleData(
        id=schedule.id,
        name=schedule.name,
        timezone=schedule.timezone,
        rules=tuple(sorted(rules, key=lambda r: (r.weekday, r.start))),
        overrides=tuple(sorted(overrides, key=lambda o: o.day)),
    )
