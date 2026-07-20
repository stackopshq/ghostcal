"""SQL sink for the audit log.

Org-scoped rows go in directly under RLS. Account-level rows (a login, an account deletion) belong
to no organization, so the tenant policy would reject them on a plain session — they go through the
``record_account_audit_event`` SECURITY DEFINER function, which can write exactly that shape and
nothing else.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.infrastructure.db import models


class SqlAuditSink:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: str,
        organization_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        target: str | None,
        details: dict[str, object],
    ) -> None:
        if organization_id is None:
            await self._session.execute(
                text(
                    "SELECT record_account_audit_event("
                    "CAST(:actor AS uuid), :action, :target, CAST(:details AS jsonb))"
                ),
                {
                    "actor": str(actor_user_id) if actor_user_id else None,
                    "action": action,
                    "target": target,
                    "details": json.dumps(details, default=str),
                },
            )
            return

        await self._session.execute(
            insert(models.AuditEvent).values(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action=action,
                target=target,
                details=details,
            )
        )
