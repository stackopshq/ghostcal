"""SQL implementation of the rotation repository port (ADR-0007).

The flip goes through the ``rotate_org_key`` SECURITY DEFINER function. It has to: the completeness
check reads ``memberships`` and ``users``, and the guarantee that matters — the new per-member keys
and the new public key land together or not at all — belongs in one place, next to the data, not
spread across an application that could be interrupted between two statements.

Its PostgreSQL exceptions are mapped back to the domain errors here, so the caller learns *who* was
left behind rather than reading a SQLSTATE.
"""

from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.rotation import (
    MembersLeftBehind,
    NotAMember,
    NotAuthorized,
    RotationRepository,
    SealedMemberKey,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_org

_LEFT_BEHIND = re.compile(r"no new key provided for: (.+)")
_NOT_A_MEMBER = re.compile(r"not a member of this organization: (.+)")


class SqlRotationRepository(RotationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def members_without_keypair(self, organization_id: uuid.UUID) -> list[str]:
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                select(models.User.email)
                .join(models.Membership, models.Membership.user_id == models.User.id)
                .where(
                    # Même défaut que `keypairs_repository.member_public_keys`, trouvé par
                    # l'audit du 2026-09-25 : la jointure s'en remettait au seul `bind_org`,
                    # donc à la RLS, et rendait les utilisateurs de **toutes** les
                    # organisations du serveur.
                    #
                    # Les deux sont les seules jointures vers `memberships` du code, et
                    # toutes deux l'avaient oublié. Ce n'est pas une inattention isolée :
                    # c'est ce que produit une isolation dont on croit qu'elle est acquise
                    # par la couche du dessous.
                    #
                    # Celle-ci est la plus lourde de conséquences des deux. Son résultat
                    # **refuse une rotation de clé d'organisation** : un membre d'une autre
                    # organisation sans paire de clés bloquait la rotation ici, et le
                    # message nommait son adresse à quelqu'un qui n'avait pas à la
                    # connaître.
                    models.Membership.organization_id == organization_id,
                    models.User.zk_public_key.is_(None),
                )
                .order_by(models.User.email)
            )
        ).all()
        return [r.email for r in rows]

    async def rotate(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        public_key: str,
        member_keys: list[SealedMemberKey],
    ) -> int:
        payload = json.dumps({str(k.user_id): k.sealed_org_key for k in member_keys})
        try:
            generation = (
                await self._session.execute(
                    text("SELECT rotate_org_key(:oid, :aid, :pk, CAST(:keys AS jsonb))"),
                    {
                        "oid": str(organization_id),
                        "aid": str(actor_id),
                        "pk": public_key,
                        "keys": payload,
                    },
                )
            ).scalar_one()
        except DBAPIError as exc:
            raise _translate(exc) from exc
        return int(generation)


def _translate(exc: DBAPIError) -> Exception:
    message = str(exc.orig)
    if "not authorized to rotate" in message:
        return NotAuthorized("only an owner or an admin may rotate the organization key")
    left_behind = _LEFT_BEHIND.search(message)
    if left_behind:
        return MembersLeftBehind([e.strip() for e in left_behind.group(1).split(",")])
    not_a_member = _NOT_A_MEMBER.search(message)
    if not_a_member:
        return NotAMember(f"not a member of this organization: {not_a_member.group(1)}")
    return exc
