"""Le strict nécessaire du protocole CalDAV, écrit ici plutôt qu'emprunté.

POURQUOI CE FICHIER EXISTE. La bibliothèque ``caldav`` tire obligatoirement
``icalendar-searcher``, qui est sous AGPL-3.0-or-later. L'AGPL est du copyleft
fort : l'embarquer dans un service distribué contamine l'ensemble, et empêchait
GhostCal de rejoindre l'Elastic License 2.0 comme les sept autres produits de la
suite. Vérifié avant d'écrire une ligne : aucune version de ``caldav`` n'ouvre de
porte de sortie. Les 3.x tirent toutes la dépendance, et les 2.x et antérieures
s'en passent mais sont elles-mêmes en GPL simple, sans la double licence Apache
que les 3.x offrent. Les deux voies bloquent, pour deux raisons différentes.

CE QU'ON EN UTILISAIT, ET DONC CE QU'IL FALLAIT REFAIRE. Six verbes : découvrir
le principal, lister les agendas, chercher dans une fenêtre, écrire un événement,
le retrouver par UID, le supprimer. C'est du HTTP avec quelques méthodes de plus
et du XML en réponse — pas un domaine où l'on a besoin d'une abstraction.

CE QUI N'EST PAS IMPLÉMENTÉ, ET C'EST DÉLIBÉRÉ. Pas de découverte par
``.well-known``, pas de synchronisation par jeton, pas de gestion des collections
partagées, pas de free-busy REPORT. GhostCal ne s'en sert pas. Ajouter ce qu'on
n'utilise pas, c'est reprendre le coût qu'on vient de poser.
"""

from __future__ import annotations

from urllib.parse import urljoin
from xml.etree.ElementTree import Element

import httpx
from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]

# L'analyse XML passe par defusedxml et non par la bibliothèque standard : l'URL
# du serveur est fournie par l'utilisateur, donc la réponse est hostile par
# défaut. `xml.etree.ElementTree` développe les entités et se fait déplier par un
# « billion laughs » en quelques kilo-octets.

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
NS = {"d": DAV, "c": CALDAV}

_PROP_PRINCIPAL = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>"""

_PROP_HOME = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><c:calendar-home-set/></d:prop></d:propfind>"""

_PROP_CALENDARS = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:"><d:prop>
  <d:resourcetype/><d:displayname/>
</d:prop></d:propfind>"""


def _query_time_range(start: str, end: str) -> str:
    # `expand` est ce qui transforme une récurrence en occurrences réelles. Sans
    # lui, un événement hebdomadaire ne compte qu'une fois comme occupé et le
    # créneau paraît libre les semaines suivantes — faux, et silencieux.
    return f"""<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <c:calendar-data><c:expand start="{start}" end="{end}"/></c:calendar-data>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range start="{start}" end="{end}"/>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""


def _query_by_uid(uid: str) -> str:
    # `collation="i;octet"` : une comparaison octet pour octet. Nos UID sont des
    # identifiants opaques que nous avons émis ; une collation qui replie la casse
    # pourrait faire correspondre deux événements distincts et en supprimer un de
    # trop.
    safe = (
        uid.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><d:getetag/></d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:prop-filter name="UID">
          <c:text-match collation="i;octet">{safe}</c:text-match>
        </c:prop-filter>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""


class DavAuthError(Exception):
    """Le serveur a refusé les identifiants (401 ou 403)."""


class DavError(Exception):
    """Tout le reste : réseau, statut inattendu, XML illisible."""


class DavSession:
    """Une session authentifiée sur un serveur CalDAV.

    Sert de contexte asynchrone pour que la connexion soit fermée même quand une
    requête lève — un client httpx laissé ouvert retient un socket jusqu'au
    ramasse-miettes, ce qui ne se voit pas en test et se voit en production.
    """

    def __init__(self, base_url: str, username: str, password: str, *, timeout: float = 30.0):
        self._base = base_url
        self._client = httpx.AsyncClient(
            auth=(username, password),
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "GhostCal"},
        )

    async def __aenter__(self) -> DavSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def request(self, method: str, url: str, body: str | None, depth: str = "0") -> str:
        headers = {"Depth": depth}
        if body is not None:
            headers["Content-Type"] = 'application/xml; charset="utf-8"'
        try:
            r = await self._client.request(method, url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise DavError(str(exc)) from exc
        if r.status_code in (401, 403):
            raise DavAuthError(f"HTTP {r.status_code}")
        # 207 Multi-Status est LA réponse normale de PROPFIND et REPORT. Un 200 y
        # est acceptable mais rare ; tout le reste est une erreur, y compris les
        # 2xx que certains serveurs renvoient à tort.
        if r.status_code not in (200, 207):
            raise DavError(f"HTTP {r.status_code}")
        return r.text

    async def put(self, url: str, ical: str) -> str:
        try:
            r = await self._client.put(
                url, content=ical.encode(), headers={"Content-Type": "text/calendar; charset=utf-8"}
            )
        except httpx.HTTPError as exc:
            raise DavError(str(exc)) from exc
        if r.status_code in (401, 403):
            raise DavAuthError(f"HTTP {r.status_code}")
        if r.status_code not in (200, 201, 204):
            raise DavError(f"HTTP {r.status_code}")
        return url

    async def delete(self, url: str) -> None:
        try:
            r = await self._client.delete(url)
        except httpx.HTTPError as exc:
            raise DavError(str(exc)) from exc
        if r.status_code in (401, 403):
            raise DavAuthError(f"HTTP {r.status_code}")
        # 404 sur une suppression est un succès : l'objectif est qu'il ne soit
        # plus là, et il n'y est pas.
        if r.status_code not in (200, 204, 404):
            raise DavError(f"HTTP {r.status_code}")


def parse_multistatus(xml: str, base_url: str) -> list[tuple[str, Element]]:
    """Rend une liste de (href absolu, élément <propstat>) pour chaque réponse.

    Les href sont souvent relatifs — c'est permis par la norme et fréquent chez
    Nextcloud comme chez iCloud. Les résoudre ici évite que chaque appelant se
    trompe à sa façon.
    """
    try:
        root = SafeET.fromstring(xml)
    except Exception as exc:
        raise DavError(f"XML illisible : {exc}") from exc
    out: list[tuple[str, Element]] = []
    for resp in root.findall("d:response", NS):
        href_el = resp.find("d:href", NS)
        if href_el is None or not href_el.text:
            continue
        out.append((urljoin(base_url, href_el.text.strip()), resp))
    return out


def first_href(xml: str, base_url: str, path: str) -> str | None:
    """Extrait le premier href niché sous `path`, résolu en absolu."""
    try:
        root = SafeET.fromstring(xml)
    except Exception as exc:
        raise DavError(f"XML illisible : {exc}") from exc
    el = root.find(path, NS)
    if el is None:
        return None
    href = el.find("d:href", NS)
    if href is None or not href.text:
        return None
    return str(urljoin(base_url, href.text.strip()))
