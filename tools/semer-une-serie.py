#!/usr/bin/env python3
"""Dépose une série récurrente sur le banc, avec un rappel posé « comme le web ».

    ./tools/banc-local.sh                 # dans une autre fenêtre
    python3 tools/semer-une-serie.py      # rend l'identifiant de la série

─── Pourquoi un semoir, et pas l'application ───

L'application ne sait pas **créer** une série : `nouvel_evenement.dart` ne lit `rrule` que
depuis un détail existant. Elle sait la modifier et la supprimer, et c'est précisément ce
qu'il faut éprouver — une modification qui perdait `rrule`, `exdates` et
`reminder_minutes`, parce que la route `PUT` remplace l'enregistrement entier.

Le rappel est posé **ici** et non par l'application, exprès : c'est le cas qui a cassé.
Un rappel réglé depuis le web vit dans `reminder_minutes`, un champ que l'application
n'affiche pas et doit pourtant renvoyer tel quel.

─── Ce que ce script ne réimplémente pas ───

Le scellement passe par le binaire `amorcer` du cœur Rust, comme `amorcer_donnees.py`. Un
banc dont la cryptographie serait réécrite ici prouverait sa cohérence avec lui-même et
rien sur le produit. La clé publique est **lue sur le serveur** (`/v1/auth/zk-keys`) et non
redérivée : les clés sont fabriquées à l'inscription et le banc ne les redonne pas.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("GHOSTCAL_API", "http://127.0.0.1:8099")
EMAIL = os.environ.get("GHOSTCAL_EMAIL", "clara@example.com")
PHRASE = os.environ.get("GHOSTCAL_PHRASE", "banc-local-ghostcal-jetable-2026")
AMORCER = os.environ.get("AMORCER", "apps/mobile/rust/target/debug/amorcer")

TITRE = os.environ.get("GHOSTCAL_TITRE_SERIE", "Série d'épreuve")
RRULE = os.environ.get("GHOSTCAL_RRULE", "FREQ=WEEKLY;COUNT=5")
RAPPEL = int(os.environ.get("GHOSTCAL_RAPPEL", "30"))


def appeler(chemin: str, corps=None, methode="GET", entetes=None):
    requete = urllib.request.Request(
        f"{API}{chemin}",
        data=None if corps is None else json.dumps(corps).encode(),
        method=methode,
        headers={"content-type": "application/json", **(entetes or {})},
    )
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            brut = reponse.read()
            return json.loads(brut) if brut else None
    except urllib.error.HTTPError as erreur:
        # Un 422 nu ne nomme pas le champ ; le corps, si. Sans cela on cherche à l'aveugle.
        sys.exit(f"{methode} {chemin} → {erreur.code} : {erreur.read().decode()[:300]}")


jetons = appeler("/v1/auth/login", {"email": EMAIL, "password": PHRASE}, methode="POST")
acces = jetons["access_token"]
auth = {"authorization": f"Bearer {acces}"}

cles = appeler("/v1/auth/zk-keys", entetes=auth)
publique = cles[-1]["public_key"]
organisation = cles[-1]["organization_id"]
entetes = {**auth, "x-organization-id": organisation}
calendrier = appeler("/v1/me/calendars", entetes=entetes)[0]["id"]

# ─── D'abord retirer les séries qui traînent ───
#
# Un témoin interrompu laisse sa série derrière lui, parfois déjà renommée. Le témoin
# cherche « la série » par son `rrule`, et en trouverait alors une dont le titre n'est plus
# celui qu'il attend : il échouerait en accusant l'application, pour un désordre du banc.
# Mesuré — deux exécutions interrompues ont suffi.
debut_fenetre = (dt.datetime.now(dt.UTC) - dt.timedelta(days=30)).isoformat()
fin_fenetre = (dt.datetime.now(dt.UTC) + dt.timedelta(days=300)).isoformat()
parametres = urllib.parse.urlencode({"from": debut_fenetre, "to": fin_fenetre})
lignes = appeler(f"/v1/me/calendar/agenda?{parametres}", entetes=entetes)
retirees = 0
for identifiant_connu in {
    ligne["event_id"] for ligne in lignes if isinstance(ligne, dict) and ligne.get("event_id")
}:
    existant = appeler(f"/v1/me/calendar/events/{identifiant_connu}", entetes=entetes)
    if existant.get("rrule"):
        appeler(f"/v1/me/calendar/events/{identifiant_connu}", methode="DELETE", entetes=entetes)
        retirees += 1
if retirees:
    print(f"{retirees} série(s) résiduelle(s) retirée(s)")

scelle = subprocess.run(
    [
        AMORCER,
        "sceller",
        publique,
        json.dumps(
            {"title": TITRE, "description": "pour éprouver la récurrence", "location": "Genève"},
            ensure_ascii=False,
        ),
    ],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()

# Demain, à une heure fixe : une série dont la première occurrence est passée se lirait
# mal dans l'agenda, et le témoin la chercherait au mauvais endroit.
debut = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).replace(
    hour=9, minute=0, second=0, microsecond=0
)

cree = appeler(
    "/v1/me/calendar/events",
    {
        "calendar_id": calendrier,
        "start_at": debut.isoformat().replace("+00:00", "Z"),
        "end_at": (debut + dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "timezone": "Europe/Zurich",
        "all_day": False,
        "rrule": RRULE,
        "exdates": [],
        "content": scelle,
        "reminder_minutes": RAPPEL,
    },
    methode="POST",
    entetes=entetes,
)

identifiant = cree["id"] if isinstance(cree, dict) else ""
relu = appeler(f"/v1/me/calendar/events/{identifiant}", entetes=entetes)

# Le contrôle avant de rendre la main : ce qu'on vient de poser est bien là. Sans lui, un
# témoin rouge accuserait l'application d'avoir perdu ce que le banc n'a jamais écrit.
for champ, attendu in (("rrule", RRULE), ("reminder_minutes", RAPPEL), ("exdates", [])):
    if relu.get(champ) != attendu:
        sys.exit(f"le banc n'a pas retenu {champ} : {relu.get(champ)!r} au lieu de {attendu!r}")

print(f"« {TITRE} » déposée — {identifiant}")
print(f"  rrule={relu['rrule']} reminder_minutes={relu['reminder_minutes']}")
print(f"  exdates={relu['exdates']}")
print(f"  début={relu['start_at']}")
