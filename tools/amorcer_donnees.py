"""Dépose de quoi remplir les cinq écrans du banc.

    tools/amorcer_donnees.py <api> <jeton> <organisation> <publique> <calendrier> <amorcer>

Les corps sont composés par un encodeur JSON, jamais par interpolation de chaînes : **un
contenu scellé est lui-même du JSON**. L'insérer entre guillemets casse le document, et le
serveur répond « JSON decode error » avec une position d'octet — un message qui n'oriente
vers rien. Le shell, lui, meurt sur une parenthèse non fermée. Les deux se sont produits en
écrivant ce banc.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import urllib.error
import urllib.request

api, jeton, organisation, publique, calendrier, amorcer = sys.argv[1:7]


def sceller(charge: dict, cle: str = publique) -> str:
    """Scelle un contenu avec le cœur Rust — jamais une réimplémentation.

    Un banc dont la cryptographie serait réécrite ici prouverait la cohérence du banc avec
    lui-même, et rien sur le produit.
    """
    return subprocess.run(
        [amorcer, "sceller", cle, json.dumps(charge, ensure_ascii=False)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def quand(heures: float) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=heures)).isoformat()


def poster(chemin: str, corps: dict) -> None:
    requete = urllib.request.Request(
        f"{api}{chemin}",
        data=json.dumps(corps).encode(),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {jeton}",
            "x-organization-id": organisation,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=15) as reponse:
            reponse.read()
    except urllib.error.HTTPError as erreur:
        # On dit ce que le serveur a refusé plutôt que de continuer en silence : un banc
        # qui s'amorce à moitié donne un écran à moitié vrai, ce qui est pire que rien.
        print(
            f"  ✗ {chemin} → {erreur.code} {erreur.read()[:200].decode(errors='replace')}",
            file=sys.stderr,
        )


def deja_amorce() -> bool:
    """Le banc a-t-il déjà ses données ?

    Sans ce contrôle, relancer le script empile les mêmes trois tâches à chaque fois — et
    l'écran finit par montrer neuf lignes là où on en attend trois, ce qui ressemble à un
    défaut du client.
    """
    requete = urllib.request.Request(
        f"{api}/v1/me/tasks",
        headers={"authorization": f"Bearer {jeton}", "x-organization-id": organisation},
    )
    with urllib.request.urlopen(requete, timeout=15) as reponse:
        return len(json.load(reponse)) > 0


if deja_amorce():
    print("  déjà amorcé — rien à déposer", file=sys.stderr)
    raise SystemExit(0)


# Une paire jetée aussitôt : personne ne pourra jamais ouvrir ce contenu-là. C'est ce qui
# permet de **voir** à l'écran la règle « ce qui ne se déchiffre pas s'affiche quand même ».
# Sans cette ligne, le banc ne montrerait que le cas heureux.
autre = json.loads(
    subprocess.run(
        [amorcer, "cles", "phrase d une autre personne", "recuperation d une autre personne"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
)["public_key"]

for contenu, debut, fin in [
    (
        sceller(
            {
                "title": "Point hebdomadaire",
                "description": "état des chantiers",
                "location": "Genève",
            }
        ),
        2,
        3,
    ),
    (
        sceller({"title": "Dentiste", "description": "contrôle annuel", "location": "Lausanne"}),
        26,
        27,
    ),
    (sceller({"title": "Scellé ailleurs", "description": "", "location": ""}, autre), 5, 6),
]:
    poster(
        "/v1/me/calendar/events",
        {
            "calendar_id": calendrier,
            "start_at": quand(debut),
            "end_at": quand(fin),
            "timezone": "Europe/Zurich",
            "all_day": False,
            "content": contenu,
        },
    )

for contenu, echeance in [
    (sceller({"title": "Relire le devis", "notes": "avant vendredi"}), 20),
    (sceller({"title": "Renouveler le passeport", "notes": ""}), -48),  # déjà en retard
    (sceller({"title": "Idée : refonte du planning", "notes": "sans urgence"}), None),
]:
    corps = {"content": contenu}
    if echeance is not None:
        corps["due_at"] = quand(echeance)
    poster("/v1/me/tasks", corps)

poster(
    "/v1/me/event-types",
    {
        "title": "Entretien de 30 minutes",
        "slug": "entretien",
        "duration_min": 30,
        "slot_interval_min": 15,
        "buffer_before_min": 5,
        "buffer_after_min": 10,
        "min_notice_min": 120,
        "date_window_days": 60,
        "location_type": "google_meet",
        "active": True,
        "kind": "solo",
        "capacity": 1,
        "questions": [
            {"id": "sujet", "label": "Sujet", "type": "text", "required": True, "options": []}
        ],
    },
)

print("  3 événements (dont un scellé ailleurs), 3 tâches, 1 type de rendez-vous", file=sys.stderr)
