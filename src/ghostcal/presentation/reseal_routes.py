"""Backlog re-sealing endpoints (ADR-0007) — where a rotation actually finishes.

Rotating the org key stops the leak going forward. These endpoints let the admin's browser walk the
records sealed *before* the rotation, open each with the key that sealed it, and re-seal it to the
current one. When the backlog hits zero, the departed member's key opens nothing at all.

The server hands out ciphertext and takes ciphertext back. It cannot open either, and every blob it
receives it stores verbatim.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.reseal import (
    ResealedRecord,
    ResealService,
    RotatedUnderneath,
)
from ghostcal.infrastructure.db.reseal_repository import SqlResealRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import (
    BacklogOut,
    ResealIn,
    ResealOut,
    SealedRecordOut,
)

router = APIRouter(prefix="/v1/me/organization/reseal", tags=["reseal"])

MANAGER_ROLES = ("owner", "admin")


def _require_manager(member: Member) -> None:
    if member.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403, detail="only an owner or admin may re-seal the organization's records"
        )


@router.get("", response_model=BacklogOut)
async def backlog(member: Member = Depends(current_member)) -> BacklogOut:
    """How much history is still sealed under a retired key. Zero means the rotation is complete."""
    _require_manager(member)
    async with db_session() as session:
        result = await ResealService(SqlResealRepository(session)).backlog(member.organization_id)
    return BacklogOut(generation=result.generation, remaining=result.remaining)


@router.get("/pending", response_model=list[SealedRecordOut])
async def pending(
    limit: int = Query(default=50, ge=1, le=200),
    member: Member = Depends(current_member),
) -> list[SealedRecordOut]:
    """A batch of records still sealed under a retired key — ciphertext, for the browser to open."""
    _require_manager(member)
    async with db_session() as session:
        records = await ResealService(SqlResealRepository(session)).pending(
            member.organization_id, limit=limit
        )
    return [SealedRecordOut(kind=r.kind, id=r.id, sealed=r.sealed) for r in records]


@router.post("", response_model=ResealOut)
async def apply(payload: ResealIn, member: Member = Depends(current_member)) -> ResealOut:
    """Write a batch back, re-sealed to the current key.

    Refused (409) if the organization rotated again while the caller was working: their blobs are
    sealed to the previous key, and writing them would stamp them current and quietly strand them.

    Idempotent — the write only touches rows still behind the current generation, so a retried batch
    is a no-op rather than a corruption.
    """
    _require_manager(member)
    async with db_session() as session:
        service = ResealService(SqlResealRepository(session))
        try:
            applied = await service.apply(
                member.organization_id,
                generation=payload.generation,
                records=[
                    ResealedRecord(kind=r.kind, id=r.id, sealed=r.sealed) for r in payload.records
                ],
            )
        except RotatedUnderneath as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result = await service.backlog(member.organization_id)
    return ResealOut(applied=applied, remaining=result.remaining)
