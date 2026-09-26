"""Les journées entières importées depuis un calendrier externe (iCloud, CalDAV).

Un VEVENT en journée entière ne dit pas la même chose qu'un VEVENT horaire, et
les deux pièges se cumulent :

- **DTEND est exclusif.** RFC 5545 §3.6.1 : pour une journée entière,
  ``DTSTART;VALUE=DATE:20260901`` / ``DTEND;VALUE=DATE:20260902`` désigne *le
  1er septembre*, pas « du 1er au 2 ». La fin nomme le lendemain matin.
- **Une date nue n'a pas de fuseau.** Minuit n'est pas minuit UTC : à Paris,
  le 1er septembre commence le 31 août à 22:00 UTC, et l'écart n'est pas le
  même en février qu'en juillet.

Chaque erreur prise isolément décale la journée ; ensemble, elles étalent un
mardi sur trois jours civils. Les tests ci-dessous sont écrits en jours civils
*dans le fuseau du calendrier*, parce que c'est là que l'utilisateur voit le
défaut — comparer des instants UTC laisserait passer exactement l'erreur qu'on
cherche.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from ghostcal.application.calendars import (
    CaldavConnectionRepository,
    ConnectionRecord,
    UnknownHostTimezone,
    sync_connection,
)
from ghostcal.application.ports.calendar import BusyEvent, CalendarError
from ghostcal.application.ports.clock import FixedClock
from ghostcal.infrastructure.calendars.caldav_client import _as_utc_range, _busy_from_ical

PARIS = ZoneInfo("Europe/Paris")


def _ics(*vevent_lines: str, calendar_props: str = "") -> str:
    """Un VCALENDAR réaliste tel qu'iCloud le rend dans un REPORT calendar-query."""
    props = f"{calendar_props}\r\n" if calendar_props else ""
    body = "\r\n".join(vevent_lines)
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Apple Inc.//iPhone OS 18.5//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        f"{props}"
        "BEGIN:VEVENT\r\n"
        f"{body}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def _civil_days(start: datetime, end: datetime, zone: ZoneInfo) -> list[date]:
    """Les jours civils réellement bloqués, dans le fuseau du calendrier.

    La fin est exclusive : un créneau qui s'arrête à minuit pile ne bloque pas
    le jour qui commence à cet instant.
    """
    local_start = start.astimezone(zone)
    local_end = end.astimezone(zone)
    days: list[date] = []
    day = local_start.date()
    while datetime.combine(day, datetime.min.time(), tzinfo=zone) < local_end:
        days.append(day)
        day += timedelta(days=1)
    return days


def _one_range(ics: str, *, default_timezone: str = "Europe/Paris"):
    busy = _busy_from_ical(ics, default_timezone=default_timezone)
    assert len(busy) == 1, f"attendu un seul VEVENT occupé, obtenu {busy!r}"
    return busy[0]


# --------------------------------------------------------------------------
# Le défaut signalé : un jour qui en bloque trois
# --------------------------------------------------------------------------


def test_journee_entiere_ne_bloque_que_son_jour() -> None:
    """Le cas rapporté : un mardi en journée entière ne doit bloquer que ce mardi."""
    ics = _ics(
        "UID:1E5C0A6E-0001@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;VALUE=DATE:20260901",  # mardi 1er septembre 2026
        "DTEND;VALUE=DATE:20260902",  # fin exclusive : le 2 au matin
        "SUMMARY:Conge",
    )
    ev = _one_range(ics)

    assert _civil_days(ev.start, ev.end, PARIS) == [date(2026, 9, 1)]
    # Et l'instant exact, pour épingler l'ancrage : minuit à Paris, pas minuit UTC.
    assert ev.start == datetime(2026, 8, 31, 22, 0, tzinfo=UTC)
    assert ev.end == datetime(2026, 9, 1, 22, 0, tzinfo=UTC)


def test_journee_entiere_sur_plusieurs_jours() -> None:
    """DTSTART 20260901 / DTEND 20260904, c'est trois jours — pas quatre."""
    ics = _ics(
        "UID:1E5C0A6E-0002@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;VALUE=DATE:20260901",
        "DTEND;VALUE=DATE:20260904",
        "SUMMARY:Deplacement",
    )
    ev = _one_range(ics)

    assert _civil_days(ev.start, ev.end, PARIS) == [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]


