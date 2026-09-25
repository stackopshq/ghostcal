"""Le second facteur TOTP : ce qu'un code juste ne suffit pas à établir.

Vérifier six chiffres est la partie facile, et c'est la seule que la
bibliothèque fait. Ce fichier éprouve tout le reste — l'anti-rejeu, la
limitation des essais, l'usage unique des codes de récupération, le parcours
d'activation — parce que c'est là que se logent les défauts qui ne se voient
pas : un second facteur cassé continue d'afficher un champ à six chiffres.

Les tests tiennent sans base de données : le dépôt est un double en mémoire qui
reproduit les seules garanties dont la politique dépend, notamment le fait
qu'un code de récupération ne peut être consommé qu'une fois.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient

from ghostcal.application.auth import (
    AuthConfig,
    AuthRepository,
    AuthService,
    AuthUserRecord,
    InvalidCredentials,
)
from ghostcal.application.two_factor import (
    LOCKOUT,
    MAX_FAILED_ATTEMPTS,
    RECOVERY_CODE_COUNT,
    TotpRecord,
    TwoFactorAlreadyEnabled,
    TwoFactorInvalid,
    TwoFactorLocked,
    TwoFactorNotEnrolled,
    TwoFactorRepository,
    TwoFactorRequired,
    TwoFactorService,
)
from ghostcal.infrastructure.db import models
from ghostcal.infrastructure.db.types import EncryptedString
from ghostcal.infrastructure.security.encryption import SecretBox
from ghostcal.infrastructure.security.totp import PERIOD_SECONDS, WINDOW, PyotpEngine
from ghostcal.presentation.api import create_app

DEBUT = datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)


class HorlogeMobile:
    """Une horloge qu'on avance à la main : le TOTP n'a de sens que dans le temps."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def avancer(self, delta: timedelta) -> None:
        self._instant += delta


class DepotEnMemoire(TwoFactorRepository):
    def __init__(self) -> None:
        self.record: TotpRecord | None = None
        # empreinte -> consommée ?
        self.codes: dict[str, bool] = {}
        self.codes_remplaces = 0

    async def get(self, user_id: uuid.UUID) -> TotpRecord | None:
        return self.record

    async def upsert_pending(self, user_id: uuid.UUID, secret: str) -> None:
        self.record = TotpRecord(
            user_id=user_id,
            secret=secret,
            confirmed_at=None,
            last_counter=0,
            failed_attempts=0,
            locked_until=None,
        )

    async def confirm(self, user_id: uuid.UUID, when: datetime) -> None:
        assert self.record is not None
        self.record = TotpRecord(**{**_as_dict(self.record), "confirmed_at": when})

    async def delete(self, user_id: uuid.UUID) -> None:
        self.record = None
        self.codes = {}

    async def record_success(self, user_id: uuid.UUID, *, last_counter: int) -> None:
        assert self.record is not None
        self.record = TotpRecord(
            **{
                **_as_dict(self.record),
                "last_counter": last_counter,
                "failed_attempts": 0,
                "locked_until": None,
            }
        )

    async def record_failure(
        self, user_id: uuid.UUID, *, failed_attempts: int, locked_until: datetime | None
    ) -> None:
        assert self.record is not None
        self.record = TotpRecord(
            **{
                **_as_dict(self.record),
                "failed_attempts": failed_attempts,
                "locked_until": locked_until,
            }
        )

    async def replace_recovery_codes(self, user_id: uuid.UUID, code_hashes: list[str]) -> None:
        self.codes_remplaces += 1
        self.codes = dict.fromkeys(code_hashes, False)

    async def consume_recovery_code(self, user_id: uuid.UUID, code_hash: str) -> bool:
        # L'usage unique est la garantie que la politique délègue au dépôt ; le
        # double doit donc la tenir, sinon les tests de rejeu ne prouvent rien.
        if self.codes.get(code_hash) is not False:
            return False
        self.codes[code_hash] = True
        return True

    async def count_unused_recovery_codes(self, user_id: uuid.UUID) -> int:
        return sum(1 for used in self.codes.values() if not used)


def _as_dict(r: TotpRecord) -> dict[str, object]:
    return {
        "user_id": r.user_id,
        "secret": r.secret,
        "confirmed_at": r.confirmed_at,
        "last_counter": r.last_counter,
        "failed_attempts": r.failed_attempts,
        "locked_until": r.locked_until,
    }


