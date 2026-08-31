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


def _as_utc_range(start_value: object, end_value: object) -> TimeRange | None:
    """Normalise le début et la fin d'un événement en une plage UTC."""

    def to_dt(value: object, *, end: bool) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, date):
            # Journée entière : couvre le jour complet, traité comme occupé.
            base = datetime.combine(value, time(0, 0), tzinfo=UTC)
            return base + timedelta(days=1) if end else base
        return None

    start = to_dt(start_value, end=False)
    end = to_dt(end_value, end=True)
    if start is None:
        return None
    if end is None or end <= start:
        end = start + timedelta(minutes=30)
    return TimeRange(start, end)


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
        self, creds: CalendarCredentials, calendar_url: str, start: datetime, end: datetime
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
            try:
                cal = ICalendar.from_ical(data.text)
            except Exception:
                # Un événement illisible ne doit pas faire échouer la fenêtre
                # entière : le reste du calendrier reste utilisable, et un créneau
                # manquant se voit, alors qu'une erreur globale masque tout.
                continue
            for comp in cal.walk("VEVENT"):
                if str(comp.get("transp", "")).upper() == "TRANSPARENT":
                    continue
                if str(comp.get("status", "")).upper() == "CANCELLED":
                    continue
                dtstart = comp.get("dtstart")
                dtend = comp.get("dtend")
                tr = _as_utc_range(dtstart.dt if dtstart else None, dtend.dt if dtend else None)
                if tr is not None:
                    summary = comp.get("summary")
                    busy.append(
                        BusyEvent(
                            start=tr.start, end=tr.end, summary=str(summary) if summary else None
                        )
                    )
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
