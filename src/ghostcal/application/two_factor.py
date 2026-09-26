"""Second facteur TOTP : enrôlement, vérification, codes de récupération.

Sans framework ni SQL, comme le reste de la couche application. L'algorithme
lui-même est derrière le port ``TotpEngine`` ; ce module ne contient que ce que
l'algorithme ne dit pas et qu'on oublie pourtant systématiquement.

**Ce qu'un code juste ne suffit pas à établir.** Vérifier six chiffres est la
partie facile. Ce qui fait qu'un second facteur protège vraiment, c'est :

- l'**anti-rejeu** — un code reste valide trente secondes, largement de quoi
  être relu dans un journal, capté sur le réseau ou lu par-dessus l'épaule et
  resservi. On retient donc la dernière période consommée et on exige qu'elle
  progresse strictement ;
- la **limitation des essais** — six chiffres, c'est un million de
  possibilités, et une fenêtre de ±1 période en rend trois acceptables à tout
  instant. Sans compteur, quelques centaines de milliers de requêtes suffisent.
  Le limiteur de `ratelimit.py` ne convient pas ici : il compte **par adresse
  IP**, qu'un attaquant fait tourner, et il est **fail-open** — Redis muet, tout
  passe. Celui-ci compte par compte, en base, dans la transaction ;
- les **codes de récupération** — sans eux un téléphone perdu est un compte
  perdu, et c'est le support qui paie. GhostPass n'en a pas ; c'est une lacune,
  pas un modèle à recopier ;
- le **parcours d'activation** — le secret est écrit dès l'affichage du QR code,
  mais il ne garde la porte qu'une fois un premier code produit. Verrouiller le
  compte avant cette preuve enfermerait dehors quiconque ferme l'onglet trop tôt.

**Ce que ce module ne prétend pas faire.** Le secret TOTP est connu du serveur —
il le faut pour vérifier un code — donc le second facteur n'est pas du
zero-knowledge, contrairement au contenu des agendas. Il est chiffré au repos
(``EncryptedString``), ce qui protège d'une base volée seule et de rien d'autre.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from ghostcal.application.ports.clock import Clock
from ghostcal.application.ports.security import TotpEngine


class TwoFactorError(Exception):
    """Base des refus liés au second facteur."""


class TwoFactorRequired(TwoFactorError):
    """Le compte a un second facteur et aucun code n'a été fourni.

    Ce n'est **pas** un échec : c'est la première moitié d'une connexion en deux
    temps. Il ne compte donc pas dans les essais ratés — sinon cinq connexions
    normales verrouilleraient le compte de quelqu'un qui n'a rien fait de mal.
    """


class TwoFactorInvalid(TwoFactorError):
    """Code faux, ou déjà consommé."""


class TwoFactorLocked(TwoFactorError):
    """Trop d'essais ratés ; le second facteur est bloqué pour un temps."""

    def __init__(self, until: datetime) -> None:
        super().__init__(f"two-factor locked until {until.isoformat()}")
        self.until = until


class TwoFactorAlreadyEnabled(TwoFactorError):
    """Le second facteur est déjà actif ; le réenrôler écraserait le secret en place."""


class TwoFactorNotEnrolled(TwoFactorError):
    """Aucun enrôlement en cours ou actif pour ce compte."""


# Cinq essais avant blocage. Avec une fenêtre de ±1 période, trois codes sur un
# million sont acceptables à un instant donné : cinq essais laissent une chance
# sur près de soixante-dix mille par salve, et il en faut une par quart d'heure.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)

# Dix codes : assez pour parer plusieurs pertes d'appareil sans que la feuille
# imprimée devienne elle-même un inventaire de secrets à garder.
RECOVERY_CODE_COUNT = 10

# Alphabet sans O, 0, I, 1 ni L : ces codes sont lus sur un écran ou sur une
# feuille imprimée, puis retapés à la main. Un zéro pris pour un O est une
# tentative perdue sur une réserve qui en compte dix — et un L pris pour un 1
# l'est tout autant, ce que la première version de cet alphabet avait oublié.
#
# Trente et un caractères, donc, et pas une puissance de deux. Sans importance :
# `secrets.choice` tire sans biais de modulo quelle que soit la taille, et
# 31**10 laisse encore 49 bits par code.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 10


@dataclass(frozen=True, slots=True)
class TotpRecord:
    user_id: uuid.UUID
    secret: str
    confirmed_at: datetime | None
    last_counter: int
    failed_attempts: int
    locked_until: datetime | None

    @property
    def is_active(self) -> bool:
        """Actif = enrôlement confirmé. Une ligne en attente ne garde aucune porte."""
        return self.confirmed_at is not None


