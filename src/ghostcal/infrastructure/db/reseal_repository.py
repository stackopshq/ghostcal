"""SQL implementation of the re-seal repository port (ADR-0007).

The three helpers are SECURITY DEFINER for the same reason the rotation one is: they read the
organization's current generation, and the guarantees that matter (only rows still behind are
written; nothing is written at all if the org rotated again) belong next to the data rather than in
an application that could be interrupted between two statements.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.reseal import (
    Backlog,
    PendingRecord,
    ResealedRecord,
    ResealRepository,
    RotatedUnderneath,
    SealedKind,
)
from ghostcal.infrastructure.db.session import bind_org


class SqlResealRepository(ResealRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def backlog(self, organization_id: uuid.UUID) -> Backlog:
        await bind_org(self._session, organization_id)
        row = (
            await self._session.execute(
                text(
                    "SELECT o.zk_key_generation AS generation, "
                    "count_pending_reseal(o.id) AS remaining "
                    "FROM organizations o WHERE o.id = :oid"
                ),
                {"oid": str(organization_id)},
            )
        ).one()
        return Backlog(generation=row.generation, remaining=row.remaining)

    async def pending(self, organization_id: uuid.UUID, *, limit: int) -> list[PendingRecord]:
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                text("SELECT kind, id, sealed FROM pending_reseal(:oid, :lim)"),
                {"oid": str(organization_id), "lim": limit},
            )
        ).all()
        return [PendingRecord(kind=_kind(r.kind), id=r.id, sealed=r.sealed) for r in rows]

    async def apply(
        self,
        organization_id: uuid.UUID,
        *,
        generation: int,
        records: list[ResealedRecord],
    ) -> int:
        await bind_org(self._session, organization_id)
        moved = 0
        try:
            for record in records:
                written = (
                    await self._session.execute(
                        text("SELECT apply_reseal(:oid, :gen, :kind, :id, :sealed)"),
                        {
                            "oid": str(organization_id),
                            "gen": generation,
                            "kind": record.kind,
                            "id": str(record.id),
                            "sealed": record.sealed,
                        },
                    )
                ).scalar_one()
                if written:
                    moved += 1
        except DBAPIError as exc:
            if "rotated again" in str(exc.orig):
                raise RotatedUnderneath(
                    "the organization key rotated again — refetch and re-seal"
                ) from exc
            raise
        return moved


def _kind(value: str) -> SealedKind:
    if value not in ("booking", "event", "task"):
        raise ValueError(f"unknown sealed record kind: {value}")
    return value  # type: ignore[return-value]
