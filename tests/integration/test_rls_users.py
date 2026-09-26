"""Ce que les politiques de `users` protègent, mesuré sans l'aide du code applicatif.

`test_rls.py` fait ceci pour les tables de locataire. `users` n'y était pas, parce que jusqu'à
`c1f4a90b7d33` elle ne portait aucune politique.

─── Pourquoi ce fichier existe, et pas seulement les tests de parcours ───

Les tests de parcours passent par les dépôts, et les dépôts posent leurs propres clauses `WHERE`.
Ils ne peuvent donc pas dire si une politique sert à quelque chose : ils resteraient verts sur une
table sans aucune politique du tout.

Vérifié le 2026-09-26, et c'est la raison d'être de ce fichier : en remplaçant `users_select` par
`USING (true)` — c'est-à-dire en supprimant *toute* isolation sur `users` — les 162 tests
d'intégration restaient **verts**. Une politique que rien ne fait rougir ne protège rien, et
personne ne s'en apercevrait avant la prochaine fuite.

Chaque test ci-dessous écrit donc la requête **sans sa clause `WHERE`**, exactement comme la
requête fautive du 2026-09-25 — `member_public_keys` rendait les utilisateurs de toutes les
organisations du serveur. C'est le seul geste qui interroge la politique elle-même plutôt que le
filtre applicatif posé par-dessus.

Chacun de ces tests rougit si l'on retire ou si l'on élargit la politique qu'il nomme. C'est la
propriété qu'ils existent pour tenir.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ghostcal.infrastructure.db.session import (
    bind_login_email,
    bind_user,
    db_session,
    org_session,
)

pytestmark = pytest.mark.integration


@dataclass
class Deux:
    org_a: uuid.UUID
    org_b: uuid.UUID
    alice: uuid.UUID  # membre de A
    bob: uuid.UUID  # membre de A, avec Alice
    mallory: uuid.UUID  # membre de B, et de rien d'autre
    mallory_email: str
    orphelin: uuid.UUID  # aucune adhésion, aucune ligne qui le référence


@pytest_asyncio.fixture
async def deux_orgs(admin_engine: AsyncEngine) -> AsyncIterator[Deux]:
    """Deux organisations, trois comptes : deux collègues d'un côté, un étranger de l'autre."""
    suffix = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as conn:

        async def org(nom: str) -> uuid.UUID:
            return await conn.scalar(  # type: ignore[return-value]
                text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
                {"n": nom, "s": f"{nom.lower()}-{suffix}"},
            )

        async def compte(nom: str) -> uuid.UUID:
            return await conn.scalar(  # type: ignore[return-value]
                text(
                    "INSERT INTO users (email, name, timezone) VALUES (:e, :n, 'UTC') RETURNING id"
                ),
                {"e": f"{nom.lower()}-{suffix}@example.test", "n": nom},
            )

        async def adhesion(o: uuid.UUID, u: uuid.UUID) -> None:
            await conn.execute(
                text(
                    "INSERT INTO memberships (organization_id, user_id, role) "
                    "VALUES (:o, :u, 'owner')"
                ),
                {"o": o, "u": u},
            )

        a, b = await org("Alpha"), await org("Beta")
        alice, bob, mallory = await compte("Alice"), await compte("Bob"), await compte("Mallory")
        # Sans adhésion et sans rien qui le référence : le seul compte dont on puisse changer
        # l'identifiant sans qu'une clé étrangère s'y oppose d'abord. C'est ce qui permet
        # d'éprouver le `WITH CHECK` de `users_update` pour lui-même — voir le test qui l'utilise.
        orphelin = await compte("Orphelin")
        await adhesion(a, alice)
        await adhesion(a, bob)
        await adhesion(b, mallory)

    deux = Deux(
        org_a=a,
        org_b=b,
        alice=alice,
        bob=bob,
        mallory=mallory,
        mallory_email=f"mallory-{suffix}@example.test",
        orphelin=orphelin,
    )
    try:
        yield deux
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM organizations WHERE id = ANY(:ids)"), {"ids": [a, b]}
            )
            await conn.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": [alice, bob, mallory, orphelin]},
            )


# ── Lecture ────────────────────────────────────────────────────────────────────────────


async def test_une_requete_sans_where_ne_voit_que_les_collegues(deux_orgs: Deux) -> None:
    """La fuite du 2026-09-25, rejouée : `SELECT … FROM users` sans filtre d'organisation.

    Trois requêtes l'avaient écrite ainsi et rendaient les comptes de tout le serveur. Sous
    `users_select`, la même requête ne rend que les membres de l'organisation déclarée.
    """
    async with org_session(deux_orgs.org_a) as session:
        vus = set((await session.execute(text("SELECT id FROM users"))).scalars().all())

    assert vus == {deux_orgs.alice, deux_orgs.bob}
    assert deux_orgs.mallory not in vus


async def test_une_session_sans_rien_declarer_ne_voit_aucun_compte(deux_orgs: Deux) -> None:
    """Refus par défaut, y compris sur une connexion du pool qui vient de servir une organisation.

    Même propriété que `test_unbound_session_sees_nothing_on_a_reused_connection`, sur `users` :
    un GUC transaction-local revient à la chaîne vide et non à « non défini », et une politique
    qui comparerait sans `NULLIF` lèverait au lieu de refuser.
    """
    async with org_session(deux_orgs.org_a) as session:
        await session.execute(text("SELECT id FROM users"))

    async with db_session() as session:
        vus = (await session.execute(text("SELECT id FROM users"))).scalars().all()

    assert vus == []


async def test_declarer_un_utilisateur_n_ouvre_que_sa_ligne(deux_orgs: Deux) -> None:
    """`bind_user` est ce que font seize des dix-sept chemins. Il n'ouvre pas l'organisation."""
    async with db_session() as session:
        await bind_user(session, deux_orgs.alice)
        vus = (await session.execute(text("SELECT id FROM users"))).scalars().all()

    assert vus == [deux_orgs.alice]


async def test_une_organisation_etrangere_ne_montre_personne(deux_orgs: Deux) -> None:
    async with org_session(deux_orgs.org_b) as session:
        vus = set((await session.execute(text("SELECT id FROM users"))).scalars().all())

    assert vus == {deux_orgs.mallory}
    assert not vus & {deux_orgs.alice, deux_orgs.bob}


# ── La politique de recherche par adresse ──────────────────────────────────────────────


async def test_l_adresse_declaree_ouvre_sa_ligne_et_elle_seule(deux_orgs: Deux) -> None:
    """Ce que la connexion a besoin de pouvoir faire, et rien de plus."""
    async with db_session() as session:
        await bind_login_email(session, deux_orgs.mallory_email)
        vus = (await session.execute(text("SELECT id FROM users"))).scalars().all()

    assert vus == [deux_orgs.mallory]


async def test_une_adresse_declaree_n_ouvre_pas_les_autres(deux_orgs: Deux) -> None:
    """La borne de `users_email_lookup` : une adresse, une ligne — jamais un annuaire.

    C'est la question qui décide si cette politique est acceptable. Si déclarer une adresse
    ouvrait autre chose que la ligne qui la porte, la migration aurait rouvert la fuite qu'elle
    prétend fermer.
    """
    async with db_session() as session:
        await bind_login_email(session, deux_orgs.mallory_email)
        vus = set((await session.execute(text("SELECT id FROM users"))).scalars().all())

    assert deux_orgs.alice not in vus
    assert deux_orgs.bob not in vus
    assert len(vus) == 1


async def test_la_casse_de_l_adresse_ne_change_pas_la_reponse(deux_orgs: Deux) -> None:
    """Une politique qui ouvrirait pour une casse et pas pour l'autre refuserait par intermittence,
    ce qui est plus difficile à diagnostiquer qu'un refus franc."""
    async with db_session() as session:
        await bind_login_email(session, deux_orgs.mallory_email.upper())
        vus = (await session.execute(text("SELECT id FROM users"))).scalars().all()

    assert vus == [deux_orgs.mallory]


