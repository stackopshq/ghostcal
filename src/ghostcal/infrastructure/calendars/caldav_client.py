"""Adaptateur CalDAV, bâti sur notre propre couche protocole (voir ``dav.py``).

L'occupation se lit en dépliant les événements sur une fenêtre ; ce qui est
marqué transparent ou annulé est ignoré. Les événements sont écrits et retirés
comme des VEVENT minimaux, identifiés par notre propre UID.

Cet adaptateur était synchrone et tournait dans un fil d'exécution parce que
``caldav`` l'était. La bibliothèque est partie, la raison aussi : tout est
désormais asynchrone de bout en bout, comme le reste du projet.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Calendar as ICalendar

from ghostcal.application.ports.calendar import (
    BusyEvent,
    CalendarAuthError,
    CalendarCredentials,
    CalendarError,
    CalendarInfo,
)
from ghostcal.domain.time import TimeRange
from ghostcal.infrastructure.calendars.dav import (
    _PROP_CALENDARS,
    _PROP_HOME,
    _PROP_PRINCIPAL,
    NS,
    DavAuthError,
    DavError,
    DavSession,
    _query_by_uid,
    _query_time_range,
    first_href,
    parse_multistatus,
)
from ghostcal.infrastructure.security.egress import (
    assert_public_url,
    calendar_private_networks,
)


def _guard(url: str) -> None:
    # Garde SSRF : ne jamais se connecter à un serveur CalDAV sur une adresse
    # interne ou de métadonnées, sauf dans une plage privée que l'opérateur a
    # explicitement ouverte pour l'auto-hébergement.
    assert_public_url(url, allowed_private_networks=calendar_private_networks())


def _ics_dt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ics_text(value: str) -> str:
    """Échappe une valeur texte iCalendar selon la RFC 5545 et retire les CR/LF.

    Le retrait des sauts de ligne n'est pas cosmétique : sans lui, une valeur
    contenant un retour chariot ouvre une propriété iCalendar arbitraire dans le
    fichier produit.
    """
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _as_utc_range(start_value: object, end_value: object, *, zone: ZoneInfo) -> TimeRange | None:
    """Normalise le début et la fin d'un événement en une plage UTC.

    Deux conventions d'iCalendar se rejoignent ici, et les manquer toutes les
    deux étalait une journée entière sur **trois** jours civils :

    - **DTEND est exclusif** (RFC 5545 §3.6.1). Sur une date nue, il nomme le
      lendemain matin : ``DTSTART:20260901`` / ``DTEND:20260902``, c'est le 1er
      septembre et rien d'autre. Lui rajouter un jour, comme on le faisait pour
      « couvrir le jour complet », en ajoutait un de trop.
    - **Une date nue n'a pas de fuseau**, et une heure sans ``Z`` ni ``TZID``
      non plus (RFC 5545 §3.3.5 : elle est dite *flottante*). Les lire en UTC
      décale l'événement de l'offset du calendrier ; à Paris, minuit tombe la
      veille à 22:00 ou 23:00 UTC, ce qui suffit à mordre sur le jour d'avant.

    Le passage par ``ZoneInfo`` plutôt que par un offset figé n'est pas un
    raffinement : un séjour à cheval sur le dernier dimanche de mars dure 71
    heures et non 72, et c'est la seule façon de le dire juste des deux côtés.
    """

    def to_dt(value: object) -> datetime | None:
        if isinstance(value, datetime):
            # Heure flottante : c'est l'heure locale du calendrier, pas de l'UTC.
            return value if value.tzinfo else value.replace(tzinfo=zone)
        if isinstance(value, date):
            return datetime.combine(value, time(0, 0), tzinfo=zone)
        return None

    # datetime hérite de date : tester datetime en premier, sinon toute heure
    # passerait pour une journée entière.
    all_day = isinstance(start_value, date) and not isinstance(start_value, datetime)
    start = to_dt(start_value)
    if start is None:
        return None
    end = to_dt(end_value)
    if end is None or end <= start:
        # Rien d'exploitable en face : une journée entière dure un jour, un
        # événement horaire garde le créneau court qu'on lui donnait déjà.
        # L'addition se fait sur l'heure murale, donc un jour reste un jour même
        # quand la nuit en compte 23 ou 25.
        end = start + (timedelta(days=1) if all_day else timedelta(minutes=30))
    return TimeRange(start.astimezone(UTC), end.astimezone(UTC))


def _zone(name: object) -> ZoneInfo | None:
    """Le fuseau nommé, ou ``None`` si la base de fuseaux ne le connaît pas.

    ``None`` dit « je n'ai pas pu lire celui-là », pas « prends UTC » : c'est à
    l'appelant de passer au candidat suivant, et de se plaindre s'il n'en reste
    aucun. Des serveurs émettent des TZID maison (« Customized Time Zone ») ;
    ils ne doivent coûter ni l'événement, ni la vérité sur les autres.
    """
    if not name:
        return None
    try:
        return ZoneInfo(str(name))
    except ZoneInfoNotFoundError, ValueError:
        return None


def _busy_from_ical(text: str, *, default_timezone: str) -> list[BusyEvent]:
    """Les créneaux occupés d'un objet iCalendar rendu par le serveur.

    Séparé de ``fetch_busy`` pour que la conversion soit éprouvable sans réseau :
    ce qui se casse ici tient à la forme du calendrier, pas au transport.

    Le fuseau appliqué aux dates nues et aux heures flottantes se choisit dans
    cet ordre : le ``TZID`` du composant, puis le ``X-WR-TIMEZONE`` du
    calendrier, puis celui de l'utilisateur. Les deux premiers manquent souvent
    dans une réponse CalDAV — le profil est donc le cas courant, pas l'exception.
    """
    try:
        cal = ICalendar.from_ical(text)
    except Exception:
        # Un événement illisible ne doit pas faire échouer la fenêtre entière :
        # le reste du calendrier reste utilisable, et un créneau manquant se
        # voit, alors qu'une erreur globale masque tout.
        return []

    fallback = _zone(default_timezone)
    if fallback is None:
        # Pas de repli sur UTC : il rendrait un agenda d'apparence normale et
        # décalé de quelques heures, ce qui ne se voit pas. Mieux vaut que la
        # synchronisation dise qu'elle n'a pas pu regarder.
        raise CalendarError(f"unknown timezone: {default_timezone!r}")
    calendar_zone = _zone(cal.get("x-wr-timezone")) or fallback

    busy: list[BusyEvent] = []
    for comp in cal.walk("VEVENT"):
        if str(comp.get("transp", "")).upper() == "TRANSPARENT":
            continue
        if str(comp.get("status", "")).upper() == "CANCELLED":
            continue
        dtstart = comp.get("dtstart")
        dtend = comp.get("dtend")
        zone = _zone(dtstart.params.get("TZID")) if dtstart is not None else None
        tr = _as_utc_range(
            dtstart.dt if dtstart else None,
            dtend.dt if dtend else None,
            zone=zone or calendar_zone,
        )
        if tr is not None:
            summary = comp.get("summary")
            busy.append(
                BusyEvent(start=tr.start, end=tr.end, summary=str(summary) if summary else None)
            )
    return busy


def _translate(exc: Exception) -> Exception:
    """Une seule frontière de traduction, pour que les appelants ne voient jamais
    le vocabulaire du protocole."""
    if isinstance(exc, DavAuthError):
        return CalendarAuthError("invalid credentials")
    return CalendarError(str(exc))


class CaldavCalendarClient:
    async def list_calendars(self, creds: CalendarCredentials) -> list[CalendarInfo]:
        _guard(creds.server_url)
        try:
            async with DavSession(creds.server_url, creds.username, creds.password) as dav:
                xml = await dav.request("PROPFIND", creds.server_url, _PROP_PRINCIPAL)
                principal = first_href(xml, creds.server_url, ".//d:current-user-principal")
                if principal is None:
                    # Certains serveurs ne publient pas de principal et servent le
                    # calendar-home-set directement sur l'URL fournie. On tente,
                    # plutôt que d'échouer sur une absence qui n'est pas une panne.
                    principal = creds.server_url

                xml = await dav.request("PROPFIND", principal, _PROP_HOME)
                home = first_href(xml, principal, ".//c:calendar-home-set") or principal

                xml = await dav.request("PROPFIND", home, _PROP_CALENDARS, depth="1")
        except (DavAuthError, DavError) as exc:
            raise _translate(exc) from exc

        result: list[CalendarInfo] = []
        for href, resp in parse_multistatus(xml, home):
            rt = resp.find(".//d:resourcetype", NS)
            # Une collection qui n'est pas un calendrier — la racine du home, un
            # carnet d'adresses — répond à la même requête. Sans ce test, elles
            # apparaissent dans la liste et l'utilisateur en choisit une qui ne
            # contiendra jamais d'événement.
            if rt is None or rt.find("c:calendar", NS) is None:
                continue
            name_el = resp.find(".//d:displayname", NS)
            name = (name_el.text or "").strip() if name_el is not None else ""
            result.append(CalendarInfo(name=name or href, url=href))
        return result

    async def fetch_busy(
        self,
        creds: CalendarCredentials,
        calendar_url: str,
        start: datetime,
        end: datetime,
        *,
        default_timezone: str = "UTC",
    ) -> list[BusyEvent]:
        _guard(creds.server_url)
        _guard(calendar_url)
        body = _query_time_range(_ics_dt(start), _ics_dt(end))
        try:
            async with DavSession(creds.server_url, creds.username, creds.password) as dav:
                xml = await dav.request("REPORT", calendar_url, body, depth="1")
        except (DavAuthError, DavError) as exc:
            raise _translate(exc) from exc

        busy: list[BusyEvent] = []
        for _href, resp in parse_multistatus(xml, calendar_url):
            data = resp.find(".//c:calendar-data", NS)
            if data is None or not data.text:
                continue
            busy.extend(_busy_from_ical(data.text, default_timezone=default_timezone))
        return busy

    async def create_event(
        self,
        creds: CalendarCredentials,
        calendar_url: str,
        *,
        uid: str,
        summary: str,
        description: str,
        location: str,
        start: datetime,
        end: datetime,
        rrule: str | None = None,
    ) -> str:
        _guard(creds.server_url)
        _guard(calendar_url)
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//GhostCal//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_ics_dt(start)}",
            f"DTSTART:{_ics_dt(start)}",
            f"DTEND:{_ics_dt(end)}",
            f"SUMMARY:{_ics_text(summary)}",
            f"DESCRIPTION:{_ics_text(description)}",
            f"LOCATION:{_ics_text(location)}",
        ]
        # Sans cette ligne, un événement hebdomadaire arrive une fois sur le
        # téléphone et jamais ensuite. Publier une récurrence comme une occurrence
        # unique est pire que ne pas la publier : ça a l'air juste.
        if rrule:
            lines.append(f"RRULE:{rrule}")
        lines += ["END:VEVENT", "END:VCALENDAR"]
        ical = "\r\n".join(lines)

        # L'URL de l'objet est choisie par NOUS à partir de notre UID, ce que la
        # RFC 4791 autorise explicitement. C'est ce qui rend la suppression
        # ultérieure possible sans avoir à retenir l'URL rendue par le serveur.
        target = urljoin(calendar_url.rstrip("/") + "/", f"{uid}.ics")
        try:
            async with DavSession(creds.server_url, creds.username, creds.password) as dav:
                return await dav.put(target, ical)
        except (DavAuthError, DavError) as exc:
            raise _translate(exc) from exc

    async def delete_event(self, creds: CalendarCredentials, calendar_url: str, uid: str) -> None:
        _guard(creds.server_url)
        _guard(calendar_url)
        try:
            async with DavSession(creds.server_url, creds.username, creds.password) as dav:
                # On cherche par UID plutôt que de deviner l'URL : un événement
                # créé par une autre application y vit sous un nom que nous
                # n'avons pas choisi.
                xml = await dav.request("REPORT", calendar_url, _query_by_uid(uid), depth="1")
                hrefs = [h for h, _ in parse_multistatus(xml, calendar_url)]
                for href in hrefs:
                    await dav.delete(href)
        except DavAuthError as exc:
            raise _translate(exc) from exc
        except DavError:
            # Déjà parti, ou introuvable : rien à supprimer. C'était déjà le
            # comportement avant, et il est volontaire — la suppression est
            # idempotente.
            return
