"""Dépose un jeu de données **de vitrine**.

Ce qu'on photographie, et ce que l'examinateur d'Apple ouvrira.

    tools/amorcer_vitrine.py <api> <jeton> <organisation> <publique>
                             <calendrier> <amorcer> <slug-org>

─── Pourquoi ce fichier existe à côté de `amorcer_donnees.py` ───

Ils ne servent pas la même chose, et les confondre s'est vu en image.

`amorcer_donnees.py` amorce un banc **d'épreuve**. Il dépose délibérément un événement
scellé sous une autre clé, que l'agenda affiche en rouge : « Contenu illisible — clé
manquante ». C'est un comportement juste, et c'est ce qu'on veut éprouver — une ligne
absente se lirait « libre », ce qui serait un mensonge.

En vitrine, la même ligne se lit comme un bogue. La première capture App Store en portait
une, sur une journée qui ne comptait que deux entrées et laissait les deux tiers de l'écran
vides.

Ce fichier-ci ne dépose donc **rien qui échoue** : une journée pleine et plausible, des
tâches dont une en retard (c'est un état normal, pas une panne), un lien de réservation
actif, une réunion réellement réservée depuis la page publique, et un sondage voté.

─── Ce qu'il ne réécrit pas ───

La cryptographie. Les contenus sont scellés par le cœur Rust via `amorcer sceller`, comme
partout ailleurs. Un jeu de vitrine dont le chiffrement serait réimplémenté ici prouverait
la cohérence du script avec lui-même, et rien sur le produit.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import urllib.error
import urllib.request

api, jeton, organisation, publique, calendrier, amorcer, slug_org = sys.argv[1:8]

FUSEAU = "Europe/Zurich"
fautes = 0


def sceller(charge: dict) -> str:
    return subprocess.run(
        [amorcer, "sceller", publique, json.dumps(charge, ensure_ascii=False)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _appel(chemin: str, corps: dict | None, methode: str, authentifie: bool):
    """Rend l'objet décodé, ou `None` si le serveur a refusé.

    `None` veut dire « je n'ai pas pu », jamais « il n'y a rien » : chaque refus est
    imprimé et compté. Un amorçage qui se tait à moitié donne un écran à moitié vrai, et
    c'est ce qu'on photographierait sans le savoir.
    """
    global fautes
    # ─── L'agent utilisateur n'est pas cosmétique ───
    #
    # `cal.ghostsuite.cloud` est derrière Cloudflare, qui **bannit la signature de
    # `Python-urllib`** : toute requête sans agent déclaré rend `403 error code: 1010`,
    # « the owner of this website has banned your access based on your browser's
    # signature ». Ce n'est ni un jeton invalide ni un droit manquant, et le message ne
    # le dit pas — on cherche longtemps du côté de l'authentification.
    #
    # Constaté le 2026-09-25 : vingt-trois refus d'affilée sur l'amorçage de vitrine.
    # La même leçon est écrite dans `ghostpass/apps/ios/AppStore/fiche.md` depuis des
    # semaines. Elle n'avait pas traversé jusqu'ici.
    entetes = {
        "content-type": "application/json",
        "user-agent": "ghostcal-amorcage-vitrine/1.0",
    }
    if authentifie:
        entetes["authorization"] = f"Bearer {jeton}"
        entetes["x-organization-id"] = organisation
    requete = urllib.request.Request(
        f"{api}{chemin}",
        data=None if corps is None else json.dumps(corps).encode(),
        headers=entetes,
        method=methode,
    )
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            brut = reponse.read()
            return json.loads(brut) if brut else {}
    except urllib.error.HTTPError as erreur:
        detail = erreur.read()[:250].decode(errors="replace")
        print(f"  ✗ {methode} {chemin} → {erreur.code} {detail}", file=sys.stderr)
        fautes += 1
        return None


def poster(chemin, corps, authentifie=True):
    return _appel(chemin, corps, "POST", authentifie)


def lire(chemin, authentifie=True):
    return _appel(chemin, None, "GET", authentifie)


# Les horaires sont ancrés sur **aujourd'hui**, pas sur une date figée : une capture qui
# montrerait un agenda de l'an dernier se remarque, et Apple regarde les captures.
AUJOURD_HUI = dt.datetime.now().astimezone()


def a(jour: int, heure: int, minute: int = 0) -> dt.datetime:
    base = (AUJOURD_HUI + dt.timedelta(days=jour)).replace(
        hour=heure, minute=minute, second=0, microsecond=0
    )
    return base


def iso(moment: dt.datetime) -> str:
    return moment.isoformat()


# ── L'agenda du jour ──────────────────────────────────────────────────────────
#
# Cinq entrées sur la journée courante, et trois sur les suivantes pour que les flèches de
# navigation mènent quelque part. Des titres qui décrivent un vrai métier : un agenda de
# démonstration rempli de « Test 1 », « Test 2 » se voit immédiatement.
EVENEMENTS = [
    (0, 9, 0, 45, "Point hebdomadaire", "Tour de table de l'équipe produit", "Genève"),
    (
        0,
        10,
        30,
        60,
        "Entretien · développeuse back-end",
        "Deuxième tour, technique",
        "Visioconférence",
    ),
    (0, 12, 30, 60, "Déjeuner avec Camille", "", "Café du Marché"),
    (0, 14, 0, 90, "Revue de sprint", "Démonstration puis rétrospective", "Salle Jura"),
    (0, 16, 30, 30, "Appel client · Helvetia", "Point d'avancement mensuel", "Visioconférence"),
    (1, 9, 0, 60, "Atelier charte graphique", "Choix de la palette", "Salle Jura"),
    (1, 11, 0, 45, "Entretien · designer produit", "Premier tour", "Visioconférence"),
    (3, 8, 30, 120, "Comité de direction", "Budget du quatrième trimestre", "Genève"),
]

print("Agenda", file=sys.stderr)
for jour, heure, minute, duree, titre, description, lieu in EVENEMENTS:
    debut = a(jour, heure, minute)
    poster(
        "/v1/me/calendar/events",
        {
            "calendar_id": calendrier,
            "start_at": iso(debut),
            "end_at": iso(debut + dt.timedelta(minutes=duree)),
            "timezone": FUSEAU,
            "all_day": False,
            "content": sceller({"title": titre, "description": description, "location": lieu}),
        },
    )

# ── Les tâches ────────────────────────────────────────────────────────────────
#
# Une en retard : c'est un **état normal** d'une liste de tâches, pas une panne, et l'écran
# le montre bien. À ne pas confondre avec l'événement illisible du banc d'épreuve, qui est
# une panne montrée exprès et n'a rien à faire en vitrine.
TACHES = [
    ("Relire le devis Helvetia", "Retour attendu avant vendredi", 20),
    ("Préparer la revue de sprint", "Trois démonstrations à enchaîner", 4),
    ("Renouveler le passeport", "", -36),
    ("Réserver la salle pour l'atelier", "", 30),
    ("Idée : refondre le planning des astreintes", "Sans urgence", None),
]

print("Tâches", file=sys.stderr)
for titre, notes, heures in TACHES:
    corps = {"content": sceller({"title": titre, "notes": notes})}
    if heures is not None:
        corps["due_at"] = iso(AUJOURD_HUI + dt.timedelta(hours=heures))
    poster("/v1/me/tasks", corps)

# ── Les disponibilités ────────────────────────────────────────────────────────
#
# Sans horaire, la page publique ne propose **aucun** créneau et la réservation plus bas
# échoue. Le banc d'épreuve n'en posait pas : c'est la raison pour laquelle l'écran
# « Réunions » y restait vide, et pour laquelle deux captures manquaient.
print("Disponibilités", file=sys.stderr)
poster(
    "/v1/me/schedules",
    {
        "name": "Heures de bureau",
        "timezone": FUSEAU,
        # 0 = lundi, la convention du serveur. Celle de Dart est 1 = lundi et celle de Java
        # 1 = dimanche : confondre les trois décalerait tout l'horaire d'un jour, en silence.
        "rules": [{"weekday": j, "start": "09:00:00", "end": "17:00:00"} for j in range(5)],
        "overrides": [],
    },
)

# ── Les liens de réservation ──────────────────────────────────────────────────
# `EventTypeIn` **n'a pas de champ `slug`** : le serveur le dérive du titre et y ajoute un
# suffixe aléatoire — « Entretien de 30 minutes » devient
# `entretien-de-30-minutes-9dd94f`. Pydantic ignore en silence le `slug` qu'on lui
# passerait, si bien que le poser ici donne l'illusion de l'avoir choisi. Le premier jet
# réservait ensuite sur `/event-types/entretien/…` et recevait « event type not found ».
#
# On relit donc le slug attribué, au lieu de le supposer.
print("Types de rendez-vous", file=sys.stderr)
# `_slug` et non `slug` : il est DANS le tuple pour que la table se lise, et
# délibérément inutilisé — c'est le slug attribué par le serveur qu'on relit
# plus bas, pas celui qu'on propose. Le souligné dit au linter que l'oubli est
# voulu, sans retirer l'information de la table.
for titre, _slug, duree, actif, questions in [
    (
        "Entretien de 30 minutes",
        "entretien",
        30,
        True,
        [
            {
                "id": "sujet",
                "label": "Sujet de l'entretien",
                "type": "text",
                "required": True,
                "options": [],
            }
        ],
    ),
    ("Découverte de 15 minutes", "decouverte", 15, True, []),
    ("Atelier d'une demi-journée", "atelier", 240, False, []),
]:
    poster(
        "/v1/me/event-types",
        {
            "title": titre,
            "duration_min": duree,
            "slot_interval_min": 15,
            "buffer_before_min": 5,
            "buffer_after_min": 10,
            "min_notice_min": 60,
            "date_window_days": 60,
            "location_type": "google_meet",
            "active": actif,
            "kind": "solo",
            "capacity": 1,
            "questions": questions,
        },
    )

# ── Une vraie réservation, prise depuis la page publique ──────────────────────
#
# On passe par la route **publique**, comme un invité — et non par une insertion
# privilégiée. Une réunion fabriquée par un raccourci n'aurait pas de `invitee_private`
# scellé, et l'écran « Réunions » afficherait un détail vide : la capture montrerait
# précisément ce que le produit sait faire de moins bien.
print("Réunion réservée", file=sys.stderr)
reunions = 0
demain = a(1, 14, 0)

# Le slug attribué à « Entretien de 30 minutes ». On le cherche par son titre, pas par sa
# position dans la liste : l'ordre n'est garanti nulle part.
types = lire("/v1/me/event-types") or []
slug_entretien = next(
    (
        t["slug"]
        for t in types
        if isinstance(t, dict) and t.get("title", "").startswith("Entretien")
    ),
    None,
)
if slug_entretien is None:
    print("  ✗ le type « Entretien » est introuvable après création", file=sys.stderr)
    fautes += 1
# Les paramètres s'appellent `from` et `to`, **pas** `date_from`/`date_to` : ce sont des
# alias déclarés côté serveur (`Query(alias="from")`, `from` étant un mot réservé en
# Python). Le premier jet se les était inventés et le serveur a répondu 422 en nommant les
# champs manquants — un refus lisible, pour une fois. Et la route ne prend aucun fuseau.
creneaux = (
    lire(
        f"/v1/orgs/{slug_org}/event-types/{slug_entretien}/availability"
        f"?from={demain.date()}&to={a(4, 9).date()}",
        authentifie=False,
    )
    if slug_entretien
    else None
)
debut_reserve = None
if creneaux:
    plats = creneaux.get("slots") if isinstance(creneaux, dict) else creneaux
    if isinstance(plats, list) and plats:
        # Les créneaux portent `start`/`end`. On lit la clé plutôt que de supposer sa
        # présence : une forme inattendue doit se dire, pas se deviner.
        premier = plats[0]
        debut_reserve = premier.get("start") if isinstance(premier, dict) else premier
if debut_reserve is None:
    print(
        "  ✗ aucun créneau proposé : la réservation est sautée, l'écran Réunions restera vide",
        file=sys.stderr,
    )
    fautes += 1
else:
    # **Trois** réservations, pas une. Avec une seule ligne, l'écran Réunions est vide à
    # quatre-vingt-dix pour cent : mesuré sur la capture du 25 septembre. Un écran presque
    # vide en devanture suggère un produit que personne n'utilise.
    #
    # On prend des créneaux espacés dans la liste plutôt que les trois premiers, pour que
    # les rendez-vous tombent des jours différents — trois réunions collées dans la même
    # heure se liraient comme un jeu d'essai.
    invites = [
        (
            "Camille Rossier",
            "camille.rossier@example.com",
            "Reprise du projet de refonte",
            "Disponible aussi le lendemain matin si besoin.",
        ),
        ("Antoine Béguin", "antoine.beguin@example.com", "Migration de l'infrastructure", ""),
        (
            "Salomé Vuillemin",
            "salome.vuillemin@example.com",
            "Point budget du quatrième trimestre",
            "Merci de prévoir trente minutes de marge.",
        ),
    ]
    pas = max(1, len(plats) // (len(invites) + 1))
    for rang, (nom, adresse, sujet, notes) in enumerate(invites):
        indice = min(rang * pas, len(plats) - 1)
        creneau = plats[indice]
        depart = creneau.get("start") if isinstance(creneau, dict) else creneau
        charge = {"name": nom, "answers": {"sujet": sujet}}
        if notes:
            charge["notes"] = notes
        reserve = poster(
            f"/v1/orgs/{slug_org}/event-types/{slug_entretien}/bookings",
            {
                "start_at": depart,
                "invitee_email": adresse,
                "invitee_timezone": FUSEAU,
                "guest_emails": [],
                # Le nom et les réponses sont **scellés à l'organisation** : le serveur les
                # stocke sans pouvoir les lire. C'est le seul endroit du produit qui soit
                # vraiment de bout en bout, et c'est ce que l'écran Réunions déchiffre —
                # la capture le prouve en affichant « Camille Rossier ».
                "invitee_private": sceller(charge),
            },
            authentifie=False,
        )
        if reserve is not None:
            reunions += 1

# ── Un sondage, avec des votes ────────────────────────────────────────────────
print("Sondage", file=sys.stderr)
sondages = 0
sondage = poster(
    "/v1/me/polls",
    {
        "title": "Atelier charte graphique",
        "duration_min": 90,
        "location_type": "google_meet",
        "option_starts": [iso(a(2, 9)), iso(a(2, 14)), iso(a(3, 10, 30))],
    },
)
if sondage and sondage.get("options"):
    identifiants = [o["id"] for o in sondage["options"]]
    slug_sondage = sondage["slug"]
    for nom, adresse, choisis in [
        ("Camille Rossier", "camille.rossier@example.com", [0, 1]),
        ("Antoine Béguin", "antoine.beguin@example.com", [1]),
        ("Salomé Vuillemin", "salome.vuillemin@example.com", [1, 2]),
    ]:
        poster(
            f"/v1/polls/{slug_sondage}/votes",
            {
                "voter_name": nom,
                "voter_email": adresse,
                "option_ids": [identifiants[i] for i in choisis],
            },
            authentifie=False,
        )
    sondages = 1
else:
    print("  ✗ sondage non créé : l'écran Sondages restera vide", file=sys.stderr)
    fautes += 1

# Le bilan compte ce qui **est**, pas ce qui était prévu. Le premier jet annonçait
# « 1 réunion » depuis un littéral, sur une exécution où la réservation avait échoué :
# la ligne de résumé démentait la ligne d'erreur imprimée trois lignes plus haut. Un
# compte rendu qui se contredit lui-même est pire qu'absent — on retient le rassurant.
etat = lire("/v1/me/meetings")
reunions_vues = len(etat) if isinstance(etat, list) else "?"
print(
    f"\n{len(EVENEMENTS)} événements, {len(TACHES)} tâches, 3 types de rendez-vous, "
    f"1 horaire, {reunions} réunion(s) réservée(s) — le serveur en compte {reunions_vues} —, "
    f"{sondages} sondage(s) — {fautes} refus",
    file=sys.stderr,
)
# Un amorçage à moitié fait donne une vitrine à moitié vraie. On sort en défaut pour que
# l'appelant ne photographie pas sans le savoir.
sys.exit(1 if fautes else 0)