def test_journee_entiere_sans_dtend_dure_un_jour() -> None:
    """DTEND absent sur une date nue : RFC 5545, la journée entière dure un jour.

    Le repli « trente minutes » des événements horaires ne convient pas ici : il
    laisserait l'après-midi réservable un jour déclaré pris.
    """
    ics = _ics(
        "UID:1E5C0A6E-0003@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;VALUE=DATE:20260901",
        "SUMMARY:Ferie",
    )
    ev = _one_range(ics)

    assert _civil_days(ev.start, ev.end, PARIS) == [date(2026, 9, 1)]
    assert ev.end - ev.start == timedelta(hours=24)


# --------------------------------------------------------------------------
# Le changement d'heure, où un décalage fixe se trahit
# --------------------------------------------------------------------------


def test_journee_entiere_a_cheval_sur_le_passage_a_l_heure_d_ete() -> None:
    """Fin mars : la nuit du 28 au 29 mars 2026 ne dure que 23 heures à Paris.

    Un ancrage à décalage fixe (+01:00 ou +02:00 pour tout l'intervalle) donne
    ici 72 ou 70 heures. Seul un vrai fuseau donne 71.
    """
    ics = _ics(
        "UID:1E5C0A6E-0004@icloud.com",
        "DTSTAMP:20260301T120000Z",
        "DTSTART;VALUE=DATE:20260328",
        "DTEND;VALUE=DATE:20260331",
        "SUMMARY:Week-end prolonge",
    )
    ev = _one_range(ics)

    assert _civil_days(ev.start, ev.end, PARIS) == [
        date(2026, 3, 28),
        date(2026, 3, 29),
        date(2026, 3, 30),
    ]
    assert ev.end - ev.start == timedelta(hours=71)
    assert ev.start == datetime(2026, 3, 27, 23, 0, tzinfo=UTC)  # encore UTC+1
    assert ev.end == datetime(2026, 3, 30, 22, 0, tzinfo=UTC)  # déjà UTC+2


def test_journee_entiere_a_cheval_sur_le_retour_a_l_heure_d_hiver() -> None:
    """Fin octobre : la nuit du 24 au 25 octobre 2026 dure 25 heures à Paris."""
    ics = _ics(
        "UID:1E5C0A6E-0005@icloud.com",
        "DTSTAMP:20261001T120000Z",
        "DTSTART;VALUE=DATE:20261024",
        "DTEND;VALUE=DATE:20261027",
        "SUMMARY:Vacances",
    )
    ev = _one_range(ics)

    assert _civil_days(ev.start, ev.end, PARIS) == [
        date(2026, 10, 24),
        date(2026, 10, 25),
        date(2026, 10, 26),
    ]
    assert ev.end - ev.start == timedelta(hours=73)
    assert ev.start == datetime(2026, 10, 23, 22, 0, tzinfo=UTC)  # encore UTC+2
    assert ev.end == datetime(2026, 10, 26, 23, 0, tzinfo=UTC)  # déjà UTC+1


# --------------------------------------------------------------------------
# D'où vient le fuseau
# --------------------------------------------------------------------------


def test_le_tzid_du_composant_prime_sur_le_fuseau_de_l_utilisateur() -> None:
    """Un TZID posé sur DTSTART décide, même s'il n'est pas censé accompagner une date nue.

    Des serveurs en émettent ; quand c'est le cas, il est plus proche de la
    vérité que le fuseau du profil, qui n'est qu'un dernier recours.
    """
    ics = _ics(
        "UID:1E5C0A6E-0006@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;VALUE=DATE;TZID=Asia/Tokyo:20260901",
        "DTEND;VALUE=DATE;TZID=Asia/Tokyo:20260902",
        "SUMMARY:Reunion Tokyo",
    )
    ev = _one_range(ics, default_timezone="Europe/Paris")

    assert _civil_days(ev.start, ev.end, ZoneInfo("Asia/Tokyo")) == [date(2026, 9, 1)]
    assert ev.start == datetime(2026, 8, 31, 15, 0, tzinfo=UTC)


def test_x_wr_timezone_du_calendrier_sert_quand_le_composant_se_tait() -> None:
    ics = _ics(
        "UID:1E5C0A6E-0007@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;VALUE=DATE:20260901",
        "DTEND;VALUE=DATE:20260902",
        "SUMMARY:Conge",
        calendar_props="X-WR-TIMEZONE:America/New_York",
    )
    ev = _one_range(ics, default_timezone="Europe/Paris")

    assert _civil_days(ev.start, ev.end, ZoneInfo("America/New_York")) == [date(2026, 9, 1)]
    assert ev.start == datetime(2026, 9, 1, 4, 0, tzinfo=UTC)


