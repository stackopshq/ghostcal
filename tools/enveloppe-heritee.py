#!/usr/bin/env python3
"""Dépose dans le banc un événement au format que le web écrivait AVANT la migration.

    ./tools/banc-local.sh                 # dans une autre fenêtre
    uv run python tools/enveloppe-heritee.py

─── Pourquoi ce script existe, et pourquoi il réimplémente la cryptographie ───

Réimplémenter la cryptographie dans un banc est normalement une faute : on prouve alors
que le banc est cohérent avec lui-même, et rien sur le produit. `tools/amorcer_donnees.py`
le dit en toutes lettres et passe par le cœur Rust.

Ici c'est l'inverse, et c'est le sujet. Le cœur **n'écrit plus** l'ancien format — il ne
sait que le lire. Pour éprouver qu'un compte de production ouvre encore ses données
d'avant la migration, il faut donc produire une enveloppe que le cœur ne produit plus.

La réimplémentation est **vérifiée avant usage** contre le vecteur réel du dépôt
(`suite/crates/ghost-crypto/tests/legacy_web.rs`), qui vient de WebCrypto et non de ce
crate : si l'algorithme dérivait, le contrôle échouerait avant d'avoir rien déposé.

─── Ce que l'ancien format a de différent ───

AES-256-GCM avec un nonce de 12 octets, et **pas de clé `v`** dans l'enveloppe. Le format
actuel est XChaCha20-Poly1305, nonce de 24 octets, `v: 1`. La dérivation de clé, elle, n'a
pas changé : X25519 puis HKDF-SHA256 sur le domaine.

─── Qui s'en sert ───

`apps/mobile/integration_test/macos_test.dart`, qui vérifie que la ligne s'affiche à son
titre et non « Contenu illisible ». À relancer après chaque `banc-local.sh`, qui repart
d'une base vide et emporte ce dépôt avec elle.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

API = os.environ.get("GHOSTCAL_API", "http://127.0.0.1:8099")
EMAIL = os.environ.get("GHOSTCAL_EMAIL", "clara@example.com")
MOTDEPASSE = os.environ.get("GHOSTCAL_MOTDEPASSE", "banc-local-ghostcal-jetable-2026")
DOMAINE = "ghostcal-zk-v1"
TITRE = "Web avant migration"

# Le préfixe PKCS#8 d'une clé privée X25519, tel que WebCrypto l'émet. Les 48 octets sont
# ces 16-là puis les 32 de la clé.
PREFIXE_PKCS8 = bytes.fromhex("302e020100300506032b656e04220420")

B64 = lambda b: base64.b64encode(b).decode()  # noqa: E731


def _cle(prive: X25519PrivateKey, pair: X25519PublicKey, domaine: str) -> bytes:
    partage = prive.exchange(pair)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=domaine.encode()).derive(
        partage
    )


def sceller_herite(publique_b64: str, clair: bytes, domaine: str) -> str:
    """Scelle vers une clé publique, à l'ancienne : AES-GCM, nonce de 12, pas de `v`."""
    ephemere = X25519PrivateKey.generate()
    cle = _cle(ephemere, X25519PublicKey.from_public_bytes(base64.b64decode(publique_b64)), domaine)
    nonce = os.urandom(12)
    return json.dumps(
        {
            "nonce": B64(nonce),
            "encrypted_target": B64(AESGCM(cle).encrypt(nonce, clair, None)),
            "epk": B64(ephemere.public_key().public_bytes_raw()),
        },
        separators=(",", ":"),
    )


def ouvrir_herite(privee_pkcs8_b64: str, blob: str, domaine: str) -> bytes:
    env = json.loads(blob)
    assert "v" not in env, "ce n'est pas une enveloppe héritée"
    prive = X25519PrivateKey.from_private_bytes(
        base64.b64decode(privee_pkcs8_b64)[len(PREFIXE_PKCS8) :]
    )
    cle = _cle(prive, X25519PublicKey.from_public_bytes(base64.b64decode(env["epk"])), domaine)
    return AESGCM(cle).decrypt(
        base64.b64decode(env["nonce"]), base64.b64decode(env["encrypted_target"]), None
    )