@dataclass(frozen=True, slots=True)
class Enrolment:
    """Ce qu'il faut pour enrôler une application d'authentification."""

    secret: str
    otpauth_uri: str


@dataclass(frozen=True, slots=True)
class TwoFactorStatus:
    enabled: bool
    """Un secret a été généré mais le premier code n'a pas encore été produit."""
    pending: bool
    recovery_codes_remaining: int


class TwoFactorRepository:
    async def get(self, user_id: uuid.UUID) -> TotpRecord | None:
        raise NotImplementedError

    async def upsert_pending(self, user_id: uuid.UUID, secret: str) -> None:
        """Écrit (ou remplace) un enrôlement non confirmé, compteurs remis à zéro."""
        raise NotImplementedError

    async def confirm(self, user_id: uuid.UUID, when: datetime) -> None:
        raise NotImplementedError

    async def delete(self, user_id: uuid.UUID) -> None:
        """Retire le second facteur ET les codes de récupération du compte."""
        raise NotImplementedError

    async def record_success(self, user_id: uuid.UUID, *, last_counter: int) -> None:
        """Avance la période consommée et efface les essais ratés."""
        raise NotImplementedError

    async def record_failure(
        self, user_id: uuid.UUID, *, failed_attempts: int, locked_until: datetime | None
    ) -> None:
        raise NotImplementedError

    async def replace_recovery_codes(self, user_id: uuid.UUID, code_hashes: list[str]) -> None:
        """Remplace toute la réserve. Les anciens codes cessent de valoir."""
        raise NotImplementedError

    async def consume_recovery_code(self, user_id: uuid.UUID, code_hash: str) -> bool:
        """Marque un code inutilisé comme consommé. False s'il n'existe pas ou a déjà servi.

        L'usage unique doit être porté par le ``WHERE used_at IS NULL`` de
        l'UPDATE, pas par une lecture suivie d'une écriture : deux requêtes
        simultanées avec le même code passeraient toutes les deux le test de
        lecture.
        """
        raise NotImplementedError

    async def count_unused_recovery_codes(self, user_id: uuid.UUID) -> int:
        raise NotImplementedError


def _normalise(code: str) -> str:
    """Un code de récupération tel qu'il est retapé : espaces et tirets en moins, majuscules."""
    return code.strip().upper().replace("-", "").replace(" ", "")


def _hash_code(code: str) -> str:
    return hashlib.sha256(_normalise(code).encode()).hexdigest()


def _new_recovery_codes() -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(RECOVERY_CODE_COUNT)]


