"""Implémentation SQL du dépôt du second facteur.

Hors RLS, comme `users` et `user_credentials` : une identité est antérieure à
toute organisation et n'appartient à aucun locataire.

Le secret traverse `EncryptedString`, donc il est chiffré en arrivant et
déchiffré en repartant sans que ce module ait à s'en occuper.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.two_factor import TotpRecord, TwoFactorRepository
from ghostcal.infrastructure.db import models


class SqlTwoFactorRepository(TwoFactorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> TotpRecord | None:
        row = (
            await self._session.execute(
                select(models.UserTotp).where(models.UserTotp.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return TotpRecord(
            user_id=row.user_id,
            secret=row.secret,
            confirmed_at=row.confirmed_at,
            last_counter=row.last_counter,
            failed_attempts=row.failed_attempts,
            locked_until=row.locked_until,
        )

    async def upsert_pending(self, user_id: uuid.UUID, secret: str) -> None:
        # Un enrôlement recommencé repart de zéro sur TOUTES les colonnes, pas
        # seulement le secret : garder l'ancien `last_counter` d'un secret
        # abandonné rejetterait les premiers codes du nouveau, et garder un
        # `locked_until` bloquerait un enrôlement neuf pour les échecs de l'ancien.
        stmt = pg_insert(models.UserTotp).values(
            user_id=user_id,
            secret=secret,
            confirmed_at=None,
            last_counter=0,
            failed_attempts=0,
            locked_until=None,
        )
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[models.UserTotp.user_id],
                set_={
                    "secret": stmt.excluded.secret,
                    "confirmed_at": None,
                    "last_counter": 0,
                    "failed_attempts": 0,
                    "locked_until": None,
                },
            )
        )

    async def confirm(self, user_id: uuid.UUID, when: datetime) -> None:
        await self._session.execute(
            update(models.UserTotp)
            .where(models.UserTotp.user_id == user_id)
            .values(confirmed_at=when)
        )

    async def delete(self, user_id: uuid.UUID) -> None:
        # Les codes de récupération partent avec : ils n'ouvrent rien sans second
        # facteur, et les laisser derrière ferait qu'un réenrôlement plus tard
        # hériterait d'une réserve que l'utilisateur croit périmée.
        await self._session.execute(
            delete(models.UserRecoveryCode).where(models.UserRecoveryCode.user_id == user_id)
        )
        await self._session.execute(
            delete(models.UserTotp).where(models.UserTotp.user_id == user_id)
        )

    async def record_success(self, user_id: uuid.UUID, *, last_counter: int) -> None:
        await self._session.execute(
            update(models.UserTotp)
            .where(models.UserTotp.user_id == user_id)
            .values(last_counter=last_counter, failed_attempts=0, locked_until=None)
        )

    async def record_failure(
        self, user_id: uuid.UUID, *, failed_attempts: int, locked_until: datetime | None
    ) -> None:
        await self._session.execute(
            update(models.UserTotp)
            .where(models.UserTotp.user_id == user_id)
            .values(failed_attempts=failed_attempts, locked_until=locked_until)
        )

    async def replace_recovery_codes(self, user_id: uuid.UUID, code_hashes: list[str]) -> None:
        await self._session.execute(
            delete(models.UserRecoveryCode).where(models.UserRecoveryCode.user_id == user_id)
        )
        if code_hashes:
            await self._session.execute(
                insert(models.UserRecoveryCode),
                [{"user_id": user_id, "code_hash": h} for h in code_hashes],
            )

    async def consume_recovery_code(self, user_id: uuid.UUID, code_hash: str) -> bool:
        # L'usage unique tient au `used_at IS NULL` de l'UPDATE, pas à une
        # lecture préalable : deux requêtes simultanées présentant le même code
        # passeraient toutes deux un test fait à la lecture, et une seule peut
        # gagner ici.
        result = await self._session.execute(
            update(models.UserRecoveryCode)
            .where(
                models.UserRecoveryCode.user_id == user_id,
                models.UserRecoveryCode.code_hash == code_hash,
                models.UserRecoveryCode.used_at.is_(None),
            )
            .values(used_at=func.now())
            .returning(models.UserRecoveryCode.id)
        )
        return result.scalar_one_or_none() is not None

    async def count_unused_recovery_codes(self, user_id: uuid.UUID) -> int:
        return (
            await self._session.execute(
                select(func.count())
                .select_from(models.UserRecoveryCode)
                .where(
                    models.UserRecoveryCode.user_id == user_id,
                    models.UserRecoveryCode.used_at.is_(None),
                )
            )
        ).scalar_one()
