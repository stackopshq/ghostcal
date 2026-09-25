"""SQL implementation of the analytics repository.

Chaque requête porte son propre filtre d'organisation. Ce fichier annonçait
« org-scoped via RLS / org_session » et s'en tenait là : aucune de ses six requêtes ne
nommait l'organisation, alors que le dépôt en reçoit l'identifiant au constructeur.

Mesuré le 2026-09-25 : la production tourne en `postgres`, superutilisateur, qui contourne
toute politique de sécurité au niveau ligne — même sous `FORCE ROW LEVEL SECURITY`.
`/v1/me/analytics` comptait donc les réservations de **tout le serveur**, et sa ventilation
par type de rendez-vous rendait les **titres des types d'autres organisations** avec leurs
volumes. C'est de la donnée métier : ce que vend le voisin, et combien.

La docstring disait la vérité sur l'intention et rien sur le résultat. C'est exactement ce
qu'une isolation déléguée à la couche du dessous produit quand la couche du dessous ne
tient pas : le code a l'air correct, et il l'est — sous une hypothèse que personne ne
vérifie.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.analytics import (
    AnalyticsRepository,
    AnalyticsSummary,
    DayCount,
    EventTypeCount,
)


class SqlAnalyticsRepository(AnalyticsRepository):
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._org_id = organization_id

    async def _scalar(self, sql: str, params: dict[str, object]) -> int:
        return int((await self._session.execute(text(sql), params)).scalar_one())

    async def summary(self, now: datetime) -> AnalyticsSummary:
        cutoff = now - timedelta(days=30)
        org = {"org": str(self._org_id)}
        total = await self._scalar(
            "SELECT count(*) FROM bookings "
            "WHERE status = 'confirmed' AND organization_id = :org",
            org,
        )
        upcoming = await self._scalar(
            "SELECT count(*) FROM bookings "
            "WHERE status = 'confirmed' AND organization_id = :org AND start_at > :now",
            {**org, "now": now},
        )
        last30 = await self._scalar(
            "SELECT count(*) FROM bookings "
            "WHERE status = 'confirmed' AND organization_id = :org AND created_at >= :c",
            {**org, "c": cutoff},
        )
        cancels = await self._scalar(
            "SELECT count(*) FROM bookings "
            "WHERE status = 'cancelled' AND organization_id = :org AND start_at >= :c",
            {**org, "c": cutoff},
        )

        by_event_rows = (
            await self._session.execute(
                text(
                    "SELECT et.title AS title, count(*) AS n "
                    "FROM bookings b JOIN event_types et ON et.id = b.event_type_id "
                    "WHERE b.status = 'confirmed' AND b.organization_id = :org "
                    "GROUP BY et.title ORDER BY n DESC LIMIT 8"
                ),
                org,
            )
        ).all()

        daily_rows = (
            await self._session.execute(
                text(
                    "SELECT (start_at AT TIME ZONE 'UTC')::date AS d, count(*) AS n "
                    "FROM bookings WHERE status = 'confirmed' AND organization_id = :org "
                    "AND start_at >= :from_ AND start_at < :to_ "
                    "GROUP BY d ORDER BY d"
                ),
                {**org, "from_": now - timedelta(days=7), "to_": now + timedelta(days=8)},
            )
        ).all()

        return AnalyticsSummary(
            total_bookings=total,
            upcoming_bookings=upcoming,
            bookings_last_30_days=last30,
            cancellations_last_30_days=cancels,
            by_event_type=[EventTypeCount(title=r.title, count=r.n) for r in by_event_rows],
            daily=[DayCount(day=r.d.isoformat(), count=r.n) for r in daily_rows],
        )