# ── Écriture ───────────────────────────────────────────────────────────────────────────


async def test_un_update_sans_where_ne_touche_que_sa_propre_ligne(deux_orgs: Deux) -> None:
    """Le mode de défaillance le plus coûteux de cette table, dans les deux sens.

    Sans déclaration, l'`UPDATE` touche **zéro** ligne et ne lève rien : la vérification
    d'adresse, le profil et le trousseau réussissaient en apparence sans rien écrire.

    L'organisation est déclarée en plus de l'utilisateur, et ce n'est pas décoratif. Une
    politique `SELECT` borne déjà les lignes qu'un `UPDATE` peut atteindre, donc sous le seul
    `bind_user` la question ne se pose jamais : `users_select` n'en montre qu'une. C'est
    exactement la configuration qu'ont `store_member_key` et la rotation de clés — les deux GUC
    posés ensemble — et la seule où `users_update` décide de quelque chose que `users_select`
    n'a pas déjà décidé. Un test qui ne déclarerait que l'utilisateur resterait vert en
    remplaçant `users_update` par `USING (true)` : mesuré le 2026-09-26.
    """
    async with db_session() as session:
        touchees_sans_declaration = (
            await session.execute(text("UPDATE users SET timezone = 'Europe/Zurich'"))
        ).rowcount

    async with org_session(deux_orgs.org_a) as session:
        await bind_user(session, deux_orgs.alice)
        # Alice et Bob sont tous deux lisibles ici — ils partagent l'organisation déclarée.
        lisibles = set((await session.execute(text("SELECT id FROM users"))).scalars().all())
        modifiees = (
            await session.execute(text("UPDATE users SET timezone = 'Europe/Zurich'"))
        ).rowcount

    assert touchees_sans_declaration == 0
    assert lisibles == {deux_orgs.alice, deux_orgs.bob}
    assert modifiees == 1  # celle d'Alice, et pas celle de son collègue