@pytest.fixture
def horloge() -> HorlogeMobile:
    return HorlogeMobile(DEBUT)


@pytest.fixture
def depot() -> DepotEnMemoire:
    return DepotEnMemoire()


@pytest.fixture
def service(depot: DepotEnMemoire, horloge: HorlogeMobile) -> TwoFactorService:
    return TwoFactorService(depot, PyotpEngine(), horloge)  # type: ignore[arg-type]


UTILISATEUR = uuid.UUID("11111111-1111-1111-1111-111111111111")


def code_pour(secret: str, quand: datetime) -> str:
    """Le code qu'afficherait l'application d'authentification à cet instant."""
    return pyotp.TOTP(secret).at(quand)


async def _activer(service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile):
    enrolment = await service.begin_enrolment(UTILISATEUR, account="kevin@stackops.ch")
    codes = await service.activate(UTILISATEUR, code=code_pour(enrolment.secret, horloge.now()))
    return enrolment.secret, codes


# --------------------------------------------------------------------------
# Le parcours d'activation
# --------------------------------------------------------------------------


async def test_un_enrolement_non_confirme_ne_garde_aucune_porte(
    service: TwoFactorService, depot: DepotEnMemoire
) -> None:
    """Fermer l'onglet du QR code ne doit pas verrouiller le compte.

    C'est le piège du parcours : le secret existe en base dès qu'on l'affiche.
    S'il gardait la porte tout de suite, quiconque abandonne à mi-chemin se
    retrouverait enfermé dehors par une application qu'il n'a jamais enrôlée.
    """
    await service.begin_enrolment(UTILISATEUR, account="kevin@stackops.ch")

    assert depot.record is not None and depot.record.confirmed_at is None
    # Aucune exception : la connexion passe comme avant.
    await service.enforce_at_login(UTILISATEUR, code=None)


async def test_l_activation_exige_un_code_juste(
    service: TwoFactorService, horloge: HorlogeMobile
) -> None:
    await service.begin_enrolment(UTILISATEUR, account="kevin@stackops.ch")

    with pytest.raises(TwoFactorInvalid):
        await service.activate(UTILISATEUR, code="000000")

    assert (await service.status(UTILISATEUR)).enabled is False


async def test_l_activation_rend_les_codes_de_recuperation_une_seule_fois(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    _, codes = await _activer(service, depot, horloge)

    assert len(codes) == RECOVERY_CODE_COUNT
    assert len(set(codes)) == RECOVERY_CODE_COUNT  # aucun doublon
    # Rien en clair côté dépôt : uniquement des empreintes.
    assert all(code not in depot.codes for code in codes)
    assert (await service.status(UTILISATEUR)).recovery_codes_remaining == RECOVERY_CODE_COUNT


async def test_activer_deux_fois_ne_remet_pas_le_secret_a_zero(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Proposer « activer » à qui l'a déjà couperait son application sans prévenir."""
    secret, _ = await _activer(service, depot, horloge)

    with pytest.raises(TwoFactorAlreadyEnabled):
        await service.begin_enrolment(UTILISATEUR, account="kevin@stackops.ch")

    assert depot.record is not None and depot.record.secret == secret


async def test_un_enrolement_repris_repart_de_zero(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Un enrôlement abandonné puis repris ne doit pas traîner les compteurs de l'ancien."""
    await service.begin_enrolment(UTILISATEUR, account="kevin@stackops.ch")
    await depot.record_failure(UTILISATEUR, failed_attempts=4, locked_until=None)

    await service.begin_enrolment(UTILISATEUR, account="kevin@stackops.ch")

    assert depot.record is not None
    assert depot.record.failed_attempts == 0
    assert depot.record.last_counter == 0


# --------------------------------------------------------------------------
# L'anti-rejeu
# --------------------------------------------------------------------------


async def test_un_code_deja_consomme_ne_repasse_pas(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Le défaut central : un code reste affiché trente secondes.

    Assez pour être lu par-dessus l'épaule, capté dans un journal ou rejoué par
    qui intercepte la requête. Sans anti-rejeu, le second facteur ne vaut que
    contre un attaquant qui n'a pas vu passer le code — c'est-à-dire pas contre
    l'hameçonnage, qui est la menace qu'il existe pour arrêter.
    """
    secret, _ = await _activer(service, depot, horloge)
    code = code_pour(secret, horloge.now())

    await service.enforce_at_login(UTILISATEUR, code=code)  # première fois : passe

    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code=code)  # rejeu : refusé


async def test_le_code_suivant_passe_apres_un_succes(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """L'anti-rejeu ne doit pas bloquer la connexion suivante, seulement la même."""
    secret, _ = await _activer(service, depot, horloge)
    await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, horloge.now()))

    horloge.avancer(timedelta(seconds=PERIOD_SECONDS * 2))
    await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, horloge.now()))


