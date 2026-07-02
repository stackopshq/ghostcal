"""SQL adapters for event attendees (org-scoped) and the public RSVP gateway (SECURITY DEFINER)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.attendees import (
    AttendeeRecord,
    AttendeeRepository,
    InvitationGateway,
    InvitationPreview,
)
from ghostcal.infrastructure.db import models


class SqlAttendeeRepository(AttendeeRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def owns_event(self, owner_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        row = (
            await self._session.execute(
                select(models.CalendarEvent.id).where(
                    models.CalendarEvent.id == event_id,
                    models.CalendarEvent.owner_id == owner_id,
                )
            )
        ).first()
        return row is not None

    async def add(
        self, event_id: uuid.UUID, *, email: str, name: str | None, token_hash: str
    ) -> uuid.UUID:
        return (
            await self._session.execute(
                insert(models.EventAttendee)
                .values(
                    organization_id=self._org_id,
                    event_id=event_id,
                    email=email,
                    name=name,
                    token_hash=token_hash,
                )
                .returning(models.EventAttendee.id)
            )
        ).scalar_one()

    async def list_for_event(self, event_id: uuid.UUID) -> list[AttendeeRecord]:
        rows = (
            await self._session.execute(
                select(
                    models.EventAttendee.id,
                    models.EventAttendee.email,
                    models.EventAttendee.name,
                    models.EventAttendee.status,
                )
                .where(models.EventAttendee.event_id == event_id)
                .order_by(models.EventAttendee.created_at)
            )
        ).all()
        return [AttendeeRecord(id=r.id, email=r.email, name=r.name, status=r.status) for r in rows]

    async def remove(self, event_id: uuid.UUID, attendee_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(models.EventAttendee).where(
                models.EventAttendee.id == attendee_id,
                models.EventAttendee.event_id == event_id,
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def token_for(self, event_id: uuid.UUID, attendee_id: uuid.UUID) -> str | None:
        return (
            await self._session.execute(
                select(models.EventAttendee.token_hash).where(
                    models.EventAttendee.id == attendee_id,
                    models.EventAttendee.event_id == event_id,
                )
            )
        ).scalar_one_or_none()


class SqlInvitationGateway(InvitationGateway):
    """Public RSVP path — no org context; uses the SECURITY DEFINER functions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def preview(self, token_hash: str) -> InvitationPreview | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT start_at, end_at, timezone, all_day, status "
                    "FROM event_invitation_preview(:h)"
                ),
                {"h": token_hash},
            )
        ).first()
        if row is None:
            return None
        return InvitationPreview(
            start_at=row.start_at,
            end_at=row.end_at,
            timezone=row.timezone,
            all_day=row.all_day,
            status=row.status,
        )

    async def respond(self, token_hash: str, status: str) -> bool:
        return bool(
            (
                await self._session.execute(
                    text("SELECT respond_to_event_invitation(:h, :s) AS ok"),
                    {"h": token_hash, "s": status},
                )
            ).scalar_one()
        )
