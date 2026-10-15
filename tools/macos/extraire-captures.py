#!/usr/bin/env python3
"""Recompose les captures que `integration_test/macos_test.dart` a recrachées en base64.

    flutter test integration_test/macos_test.dart -d macos … \
      --dart-define=GHOSTCAL_CAPTURES_SORTIE=true | tee /tmp/campagne.txt
    tools/macos/extraire-captures.py /tmp/campagne.txt captures/

Pourquoi par la sortie du test plutôt qu'en lisant les fichiers : l'application est en bac
à sable, donc elle n'écrit que dans son conteneur, et macOS protège le conteneur d'une
application contre les autres processus. Sans « accès complet au disque » accordé au
terminal, `ls` sur le dossier qu'on vient de faire remplir rend « Operation not permitted ».
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    journal, dossier = Path(sys.argv[1]), Path(sys.argv[2])
    dossier.mkdir(parents=True, exist_ok=True)

    nom: str | None = None
    attendu = 0
    morceaux: list[str] = []
    ecrites = 0
    for ligne in journal.read_text(encoding="utf-8", errors="replace").splitlines():
        ligne = ligne.strip()
        if ligne.startswith("<<<CAPTURE "):
            _, nom, taille = ligne.split()
            attendu, morceaux = int(taille), []
        elif ligne == "CAPTURE>>>" and nom:
            texte = "".join(morceaux)
            # La longueur est annoncée puis vérifiée : une sortie tronquée donnerait une
            # image qui ne s'ouvre pas, et on la lirait comme un défaut du rendu.
            if len(texte) != attendu:
                sys.exit(f"{nom} : {len(texte)} caractères reçus pour {attendu} annoncés")
            (dossier / f"{nom}.png").write_bytes(base64.b64decode(texte))
            print(f"  {nom}.png")
            ecrites += 1
            nom = None
        elif nom is not None:
            morceaux.append(ligne)
    if not ecrites:
        sys.exit("Aucune capture dans ce journal : GHOSTCAL_CAPTURES_SORTIE était-il posé ?")


if __name__ == "__main__":
    main()