async def test_un_rejeu_compte_comme_un_essai_rate(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Sinon un attaquant rejoue un code capté à l'infini sans jamais déclencher le blocage."""
    secret, _ = await _activer(service, depot, horloge)
    code = code_pour(secret, horloge.now())
    await service.enforce_at_login(UTILISATEUR, code=code)

    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code=code)

    assert depot.record is not None and depot.record.failed_attempts == 1


async def test_un_code_anterieur_encore_dans_la_fenetre_ne_passe_pas_apres_coup(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """La tolérance d'horloge ne doit pas rouvrir la porte à la période précédente.

    Le code d'il y a trente secondes est encore « valide » au sens de RFC 6238.
    Il ne doit pourtant plus passer une fois le code suivant consommé, sans quoi
    la fenêtre de tolérance annule l'anti-rejeu.
    """
    secret, _ = await _activer(service, depot, horloge)
    precedent = code_pour(secret, horloge.now())

    horloge.avancer(timedelta(seconds=PERIOD_SECONDS))
    await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, horloge.now()))

    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code=precedent)


async def test_la_fenetre_de_tolerance_accepte_une_horloge_en_retard(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Un téléphone mal synchronisé doit pouvoir se connecter — c'est le cas courant."""
    secret, _ = await _activer(service, depot, horloge)
    en_retard = horloge.now() - timedelta(seconds=PERIOD_SECONDS * WINDOW)

    await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, en_retard))


async def test_au_dela_de_la_fenetre_le_code_est_refuse(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    secret, _ = await _activer(service, depot, horloge)
    trop_vieux = horloge.now() - timedelta(seconds=PERIOD_SECONDS * (WINDOW + 1))

    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, trop_vieux))


# --------------------------------------------------------------------------
# La limitation des essais
# --------------------------------------------------------------------------


async def test_le_compte_se_bloque_apres_les_essais_permis(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Six chiffres, c'est un million de possibilités. Sans compteur, elles s'essaient."""
    secret, _ = await _activer(service, depot, horloge)

    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(TwoFactorInvalid):
            await service.enforce_at_login(UTILISATEUR, code="000000")

    # Même le bon code ne passe plus : le blocage se teste avant toute comparaison,
    # pour qu'un compte bloqué ne serve pas d'oracle.
    with pytest.raises(TwoFactorLocked):
        await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, horloge.now()))


async def test_le_blocage_expire(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    secret, _ = await _activer(service, depot, horloge)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(TwoFactorInvalid):
            await service.enforce_at_login(UTILISATEUR, code="000000")

    horloge.avancer(LOCKOUT + timedelta(seconds=1))
    await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, horloge.now()))
    assert depot.record is not None and depot.record.failed_attempts == 0


async def test_apres_un_blocage_un_seul_echec_reverrouille(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Le compteur n'est pas remis à zéro par l'expiration du blocage.

    Volontairement sévère : passé le premier verrouillage, un attaquant n'a plus
    qu'un essai par quart d'heure au lieu de cinq. Le propriétaire du compte,
    lui, remet tout à zéro avec un seul code juste.
    """
    await _activer(service, depot, horloge)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(TwoFactorInvalid):
            await service.enforce_at_login(UTILISATEUR, code="000000")

    horloge.avancer(LOCKOUT + timedelta(seconds=1))
    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code="000000")

    assert depot.record is not None and depot.record.locked_until is not None
    with pytest.raises(TwoFactorLocked):
        await service.enforce_at_login(UTILISATEUR, code="000000")