class TwoFactorService:
    def __init__(self, repo: TwoFactorRepository, engine: TotpEngine, clock: Clock) -> None:
        self._repo = repo
        self._engine = engine
        self._clock = clock

    async def status(self, user_id: uuid.UUID) -> TwoFactorStatus:
        record = await self._repo.get(user_id)
        if record is None:
            return TwoFactorStatus(enabled=False, pending=False, recovery_codes_remaining=0)
        return TwoFactorStatus(
            enabled=record.is_active,
            pending=not record.is_active,
            recovery_codes_remaining=await self._repo.count_unused_recovery_codes(user_id),
        )

    async def begin_enrolment(self, user_id: uuid.UUID, *, account: str) -> Enrolment:
        """Génère un secret et l'URI du QR code.

        Refuse si le second facteur est déjà actif. C'est la garde que GhostPass
        a dû ajouter après coup : proposer « activer » à quelqu'un qui l'a déjà
        remet son secret à zéro sans prévenir, et son application
        d'authentification devient muette sans que rien ne l'explique.
        """
        existing = await self._repo.get(user_id)
        if existing is not None and existing.is_active:
            raise TwoFactorAlreadyEnabled(str(user_id))
        secret = self._engine.new_secret()
        await self._repo.upsert_pending(user_id, secret)
        return Enrolment(
            secret=secret, otpauth_uri=self._engine.provisioning_uri(secret, account=account)
        )

    async def activate(self, user_id: uuid.UUID, *, code: str) -> list[str]:
        """Confirme l'enrôlement contre un premier code et rend les codes de récupération.

        Ils ne sont rendus qu'ici, une seule fois : seules leurs empreintes sont
        gardées, donc personne — nous compris — ne peut les réafficher ensuite.

        La période n'est pas consommée à l'activation. La session est déjà
        authentifiée, donc il n'y a rien à rejouer ; et la consommer interdirait
        de se reconnecter dans les trente secondes qui suivent avec le code
        affiché à l'écran, ce que tout le monde essaie.
        """
        record = await self._repo.get(user_id)
        if record is None:
            raise TwoFactorNotEnrolled(str(user_id))
        if record.is_active:
            raise TwoFactorAlreadyEnabled(str(user_id))
        if self._engine.verify(record.secret, code, at=self._clock.now()) is None:
            raise TwoFactorInvalid("invalid code")
        await self._repo.confirm(user_id, self._clock.now())
        return await self._issue_recovery_codes(user_id)

    async def disable(self, user_id: uuid.UUID, *, code: str) -> None:
        """Retire le second facteur. Exige un code valide, TOTP ou de récupération.

        L'appelant a déjà revérifié le mot de passe ; le code s'y ajoute pour
        qu'une session volée ne suffise pas à retirer la protection qu'elle est
        censée avoir franchie.
        """
        record = await self._repo.get(user_id)
        if record is None or not record.is_active:
            raise TwoFactorNotEnrolled(str(user_id))
        await self._verify(record, code)
        await self._repo.delete(user_id)

    async def regenerate_recovery_codes(self, user_id: uuid.UUID, *, code: str) -> list[str]:
        """Refait la réserve. Les anciens codes cessent de valoir à cet instant."""
        record = await self._repo.get(user_id)
        if record is None or not record.is_active:
            raise TwoFactorNotEnrolled(str(user_id))
        await self._verify(record, code)
        return await self._issue_recovery_codes(user_id)

    async def enforce_at_login(self, user_id: uuid.UUID, *, code: str | None) -> None:
        """La porte, au moment de la connexion. Ne fait rien si le compte n'a pas de second facteur.

        Appelée **après** la vérification du mot de passe, jamais avant : demander
        un code à qui n'a pas donné le bon mot de passe dirait à un inconnu quels
        comptes existent et lesquels sont protégés.
        """
        record = await self._repo.get(user_id)
        if record is None or not record.is_active:
            return
        if code is None:
            # Demande, pas échec — ne compte pas dans les essais ratés.
            raise TwoFactorRequired("two-factor code required")
        await self._verify(record, code)

    async def _verify(self, record: TotpRecord, code: str) -> None:
        """Vérifie un code TOTP ou de récupération, et en tire les conséquences.

        Le blocage se teste avant toute comparaison : un compte bloqué ne doit
        pas pouvoir servir d'oracle, même à qui présenterait le bon code.
        """
        now = self._clock.now()
        if record.locked_until is not None and record.locked_until > now:
            raise TwoFactorLocked(record.locked_until)

        counter = self._engine.verify(record.secret, code, at=now)
        if counter is not None:
            if counter <= record.last_counter:
                # Code juste mais déjà consommé : c'est un rejeu, donc un échec,
                # et il compte comme tel. Le distinguer d'un code faux dans la
                # réponse renseignerait l'attaquant sur ce qu'il vient de capter.
                await self._fail(record, now)
                raise TwoFactorInvalid("code already used")
            await self._repo.record_success(record.user_id, last_counter=counter)
            return

        if await self._repo.consume_recovery_code(record.user_id, _hash_code(code)):
            # Un code de récupération n'avance pas la période TOTP : il n'en a
            # pas. Il efface en revanche les essais ratés, comme tout succès.
            await self._repo.record_success(record.user_id, last_counter=record.last_counter)
            return

        await self._fail(record, now)
        raise TwoFactorInvalid("invalid code")

    async def _fail(self, record: TotpRecord, now: datetime) -> None:
        """Compte l'échec et bloque au seuil.

        Le compteur n'est **pas** remis à zéro quand le blocage expire : passé le
        premier verrouillage, chaque nouvel échec reverrouille aussitôt, donc un
        essai par quart d'heure au lieu de cinq. C'est volontairement sévère —
        un compte sous attaque ne se rouvre pas tout seul — et sans conséquence
        pour son propriétaire, qu'un seul code juste remet à zéro, et à qui il
        reste ses codes de récupération.
        """
        attempts = record.failed_attempts + 1
        locked_until = now + LOCKOUT if attempts >= MAX_FAILED_ATTEMPTS else None
        await self._repo.record_failure(
            record.user_id, failed_attempts=attempts, locked_until=locked_until
        )

    async def _issue_recovery_codes(self, user_id: uuid.UUID) -> list[str]:
        codes = _new_recovery_codes()
        await self._repo.replace_recovery_codes(user_id, [_hash_code(c) for c in codes])
        return codes
