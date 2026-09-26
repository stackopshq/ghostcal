"""SQL implementation of the per-user keypair repository port (ADR-0007).

``users`` **was** a global (non-RLS) table; since ``c1f4a90b7d33`` it carries FORCE ROW LEVEL
SECURITY and four policies. Every method here therefore declares the user it is about to touch
before touching it — the id is always the authenticated caller's, so declaring it grants nothing
the caller did not already hold. Listing an
organization's member public keys crosses from that global table into the tenant-scoped
``memberships``, so it runs under the org's GUC and RLS scopes the join for us: a caller can only
ever see the public keys of people they share an organization with.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ghostcal.application.keypairs import (
    KeypairRepository,
    MemberPublicKey,
    UserKeypair,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_org, bind_user


class SqlKeypairRepository(KeypairRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> UserKeypair | None:
        # `users` n'est plus une table globale : elle porte des politiques depuis
        # `c1f4a90b7d33`. Le docstring du module disait le contraire ; il est corrigé.
        await bind_user(self._session, user_id)
        row = (
            await self._session.execute(
                select(
                    models.User.zk_public_key,
                    models.User.zk_wrapped_private_key,
                    models.User.zk_wrap_salt,
                ).where(models.User.id == user_id)
            )
        ).first()
        if row is None or row.zk_public_key is None:
            return None
        return UserKeypair(
            public_key=row.zk_public_key,
            wrapped_private_key=row.zk_wrapped_private_key,
            wrap_salt=row.zk_wrap_salt,
        )

    async def set(self, user_id: uuid.UUID, keypair: UserKeypair) -> bool:
        # ─── Déclarer AVANT d'écrire, sinon l'échec ment ───
        #
        # La règle « une seule fois » est portée par le `WHERE`, et le service lit le nombre de
        # lignes touchées pour savoir si elle a mordu. Sous `users_update`, un `UPDATE` non
        # déclaré touche zéro ligne — indiscernable d'une clé déjà posée.
        #
        # Le service traduisait donc ce zéro en `KeypairAlreadySet` sur un compte qui n'avait
        # jamais eu de clé, pendant que `get()` jurait qu'il n'existait pas. La lecture dit
        # « absent », l'écriture dit « existe déjà » : c'est la même ligne, vue deux fois à
        # travers la même politique manquante.
        await bind_user(self._session, user_id)
        # Write-once, enforced in the WHERE clause rather than by a read-then-write: two logins
        # racing each other must not end with one user's keypair overwriting the other's, stranding
        # whatever was already sealed to the loser.
        result = await self._session.execute(
            update(models.User)
            .where(models.User.id == user_id, models.User.zk_public_key.is_(None))
            .values(
                zk_public_key=keypair.public_key,
                zk_wrapped_private_key=keypair.wrapped_private_key,
                zk_wrap_salt=keypair.wrap_salt,
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def rewrap(
        self, user_id: uuid.UUID, *, public_key: str, wrapped_private_key: str, wrap_salt: str
    ) -> bool:
        # Même raison que dans `set` : sans déclaration, zéro ligne touchée, et l'appelant
        # conclut « ce n'est pas votre trousseau » sur un trousseau qui est bien le sien.
        await bind_user(self._session, user_id)
        # `zk_public_key` is in the WHERE clause and NOT in the SET clause. That is the whole
        # difference from `set` above: the write-once rule exists to stop a public key changing,
        # and this statement cannot change one. Matching it also proves the caller is re-wrapping
        # the keypair that is actually stored — a browser holding a stale one updates nothing.
        result = await self._session.execute(
            update(models.User)
            .where(models.User.id == user_id, models.User.zk_public_key == public_key)
            .values(zk_wrapped_private_key=wrapped_private_key, zk_wrap_salt=wrap_salt)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def member_public_keys(self, organization_id: uuid.UUID) -> list[MemberPublicKey]:
        # ─── Le filtre d'organisation est ici, pas seulement dans la RLS ───
        #
        # Cette requête s'en remettait au seul `bind_org`, c'est-à-dire à la sécurité au
        # niveau ligne de PostgreSQL. Mesuré en production le 2026-09-25 : elle rendait
        # **les utilisateurs de toutes les organisations du serveur**, avec leur nom, leur
        # adresse et leur clé publique.
        #
        # Le symptôme, côté écran : « ces membres n'ont pas encore de clé de chiffrement »
        # nommait des comptes d'autres organisations. On lit d'abord une erreur d'affichage,
        # alors que c'est la réponse du serveur qui déborde.
        #
        # `/members`, servie par `org_repository`, filtrait correctement — d'où un écran
        # qui montrait un membre et un autre qui en montrait trois, sur la même
        # organisation. C'est ce désaccord qui a mis sur la piste.
        #
        # `org_repository` pose ce filtre explicitement à sept endroits. Celui-ci était le
        # seul à ne pas le faire. La RLS reste la seconde barrière, et c'est son rôle : une
        # défense qui dépend d'une politique pour être correcte se casse dès qu'une
        # politique permissive est ajoutée ailleurs — `memberships_self_read` en est une, et
        # PostgreSQL combine les politiques permissives par OU.
        await bind_org(self._session, organization_id)
        rows = (
            await self._session.execute(
                select(
                    models.User.id,
                    models.User.name,
                    models.User.email,
                    models.User.zk_public_key,
                )
                .join(models.Membership, models.Membership.user_id == models.User.id)
                .where(models.Membership.organization_id == organization_id)
                .order_by(models.User.name)
            )
        ).all()
        return [
            MemberPublicKey(user_id=r.id, name=r.name, email=r.email, public_key=r.zk_public_key)
            for r in rows
        ]