async def test_un_code_juste_efface_les_essais_rates(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    secret, _ = await _activer(service, depot, horloge)
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(TwoFactorInvalid):
            await service.enforce_at_login(UTILISATEUR, code="000000")

    await service.enforce_at_login(UTILISATEUR, code=code_pour(secret, horloge.now()))

    assert depot.record is not None and depot.record.failed_attempts == 0


async def test_une_demande_de_code_ne_compte_pas_comme_un_essai_rate(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Le piège de la connexion en deux temps.

    Un client envoie d'abord le mot de passe seul, reçoit « il faut un code »,
    puis renvoie avec le code. Si le premier appel comptait comme un échec,
    cinq connexions parfaitement normales verrouilleraient le compte.
    """
    await _activer(service, depot, horloge)

    for _ in range(MAX_FAILED_ATTEMPTS * 2):
        with pytest.raises(TwoFactorRequired):
            await service.enforce_at_login(UTILISATEUR, code=None)

    assert depot.record is not None
    assert depot.record.failed_attempts == 0
    assert depot.record.locked_until is None


# --------------------------------------------------------------------------
# Les codes de récupération
# --------------------------------------------------------------------------


async def test_un_code_de_recuperation_ouvre_la_porte(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Sans eux, un téléphone perdu est un compte perdu."""
    _, codes = await _activer(service, depot, horloge)

    await service.enforce_at_login(UTILISATEUR, code=codes[0])

    assert (await service.status(UTILISATEUR)).recovery_codes_remaining == RECOVERY_CODE_COUNT - 1


async def test_un_code_de_recuperation_ne_sert_qu_une_fois(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    _, codes = await _activer(service, depot, horloge)
    await service.enforce_at_login(UTILISATEUR, code=codes[0])

    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code=codes[0])


async def test_un_code_de_recuperation_se_retape_sans_ceremonie(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Il est lu sur une feuille imprimée : casse, tirets et espaces ne doivent pas compter."""
    _, codes = await _activer(service, depot, horloge)
    brouillon = f"  {codes[0].lower().replace('-', ' ')}  "

    await service.enforce_at_login(UTILISATEUR, code=brouillon)


async def test_les_codes_de_recuperation_evitent_les_caracteres_ambigus(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Un zéro pris pour un O est une tentative perdue sur une réserve qui en compte dix."""
    _, codes = await _activer(service, depot, horloge)

    assert not set("".join(codes)) & set("O0I1L")


async def test_un_code_de_recuperation_efface_les_essais_rates(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    _, codes = await _activer(service, depot, horloge)
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(TwoFactorInvalid):
            await service.enforce_at_login(UTILISATEUR, code="000000")

    await service.enforce_at_login(UTILISATEUR, code=codes[0])

    assert depot.record is not None and depot.record.failed_attempts == 0


async def test_un_code_de_recuperation_faux_compte_dans_les_essais(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    await _activer(service, depot, horloge)

    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code="ZZZZZ-ZZZZZ")

    assert depot.record is not None and depot.record.failed_attempts == 1


async def test_refaire_la_reserve_invalide_les_anciens_codes(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    secret, anciens = await _activer(service, depot, horloge)
    horloge.avancer(timedelta(seconds=PERIOD_SECONDS * 2))

    nouveaux = await service.regenerate_recovery_codes(
        UTILISATEUR, code=code_pour(secret, horloge.now())
    )

    assert set(nouveaux).isdisjoint(anciens)
    with pytest.raises(TwoFactorInvalid):
        await service.enforce_at_login(UTILISATEUR, code=anciens[0])


# --------------------------------------------------------------------------
# Le retrait
# --------------------------------------------------------------------------


async def test_retirer_le_second_facteur_exige_un_code(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Une session volée ne doit pas suffire à retirer la protection qu'elle a franchie."""
    await _activer(service, depot, horloge)

    with pytest.raises(TwoFactorInvalid):
        await service.disable(UTILISATEUR, code="000000")

    assert (await service.status(UTILISATEUR)).enabled is True


async def test_le_retrait_emporte_les_codes_de_recuperation(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Sinon un réenrôlement plus tard hériterait d'une réserve qu'on croit périmée."""
    secret, _ = await _activer(service, depot, horloge)
    horloge.avancer(timedelta(seconds=PERIOD_SECONDS * 2))

    await service.disable(UTILISATEUR, code=code_pour(secret, horloge.now()))

    assert depot.record is None
    assert depot.codes == {}
    assert (await service.status(UTILISATEUR)).enabled is False


async def test_retirer_sans_second_facteur_est_un_refus_explicite(
    service: TwoFactorService,
) -> None:
    with pytest.raises(TwoFactorNotEnrolled):
        await service.disable(UTILISATEUR, code="000000")


# --------------------------------------------------------------------------
# L'URI d'enrôlement
# --------------------------------------------------------------------------


async def test_l_uri_otpauth_porte_l_emetteur_et_le_compte(service: TwoFactorService) -> None:
    """C'est ce qui distingue « GhostCal » de « GhostPass » dans l'application du téléphone."""
    enrolment = await service.begin_enrolment(UTILISATEUR, account="kevin@stackops.ch")

    assert enrolment.otpauth_uri.startswith("otpauth://totp/GhostCal:")
    assert "issuer=GhostCal" in enrolment.otpauth_uri
    assert f"secret={enrolment.secret}" in enrolment.otpauth_uri


# --------------------------------------------------------------------------
# La plomberie : la connexion doit vraiment passer par la porte
# --------------------------------------------------------------------------


class _DepotAuth(AuthRepository):
    """Le strict nécessaire pour `AuthService.login`."""

    def __init__(self, user_id: uuid.UUID) -> None:
        self.record = AuthUserRecord(
            id=user_id,
            email="kevin@stackops.ch",
            name="Kevin",
            timezone="Europe/Zurich",
            email_verified=True,
            password_hash="hash:bon-mot-de-passe",
        )
        self.jetons_emis = 0

    async def get_by_email(self, email: str) -> AuthUserRecord | None:
        return self.record

    async def get_by_id(self, user_id: uuid.UUID) -> AuthUserRecord | None:
        return self.record

    async def add_refresh_token(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        self.jetons_emis += 1


class _HacheurFactice:
    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, hashed: str, password: str) -> bool:
        return hashed == f"hash:{password}"


class _CodecFactice:
    def encode(self, user_id: uuid.UUID) -> str:
        return f"acces:{user_id}"

    def decode(self, token: str) -> uuid.UUID:
        return uuid.UUID(token.removeprefix("acces:"))


class _MailerFactice:
    async def send(self, *, to: str, subject: str, html: str) -> None:
        return None


def _auth_service(depot_auth: _DepotAuth, second_facteur: TwoFactorService, horloge: object):
    return AuthService(
        depot_auth,
        _HacheurFactice(),  # type: ignore[arg-type]
        _CodecFactice(),  # type: ignore[arg-type]
        _MailerFactice(),  # type: ignore[arg-type]
        horloge,  # type: ignore[arg-type]
        AuthConfig(
            access_ttl=timedelta(minutes=15),
            refresh_ttl=timedelta(days=30),
            email_verification_ttl=timedelta(hours=24),
            frontend_base_url="http://localhost:3001",
        ),
        second_facteur,
    )


async def test_la_connexion_reclame_le_code_quand_le_second_facteur_est_actif(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """Sans ce fil, la politique serait juste et la porte grande ouverte."""
    depot_auth = _DepotAuth(UTILISATEUR)
    auth = _auth_service(depot_auth, service, horloge)
    secret, _ = await _activer(service, depot, horloge)
    horloge.avancer(timedelta(seconds=PERIOD_SECONDS * 2))

    with pytest.raises(TwoFactorRequired):
        await auth.login(email="kevin@stackops.ch", password="bon-mot-de-passe")
    # Et surtout : aucun jeton n'a été émis au passage.
    assert depot_auth.jetons_emis == 0

    pair = await auth.login(
        email="kevin@stackops.ch",
        password="bon-mot-de-passe",
        totp_code=code_pour(secret, horloge.now()),
    )
    assert pair.access_token == f"acces:{UTILISATEUR}"
    assert depot_auth.jetons_emis == 1


async def test_un_mauvais_mot_de_passe_ne_dit_pas_si_le_compte_a_un_second_facteur(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    """L'ordre des contrôles est lui-même une propriété de sécurité.

    Si le second facteur se testait avant le mot de passe, la réponse dirait à
    un inconnu quels comptes existent et lesquels sont protégés — exactement ce
    que la vérification à temps constant du mot de passe cherche à taire.
    """
    depot_auth = _DepotAuth(UTILISATEUR)
    auth = _auth_service(depot_auth, service, horloge)
    await _activer(service, depot, horloge)

    with pytest.raises(InvalidCredentials):
        await auth.login(email="kevin@stackops.ch", password="mauvais")

    # Et l'essai raté n'a pas entamé le compteur du second facteur : il n'a pas
    # été consulté du tout.
    assert depot.record is not None and depot.record.failed_attempts == 0


async def test_la_connexion_passe_comme_avant_sans_second_facteur(
    service: TwoFactorService, horloge: HorlogeMobile
) -> None:
    depot_auth = _DepotAuth(UTILISATEUR)
    auth = _auth_service(depot_auth, service, horloge)

    pair = await auth.login(email="kevin@stackops.ch", password="bon-mot-de-passe")

    assert pair.access_token == f"acces:{UTILISATEUR}"


async def test_un_code_de_recuperation_ouvre_aussi_la_connexion(
    service: TwoFactorService, depot: DepotEnMemoire, horloge: HorlogeMobile
) -> None:
    depot_auth = _DepotAuth(UTILISATEUR)
    auth = _auth_service(depot_auth, service, horloge)
    _, codes = await _activer(service, depot, horloge)

    pair = await auth.login(
        email="kevin@stackops.ch", password="bon-mot-de-passe", totp_code=codes[0]
    )

    assert pair.access_token == f"acces:{UTILISATEUR}"


# --------------------------------------------------------------------------
# Le secret au repos
# --------------------------------------------------------------------------


def test_le_secret_totp_est_chiffre_en_base() -> None:
    """Ce qu'une base volée donne — et ce qu'elle ne donne pas.

    Le serveur DOIT connaître la graine pour vérifier six chiffres : le second
    facteur n'est pas du zero-knowledge, contrairement au contenu des agendas.
    Ce qui reste faisable, c'est qu'une base lue seule ne suffise pas. Sans
    chiffrement au repos, une sauvegarde égarée rendrait les codes de tout le
    monde, et le second facteur cesserait d'en être un.

    La clé vit à côté de la base, pas dedans : qui obtient les deux gagne quand
    même. C'est une atténuation, pas une garantie, et l'écrire ainsi évite de la
    vendre pour ce qu'elle n'est pas.
    """
    assert isinstance(models.UserTotp.__table__.c.secret.type, EncryptedString)

    boite = SecretBox("une-cle-applicative-de-plus-de-32-caracteres")
    chiffre = boite.encrypt("JBSWY3DPEHPK3PXP")
    assert "JBSWY3DPEHPK3PXP" not in chiffre
    assert boite.decrypt(chiffre) == "JBSWY3DPEHPK3PXP"


def test_les_codes_de_recuperation_ne_sont_stockes_que_hachés() -> None:
    """Une base lue ne doit pas rendre de code utilisable."""
    assert models.UserRecoveryCode.__table__.c.code_hash.type.length == 64
    assert not hasattr(models.UserRecoveryCode, "code")


# --------------------------------------------------------------------------
# Les routes
# --------------------------------------------------------------------------


def test_les_routes_du_second_facteur_sont_montees_et_exigent_une_session() -> None:
    """Une garde bon marché contre la régression la plus bête : la route qui disparaît.

    401 et non 404 : la route existe et demande une session. Le jour où un
    remaniement de `api.py` oublie le routeur, cette assertion vire au rouge
    plutôt que de laisser une interface appeler dans le vide.
    """
    client = TestClient(create_app())
    for methode, chemin in [
        ("GET", "/v1/auth/mfa"),
        ("POST", "/v1/auth/mfa/setup"),
        ("POST", "/v1/auth/mfa/activate"),
        ("POST", "/v1/auth/mfa/disable"),
        ("POST", "/v1/auth/mfa/recovery-codes"),
    ]:
        reponse = client.request(methode, chemin, json={})
        assert reponse.status_code == 401, f"{methode} {chemin} -> {reponse.status_code}"
