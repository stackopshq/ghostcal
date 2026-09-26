"""Le compteur d'essais ratés du second facteur survit-il à l'échec qui le crée ?

Ce fichier existe à cause d'un défaut mesuré contre un vrai PostgreSQL le 2026-09-26, et qui
ne pouvait PAS être vu autrement.

`db_session` valide à la sortie propre et **annule sur exception**. `TwoFactorService._fail`
écrivait `failed_attempts` juste avant que `_verify` lève `TwoFactorInvalid` : dans la
transaction de la requête, l'incrément repartait donc à chaque fois. Après onze codes faux, la
base affichait toujours `failed_attempts = 0`. Posé à 4 à la main, un douzième échec le
laissait à 4.

Conséquence : `locked_until` n'était jamais écrit, `TwoFactorLocked` jamais levée, et le
verrouillage à cinq essais — la seule défense PAR COMPTE contre le balayage d'un code à six
chiffres — entièrement inerte. Restait le limiteur par IP, qui protège une adresse, pas un
compte.

Tout le reste fonctionnait, et c'est ce qui rendait le défaut invisible : la route rend bien un
429 avec `locked_until` quand la base porte un verrou, et l'écran sait le lire. Un test à dépôt
simulé passait au vert, puisqu'une maquette n'annule rien. **Seule une vraie transaction, avec
une vraie exception qui la traverse, montre le trou.**
"""

from __future__ import annotations

import uuid

import pyotp
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ghostcal.application.two_factor import (
    MAX_FAILED_ATTEMPTS,
    TwoFactorInvalid,
    TwoFactorLocked,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.session import bind_user, db_session

from .test_auth import _two_factor

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def compte_a_second_facteur():
    """Un compte dont le second facteur est ACTIVÉ, par le vrai service.

    L'enrôlement passe par `begin_enrolment` puis `activate` plutôt que par une ligne posée à
    la main : c'est l'état que produit le produit, et un état fabriqué autrement ne prouverait
    rien du chemin réel.
    """
    suffixe = uuid.uuid4().hex[:8]
    # Par la connexion de l'APPLICATION, et non par le moteur d'administration : `users` porte
    # `FORCE ROW LEVEL SECURITY`, et le rôle propriétaire n'est pas superutilisateur — il y est
    # soumis comme les autres. C'est le chemin qu'emprunte l'inscription.
    # L'identifiant est tiré AVANT l'insertion : la politique `users_insert` exige
    # `id = app.current_user_id`, donc il faut se déclarer pour avoir le droit de naître.
    user_id = uuid.uuid4()
    async with db_session() as s:
        await bind_user(s, user_id)
        s.add(
            models.User(
                id=user_id, email=f"verrou-{suffixe}@stackops.ch", name="Verrou", timezone="UTC"
            )
        )

    async with db_session() as s:
        enrolement = await _two_factor(s).begin_enrolment(user_id, account="verrou@stackops.ch")
    async with db_session() as s:
        await _two_factor(s).activate(user_id, code=pyotp.TOTP(enrolement.secret).now())

    try:
        yield {"user_id": user_id, "secret": enrolement.secret}
    finally:
        async with db_session() as s:
            await bind_user(s, user_id)
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})


async def _compteur(engine: AsyncEngine, user_id: uuid.UUID) -> tuple[int, object]:
    maker = async_sessionmaker(engine)
    async with maker() as s:
        row = (
            await s.execute(
                text("SELECT failed_attempts, locked_until FROM user_totp WHERE user_id = :u"),
                {"u": user_id},
            )
        ).one()
    return int(row[0]), row[1]


@pytest.mark.asyncio
async def test_un_echec_survit_a_l_exception_qui_le_signale(
    admin_engine: AsyncEngine, compte_a_second_facteur: dict[str, object]
) -> None:
    user_id = compte_a_second_facteur["user_id"]
    assert isinstance(user_id, uuid.UUID)

    # UN seul code faux. L'exception traverse `db_session`, qui annule la transaction :
    # c'est exactement là que l'incrément se perdait.
    with pytest.raises(TwoFactorInvalid):
        async with db_session() as s:
            await _two_factor(s).enforce_at_login(user_id, code="000000")

    essais, verrou = await _compteur(admin_engine, user_id)
    assert essais == 1, (
        "l'échec n'a pas été compté : il a été annulé avec la transaction de la requête, "
        "donc le verrouillage ne peut jamais se déclencher"
    )
    assert verrou is None, "un seul échec ne doit pas verrouiller"


@pytest.mark.asyncio
async def test_le_verrou_tombe_au_seuil_et_refuse_meme_un_bon_code(
    admin_engine: AsyncEngine, compte_a_second_facteur: dict[str, object]
) -> None:
    user_id = compte_a_second_facteur["user_id"]
    secret = compte_a_second_facteur["secret"]
    assert isinstance(user_id, uuid.UUID) and isinstance(secret, str)

    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(TwoFactorInvalid):
            async with db_session() as s:
                await _two_factor(s).enforce_at_login(user_id, code="000000")

    essais, verrou = await _compteur(admin_engine, user_id)
    assert essais == MAX_FAILED_ATTEMPTS
    assert verrou is not None, "le seuil atteint doit poser un verrou"

    # Un compte verrouillé ne doit pas servir d'oracle : même le BON code est refusé, et par
    # `TwoFactorLocked` et non `TwoFactorInvalid`, pour que l'écran dise « attendez » plutôt
    # que « recommencez ».
    with pytest.raises(TwoFactorLocked):
        async with db_session() as s:
            await _two_factor(s).enforce_at_login(user_id, code=pyotp.TOTP(secret).now())