async def test_on_ne_peut_pas_transformer_sa_ligne_en_celle_d_un_autre(deux_orgs: Deux) -> None:
    """Changer son propre identifiant est refusé — mais pas par la politique qu'on croit.

    Mesuré le 2026-09-26, et c'est la raison d'être de ce commentaire : en remplaçant le
    `WITH CHECK` de `users_update` par `true`, ce test reste **vert**. Ce n'est pas lui qui
    refuse. C'est `users_select` : quand une table porte des politiques de lecture, PostgreSQL
    exige que la ligne **après** écriture reste visible à qui l'écrit, et un identifiant tiré au
    hasard ne l'est plus. Vérifié en ouvrant `users_select` : l'écriture passe alors.

    Le `WITH CHECK` de `users_update` est donc aujourd'hui **redondant**, et aucun test ne peut
    l'isoler tant que `users_select` refuse en premier. Il reste défendable comme second verrou
    — il mordrait si `users_select` venait à s'élargir — mais il ne faut pas lui prêter une
    protection qu'il n'exerce pas : c'est ce genre de crédit non mérité qui laisse retirer une
    clause en croyant qu'une autre la couvre.

    Le compte orphelin est indispensable : sur Alice, la clé étrangère de `memberships`
    refuserait la première, et le test serait vert pour une troisième raison encore.
    """
    from sqlalchemy.exc import DBAPIError, ProgrammingError

    with pytest.raises((ProgrammingError, DBAPIError)):
        async with db_session() as session:
            await bind_user(session, deux_orgs.orphelin)
            await session.execute(
                text("UPDATE users SET id = gen_random_uuid() WHERE id = :soi"),
                {"soi": deux_orgs.orphelin},
            )


async def test_un_delete_sans_where_n_emporte_que_sa_propre_ligne(deux_orgs: Deux) -> None:
    """La suppression de compte tourne sans filtre d'organisation. `users_delete` est ce qui
    empêche un `DELETE FROM users` d'emporter les collègues avec soi.

    L'organisation est déclarée pour la même raison que dans le test d'`UPDATE` : sans elle,
    `users_select` ne laisse voir qu'une ligne et `users_delete` n'a plus rien à décider.
    """
    async with org_session(deux_orgs.org_a) as session:
        await bind_user(session, deux_orgs.alice)
        emportees = (await session.execute(text("DELETE FROM users"))).rowcount

    assert emportees == 1

    # Bob partageait l'organisation d'Alice et n'a pas bougé.
    async with org_session(deux_orgs.org_a) as session:
        restants = (await session.execute(text("SELECT id FROM users"))).scalars().all()
    assert restants == [deux_orgs.bob]


async def test_une_insertion_doit_etre_celle_qu_on_declare_etre(deux_orgs: Deux) -> None:
    """`users_insert` en `WITH CHECK (id = …)` : on n'insère pas une ligne pour quelqu'un d'autre.

    C'est ce qui oblige `provision_account` à engendrer l'identifiant, le déclarer, puis insérer
    avec — et ce qui fait que son `RETURNING` fonctionne.
    """
    from sqlalchemy.exc import DBAPIError, ProgrammingError

    # L'adresse est unique à chaque exécution, et ce n'est pas un détail. Avec une adresse
    # fixe, la toute première fois que la politique laisse passer l'insertion, la ligne
    # **reste** — `db_session` valide — et la contrainte d'unicité refuse toutes les fois
    # suivantes. Le test redevient vert, pour une raison qui n'est plus la sienne, et il ne
    # rougira plus jamais. Constaté ici le 2026-09-26 en jouant la mutation deux fois.
    intrus = f"intrus-{uuid.uuid4().hex[:8]}@example.test"

    with pytest.raises((ProgrammingError, DBAPIError)):
        async with db_session() as session:
            await bind_user(session, deux_orgs.alice)
            await session.execute(
                text(
                    "INSERT INTO users (id, email, name, timezone) "
                    "VALUES (gen_random_uuid(), :e, 'Intrus', 'UTC')"
                ),
                {"e": intrus},
            )