def test_un_fuseau_inconnu_ne_passe_pas_pour_utc() -> None:
    """Trois états, pas deux : si le fuseau est illisible partout, on le dit.

    Retomber silencieusement sur UTC rendrait un agenda d'apparence normale et
    décalé de quelques heures — exactement la panne qu'on ne voit pas.
    """
    ics = _ics(
        "UID:1E5C0A6E-0008@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;VALUE=DATE:20260901",
        "DTEND;VALUE=DATE:20260902",
        "SUMMARY:Conge",
    )
    with pytest.raises(CalendarError):
        _busy_from_ical(ics, default_timezone="Mars/Olympus_Mons")


def test_un_tzid_illisible_retombe_sur_le_fuseau_connu_suivant() -> None:
    """Un TZID que la base de fuseaux ne connaît pas ne doit pas coûter l'événement."""
    ics = _ics(
        "UID:1E5C0A6E-0009@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;VALUE=DATE;TZID=Customized Time Zone:20260901",
        "DTEND;VALUE=DATE;TZID=Customized Time Zone:20260902",
        "SUMMARY:Conge",
    )
    ev = _one_range(ics, default_timezone="Europe/Paris")

    assert _civil_days(ev.start, ev.end, PARIS) == [date(2026, 9, 1)]


# --------------------------------------------------------------------------
# Ce qui ne doit pas bouger : les événements horaires
# --------------------------------------------------------------------------


def test_evenement_horaire_en_utc_inchange() -> None:
    ics = _ics(
        "UID:1E5C0A6E-0010@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART:20260901T090000Z",
        "DTEND:20260901T103000Z",
        "SUMMARY:Point equipe",
    )
    ev = _one_range(ics)

    assert ev.start == datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    assert ev.end == datetime(2026, 9, 1, 10, 30, tzinfo=UTC)


def test_evenement_horaire_avec_tzid_reste_ancre_sur_son_fuseau() -> None:
    ics = _ics(
        "UID:1E5C0A6E-0011@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART;TZID=Europe/Paris:20260901T090000",
        "DTEND;TZID=Europe/Paris:20260901T100000",
        "SUMMARY:Point equipe",
    )
    ev = _one_range(ics)

    assert ev.start == datetime(2026, 9, 1, 7, 0, tzinfo=UTC)
    assert ev.end == datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def test_evenement_horaire_flottant_suit_le_fuseau_du_calendrier() -> None:
    """Une heure sans Z ni TZID est « flottante » : elle se lit dans le fuseau local.

    La lire en UTC décalait l'événement de l'offset du fuseau — même faute que
    pour les dates nues, en moins visible.
    """
    ics = _ics(
        "UID:1E5C0A6E-0012@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART:20260901T090000",
        "DTEND:20260901T100000",
        "SUMMARY:Point equipe",
    )
    ev = _one_range(ics, default_timezone="Europe/Paris")

    assert ev.start == datetime(2026, 9, 1, 7, 0, tzinfo=UTC)


def test_evenement_horaire_sans_fin_garde_son_repli_de_trente_minutes() -> None:
    ics = _ics(
        "UID:1E5C0A6E-0013@icloud.com",
        "DTSTAMP:20260801T120000Z",
        "DTSTART:20260901T090000Z",
        "SUMMARY:Point equipe",
    )
    ev = _one_range(ics)

    assert ev.end - ev.start == timedelta(minutes=30)


def test_transparent_et_annule_restent_ignores() -> None:
    for ligne in ("TRANSP:TRANSPARENT", "STATUS:CANCELLED"):
        ics = _ics(
            "UID:1E5C0A6E-0014@icloud.com",
            "DTSTAMP:20260801T120000Z",
            "DTSTART;VALUE=DATE:20260901",
            "DTEND;VALUE=DATE:20260902",
            "SUMMARY:Conge",
            ligne,
        )
        assert _busy_from_ical(ics, default_timezone="Europe/Paris") == []


# --------------------------------------------------------------------------
# Le cœur de la conversion, sans passer par iCalendar
# --------------------------------------------------------------------------


def test_as_utc_range_ne_rallonge_plus_une_fin_deja_exclusive() -> None:
    tr = _as_utc_range(date(2026, 9, 1), date(2026, 9, 2), zone=PARIS)
    assert tr is not None
    assert tr.end - tr.start == timedelta(hours=24)


def test_as_utc_range_sans_debut_ne_rend_rien() -> None:
    assert _as_utc_range(None, date(2026, 9, 2), zone=PARIS) is None


