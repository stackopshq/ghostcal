"""SQL side of instance administration.

Every read and write of ``users`` here runs under the ``users_instance_admin_*`` policies, opened
by ``bind_instance_admin``. The repository binds it itself, in each method, rather than trusting a
caller to have done so: a missing declaration under FORCE ROW LEVEL SECURITY does not fail, it
returns no rows, and the view would show an empty instance as if that were the truth.

What is selected is the whole of what leaves: no key material, no password hash, no TOTP secret.

The tombstone user (``TOMBSTONE_USER_ID``) is not an account: it is the row erased accounts'
shared records are reassigned to. It never appears here, so it can be neither listed nor suspended
nor erased; erasing it would cascade through every record it holds.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.administration import AccountSummary, AdministrationRepository
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_instance_admin


def _summary_query() -> Select[tuple[Any, ...]]:
    two_factor = (
        exists()
        .where(
            models.UserTotp.user_id == models.User.id,
            models.UserTotp.confirmed_at.is_not(None),
        )
        .correlate(models.User)
    )
    return select(
        models.User.id,
        models.User.email,
        models.User.name,
        models.User.created_at,
        models.User.email_verified_at,
        models.User.last_login_at,
        models.User.suspended_at,
        two_factor.label("two_factor_enabled"),
    )


def _to_summary(row: object) -> AccountSummary:
    return AccountSummary(
        id=row.id,  # type: ignore[attr-defined]
        email=row.email,  # type: ignore[attr-defined]
        name=row.name,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        email_verified=row.email_verified_at is not None,  # type: ignore[attr-defined]
        last_login_at=row.last_login_at,  # type: ignore[attr-defined]
        two_factor_enabled=bool(row.two_factor_enabled),  # type: ignore[attr-defined]
        suspended_at=row.suspended_at,  # type: ignore[attr-defined]
    )


class SqlAdministrationRepository(AdministrationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_accounts(self) -> list[AccountSummary]:
        await bind_instance_admin(self._session)
        rows = await self._session.execute(
            _summary_query()
            .where(models.User.id != models.TOMBSTONE_USER_ID)
            .order_by(models.User.created_at)
        )
        return [_to_summary(row) for row in rows]

    async def get_account(self, user_id: uuid.UUID) -> AccountSummary | None:
        await bind_instance_admin(self._session)
        if user_id == models.TOMBSTONE_USER_ID:
            return None
        row = (
            await self._session.execute(_summary_query().where(models.User.id == user_id))
        ).first()
        return _to_summary(row) if row is not None else None

    async def set_suspended(self, user_id: uuid.UUID, suspended_at: datetime | None) -> None:
        await bind_instance_admin(self._session)
        await self._session.execute(
            update(models.User).where(models.User.id == user_id).values(suspended_at=suspended_at)
        )

    async def get_setting(self, key: str) -> str | None:
        return (
            await self._session.execute(
                select(models.InstanceSetting.value).where(models.InstanceSetting.key == key)
            )
        ).scalar_one_or_none()

    async def set_setting(self, key: str, value: str, now: datetime) -> None:
        stmt = insert(models.InstanceSetting).values(key=key, value=value, updated_at=now)
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[models.InstanceSetting.key],
                set_={"value": value, "updated_at": now},
            )
        )
