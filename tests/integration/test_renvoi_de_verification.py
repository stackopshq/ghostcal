"""La sortie d'un cul-de-sac : renvoyer le courriel de vérification.

POURQUOI CE FICHIER EXISTE
--------------------------
Un compte dont le courriel de vérification s'était perdu était **définitivement
inutilisable**, et par trois portes fermées en même temps :

    connexion            403 « email not verified »
    réinscription        409 « email already registered »
    mot de passe oublié  n'envoie RIEN à une adresse non vérifiée, et c'est VOULU :
                         le lien est une preuve de contrôle de la boîte

Le courriel se perd pour des raisons ordinaires — un filtre anti-spam, un refus du
prestataire, une file de messages indisponible au moment de la mise en file. Aucune ne
justifiait de condamner le compte, et aucune n'était réparable sans accès à la base.

CE QUE CES TESTS SURVEILLENT
----------------------------
Les trois règles, dont deux sont des règles de sécurité et non de confort : le 202 est
inconditionnel (sinon la route devient un oracle d'énumération de comptes), et rien ne part
vers une adresse DÉJÀ vérifiée (sinon un tiers encombre la boîte de n'importe qui). Le
troisième test va jusqu'au bout : le jeton renvoyé vérifie vraiment le compte, et la
connexion qui rendait 403 rend ensuite des jetons.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.infrastructure.db.session import db_session

from .conftest import ZK_PLACEHOLDER
from .test_auth import CapturingMailer, _service

pytestmark = pytest.mark.integration

MOT_DE_PASSE = "un-mot-de-passe-de-banc-42"


async def _compte_non_verifie(adresse: str) -> uuid.UUID:
    facteur = CapturingMailer()
    async with db_session() as s:
        return await _service(s, facteur).register(
            email=adresse, name="Alice", password=MOT_DE_PASSE, zk_keys=ZK_PLACEHOLDER
        )


async def _nettoyer(engine: AsyncEngine, user_id: uuid.UUID) -> None:
    maker = async_sessionmaker(engine)
    async with maker() as s:
        org = (
            await s.execute(
                text("SELECT organization_id FROM memberships WHERE user_id = :u"), {"u": user_id}
            )
        ).scalar()
        if org is not None:
            await s.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})
        await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        await s.commit()


@pytest.mark.asyncio
async def test_le_renvoi_rouvre_un_compte_dont_le_courriel_s_est_perdu(
    admin_engine: AsyncEngine,
) -> None:
    adresse = f"perdu-{uuid.uuid4().hex[:8]}@stackops.ch"
    user_id = await _compte_non_verifie(adresse)
    try:
        # Le premier courriel est réputé perdu : on ne s'en sert pas. C'est tout le scénario.
        facteur = CapturingMailer()
        async with db_session() as s:
            await _service(s, facteur).resend_verification(email=adresse)
        assert facteur.last_html is not None, "aucun second courriel : le compte reste condamné"

        async with db_session() as s:
            await _service(s, facteur).verify_email(token=facteur.token())

        # La porte qui rendait 403 s'ouvre.
        async with db_session() as s:
            jetons = await _service(s, facteur).login(email=adresse, password=MOT_DE_PASSE)
        assert jetons.access_token
    finally:
        await _nettoyer(admin_engine, user_id)


@pytest.mark.asyncio
async def test_une_adresse_inconnue_ne_dit_rien_et_n_envoie_rien(admin_engine: AsyncEngine) -> None:
    # Pas d'exception, pas de courriel : la réponse doit être indiscernable du cas connu, sinon
    # la route énumère les comptes pour qui la sonde.
    facteur = CapturingMailer()
    async with db_session() as s:
        await _service(s, facteur).resend_verification(
            email=f"jamais-vu-{uuid.uuid4().hex[:8]}@stackops.ch"
        )
    assert facteur.last_html is None


@pytest.mark.asyncio
async def test_une_adresse_deja_verifiee_ne_recoit_rien(admin_engine: AsyncEngine) -> None:
    # Sans cette règle, n'importe qui encombre la boîte de n'importe quel compte vérifié, à
    # raison d'un courriel par appel.
    adresse = f"deja-{uuid.uuid4().hex[:8]}@stackops.ch"
    user_id = await _compte_non_verifie(adresse)
    try:
        premier = CapturingMailer()
        async with db_session() as s:
            await _service(s, premier).resend_verification(email=adresse)
        async with db_session() as s:
            await _service(s, premier).verify_email(token=premier.token())

        second = CapturingMailer()
        async with db_session() as s:
            await _service(s, second).resend_verification(email=adresse)
        assert second.last_html is None, "un compte vérifié n'a plus rien à vérifier"
    finally:
        await _nettoyer(admin_engine, user_id)