def test_as_utc_range_refuse_une_fin_anterieure_au_debut() -> None:
    """Un calendrier qui rend DTEND avant DTSTART est cassé ; on ne fabrique pas
    un intervalle négatif, mais on ne l'enterre pas non plus en silence."""
    tr = _as_utc_range(date(2026, 9, 4), date(2026, 9, 1), zone=PARIS)
    assert tr is not None
    assert tr.end > tr.start


# --------------------------------------------------------------------------
# La plomberie : le fuseau du membre doit arriver jusqu'à l'adaptateur
# --------------------------------------------------------------------------


class _FauxRepo(CaldavConnectionRepository):
    """Juste ce qu'il faut pour `sync_connection`, sans base de données."""

    def __init__(self, *, timezone_du_membre: str | None) -> None:
        self.timezone_du_membre = timezone_du_membre
        self.enregistres: list[BusyEvent] = []
        self.record = ConnectionRecord(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            server_url="https://caldav.icloud.com/",
            username="membre@example.org",
            password_encrypted="enc:secret",
            calendar_url="https://caldav.icloud.com/123/calendars/home/",
            calendar_name="Perso",
            color="#7aa2f7",
            mirror_bookings=True,
            mirror_detail="busy",
            status="active",
            last_synced_at=None,
        )

    async def get(self, connection_id: uuid.UUID, user_id: uuid.UUID) -> ConnectionRecord | None:
        return self.record

    async def host_timezone(self, user_id: uuid.UUID) -> str | None:
        return self.timezone_du_membre

    async def replace_busy(
        self, connection_id: uuid.UUID, host_id: uuid.UUID, busy: list[BusyEvent]
    ) -> None:
        self.enregistres = list(busy)

    async def mark_synced(self, connection_id: uuid.UUID, when: datetime, status: str) -> None:
        return None


class _FauxCipher:
    def encrypt(self, plaintext: str) -> str:
        return f"enc:{plaintext}"

    def decrypt(self, token: str) -> str:
        return token.removeprefix("enc:")


class _ClientEnregistreur:
    """Rend une journée entière, et retient le fuseau qu'on lui a passé."""

    def __init__(self) -> None:
        self.fuseau_recu: str | None = None

    async def list_calendars(self, creds: object) -> list[object]:
        raise NotImplementedError

    async def fetch_busy(
        self,
        creds: object,
        calendar_url: str,
        start: datetime,
        end: datetime,
        *,
        default_timezone: str = "UTC",
    ) -> list[BusyEvent]:
        self.fuseau_recu = default_timezone
        return _busy_from_ical(
            _ics(
                "UID:1E5C0A6E-0020@icloud.com",
                "DTSTAMP:20260801T120000Z",
                "DTSTART;VALUE=DATE:20260901",
                "DTEND;VALUE=DATE:20260902",
                "SUMMARY:Conge",
            ),
            default_timezone=default_timezone,
        )

    async def create_event(self, *args: object, **kwargs: object) -> str:
        raise NotImplementedError

    async def delete_event(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError


async def test_la_synchronisation_transmet_le_fuseau_du_membre() -> None:
    """Sans ce fil, la correction resterait vraie en théorie et fausse en production."""
    repo = _FauxRepo(timezone_du_membre="Europe/Paris")
    client = _ClientEnregistreur()

    compte = await sync_connection(
        repo,
        _FauxCipher(),
        client,  # type: ignore[arg-type]
        FixedClock(datetime(2026, 8, 20, 9, 0, tzinfo=UTC)),
        connection_id=repo.record.id,
        user_id=repo.record.user_id,
    )

    assert compte == 1
    assert client.fuseau_recu == "Europe/Paris"
    (ecrit,) = repo.enregistres
    assert _civil_days(ecrit.start, ecrit.end, PARIS) == [date(2026, 9, 1)]


async def test_sans_fuseau_de_membre_la_synchronisation_refuse_plutot_que_de_supposer() -> None:
    """Trois états : plutôt échouer que d'écrire en base des journées décalées."""
    repo = _FauxRepo(timezone_du_membre=None)

    with pytest.raises(UnknownHostTimezone):
        await sync_connection(
            repo,
            _FauxCipher(),
            _ClientEnregistreur(),  # type: ignore[arg-type]
            FixedClock(datetime(2026, 8, 20, 9, 0, tzinfo=UTC)),
            connection_id=repo.record.id,
            user_id=repo.record.user_id,
        )
    assert repo.enregistres == []