def controler() -> None:
    """Le vecteur de `legacy_web.rs`, produit par WebCrypto. S'il ne s'ouvre pas, on
    s'arrête : déposer une enveloppe fabriquée de travers ferait échouer le témoin en
    accusant l'application."""
    vecteur = (
        '{"nonce":"S7zH0JfXlYxxIfYu","encrypted_target":"WB+N2vaTKcWIgMhnbnoYqo4U+CPB'
        'nyZ52lhqsUWAzeEHK/scb/HIjsRxD7Hp6CR9","epk":"mYFpBqLknLyvNHmzG7buBrJU6IKFxmw'
        '+cSTBXiTY7Bk="}'
    )
    # Clé jetable, créée pour ces vecteurs et qui ne protège rien.
    privee = "MC4CAQAwBQYDK2VuBCIEICgZYk9PD9l9b63sJ4+ZuQlqD8SbUtRE2L4SoXut2wFy"  # gitleaks:allow
    attendu = "Déjeuner avec Camille — 12:30"
    obtenu = ouvrir_herite(privee, vecteur, DOMAINE).decode()
    if obtenu != attendu:
        sys.exit(f"Le vecteur du dépôt ne s'ouvre pas : {obtenu!r} au lieu de {attendu!r}")
    print(f"  contrôle : le vecteur WebCrypto s'ouvre → {obtenu!r}", file=sys.stderr)


def appel(chemin, corps=None, jeton=None, organisation=None):
    requete = urllib.request.Request(
        API + chemin,
        method="POST" if corps is not None else "GET",
        data=json.dumps(corps).encode() if corps is not None else None,
        headers={
            k: v
            for k, v in {
                "content-type": "application/json" if corps is not None else None,
                "authorization": f"Bearer {jeton}" if jeton else None,
                "x-organization-id": organisation,
            }.items()
            if v
        },
    )
    try:
        with urllib.request.urlopen(requete) as reponse:
            return json.load(reponse) if reponse.status != 204 else None
    except urllib.error.HTTPError as e:
        sys.exit(f"{chemin} → {e.code} {e.read()[:300].decode(errors='replace')}")
    except urllib.error.URLError as e:
        sys.exit(f"{API} injoignable ({e.reason}). Le banc tourne-t-il ?")


def main() -> None:
    controler()

    jeton = appel("/v1/auth/login", {"email": EMAIL, "password": MOTDEPASSE})["access_token"]
    organisation = appel("/v1/me/organizations", jeton=jeton)[0]["id"]
    publique = appel("/v1/auth/zk-keys", jeton=jeton)[0]["public_key"]
    calendrier = appel("/v1/me/calendars", jeton=jeton, organisation=organisation)[0]["id"]

    # Dans trois heures : assez loin pour rester devant nous le temps d'une campagne, assez
    # près pour tomber dans la fenêtre que toutes les vues chargent.
    debut = dt.datetime.now(dt.UTC) + dt.timedelta(hours=3)
    contenu = sceller_herite(
        publique,
        json.dumps(
            {
                "title": TITRE,
                "description": "ecrit par l ancien web",
                "location": "Nyon",
            },
            ensure_ascii=False,
        ).encode(),
        DOMAINE,
    )
    cree = appel(
        "/v1/me/calendar/events",
        {
            "calendar_id": calendrier,
            "start_at": debut.isoformat(),
            "end_at": (debut + dt.timedelta(hours=1)).isoformat(),
            "timezone": "Europe/Zurich",
            "all_day": False,
            "content": contenu,
        },
        jeton=jeton,
        organisation=organisation,
    )
    local = debut.astimezone()
    print(f"« {TITRE} » déposé à {local:%H:%M} — {cree['id']}", file=sys.stderr)


if __name__ == "__main__":
    main()
