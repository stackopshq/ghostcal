#!/usr/bin/env bash
# Rend l'icône de l'application depuis la source vectorielle de la charte.
#
# Les PNG du catalogue Xcode sont des *sorties* : les retoucher à la main condamne le
# prochain changement de teinte à de la peinture pixel. La source est le SVG, et cette
# commande est la seule façon de produire les PNG.
#
#   ./tools/brand/render-assets.sh
#
# ─── Le décalage vertical, et pourquoi il ne va pas de soi ───
#
# `assets/ghostcal/favicon.svg` est cadré pour un **favicon** : la silhouette touche le
# bord haut, ce qui est sans conséquence à 16 px et même souhaitable. Une icône
# d'application, elle, est rognée en carré arrondi et posée à côté de ses voisines : sans
# marge, le fantôme est coupé au sommet et paraît décentré vers le haut.
#
# GhostPass résout cela dans sa propre copie, dont le viewBox porte un `-21.4` vertical.
# Plutôt que de retoucher le SVG canonique — qui dit lui-même « ne pas retoucher :
# régénérer » — on réécrit le viewBox **au moment du rendu**, avec le même décalage, pour
# que les deux applications se ressemblent sur l'écran d'accueil.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUITE="${GHOSTSUITE:-$ROOT/../suite}"
SOURCE="$SUITE/assets/ghostcal/favicon.svg"
ICONES="$ROOT/apps/mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset"
DECALAGE_VERTICAL=-21.4

command -v rsvg-convert >/dev/null || {
  echo "rsvg-convert introuvable — brew install librsvg" >&2
  exit 1
}
[[ -f "$SOURCE" ]] || {
  echo "Source de charte introuvable : $SOURCE" >&2
  echo "Réglez GHOSTSUITE sur la racine du dépôt de la suite." >&2
  exit 1
}

CADRE="$(mktemp -t ghostcal-icone).svg"
trap 'rm -f "$CADRE"' EXIT
python3 - "$SOURCE" "$CADRE" "$DECALAGE_VERTICAL" <<'PY'
import re, sys

source, sortie, decalage = sys.argv[1], sys.argv[2], float(sys.argv[3])
svg = open(source, encoding="utf-8").read()

trouve = re.search(r'viewBox="([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"', svg)
if not trouve:
    sys.exit("Le SVG de charte n'a pas de viewBox exploitable : le cadrage doit être vérifié à la main.")

x, y, largeur, hauteur = (float(v) for v in trouve.groups())
svg = svg[: trouve.start()] + f'viewBox="{x} {y + decalage} {largeur} {hauteur}"' + svg[trouve.end() :]
open(sortie, "w", encoding="utf-8").write(svg)
PY

# **Sans canal alpha** : l'App Store refuse une icône transparente. On aplatit sur du
# blanc, comme GhostPass — un fond sombre ferait de GhostCal l'intrus de la famille sur
# l'écran d'accueil, et le fantôme cyan y perd son contraste.
rendre() { rsvg-convert -w "$1" -h "$1" -b white "$CADRE" -o "$2"; }

# Les tailles sont lues dans le catalogue plutôt que recopiées : une taille ajoutée par
# Xcode et oubliée ici donnerait une icône floue, sans erreur nulle part.
python3 - "$ICONES/Contents.json" <<'PY' | while read -r fichier taille; do
import json, sys
vues = set()
for image in json.load(open(sys.argv[1]))["images"]:
    nom = image.get("filename")
    if not nom or nom in vues:
        continue
    vues.add(nom)
    cote = float(image["size"].split("x")[0]) * float(image["scale"].rstrip("x"))
    print(nom, int(round(cote)))
PY
  rendre "$taille" "$ICONES/$fichier"
  printf '  %-32s %s px\n' "$fichier" "$taille"
done

echo "Icônes rendues depuis ${SOURCE#"$ROOT"/}"
