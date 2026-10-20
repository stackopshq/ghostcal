#!/usr/bin/env bash
# Rend les images de marque de l'application depuis la source vectorielle de la charte.
#
#   ./tools/brand/render-assets.sh
#
# Les PNG sont des *sorties* : les retoucher à la main condamne le prochain changement de
# teinte à de la peinture pixel. La source est le SVG de la suite, et cette commande est
# la seule façon de produire les PNG.
#
# Le cadrage de l'icône n'est **pas** décidé ici : il l'est par `tools/brand/icone-ios.py`
# de la suite, qui mesure la silhouette et la ramène à la proportion de la charte. C'est
# ce qui fait que GhostCal et GhostPass se ressemblent sur l'écran d'accueil — mesuré le
# 2026-08-31 : la même recette naïve leur donnait 89,0 % et 80,1 % de hauteur, un écart
# invisible sur une capture isolée et flagrant quand les deux sont côte à côte.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUITE="${GHOSTSUITE:-$ROOT/../suite}"
SOURCE="$SUITE/assets/ghostcal/favicon.svg"
OUTIL="$SUITE/tools/brand/icone-ios.py"

command -v rsvg-convert >/dev/null || {
  echo "rsvg-convert introuvable — brew install librsvg" >&2
  exit 1
}
[[ -f "$SOURCE" && -x "$OUTIL" ]] || {
  echo "Charte de la suite introuvable sous $SUITE." >&2
  echo "Réglez GHOSTSUITE sur la racine du dépôt de la suite." >&2
  exit 1
}

"$OUTIL" "$SOURCE" "$ROOT/apps/mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset"

# LogoMark : la silhouette sur fond **transparent**, pour l'enseigne de l'écran d'entrée.
# Elle est posée sur une plaque dessinée par l'application, qui doit rester visible
# derrière — un fond aplati ici ferait un carré au milieu de la plaque.
#
# **Recadrée comme l'icône**, contrairement à ce que j'avais d'abord écrit ici : la plaque
# fournit une marge autour de l'image, pas autour de la silhouette. Sans recadrage, celle-ci
# remplit sa boîte bord à bord et paraît à l'étroit — vérifié à l'écran, les pattes du
# fantôme touchaient le bas de la plaque quand celles de GhostPass respiraient.
MARQUE="$ROOT/apps/mobile/assets/marque"
mkdir -p "$MARQUE"
CADRE="$(mktemp -t ghostcal-marque).svg"
trap 'rm -f "$CADRE"' EXIT
"$OUTIL" --cadre "$CADRE" "$SOURCE"
for facteur in 1 2 3; do
  taille=$((64 * facteur))
  rsvg-convert -w "$taille" -h "$taille" "$CADRE" -o "$MARQUE/logo@${facteur}x.png"
done
cp "$MARQUE/logo@1x.png" "$MARQUE/logo.png"
printf '  %-32s %s\n' "assets/marque/logo*.png" "64/128/192 px, transparent"

# Android launcher icon source, framed like the iOS one and flattened on the charte
# background. It used to be a bitmap rendered from the favicon framing, where the ghost
# touches the top edge: 1.6 % margin above, 9.4 % below, measured 2026-10-15.
# `flutter_launcher_icons` then derives the mipmaps (Android only; iOS comes from above).
rsvg-convert -w 1024 -h 1024 -b "#21222C" "$CADRE" -o "$ROOT/apps/mobile/assets/icone.png"
printf '  %-32s %s\n' "assets/icone.png" "1024 px, then: dart run flutter_launcher_icons"

# ─── L'icône macOS : la même silhouette, un gabarit qui n'est pas celui d'iOS ───
#
# `icone-ios.py` ne sert pas ici, et pas par oubli. iOS rogne lui-même l'icône en carré
# arrondi : on lui donne donc une image **pleine page**, et c'est ce que l'outil produit.
# macOS, lui, affiche le PNG tel quel. La même image pleine page y donnerait un carré
# blanc franc dans le Dock, au milieu de voisines qui sont toutes des plaques arrondies
# posées sur du vide.
#
# Le gabarit est donc celui d'Apple pour macOS, et ses valeurs sont **relevées sur l'icône
# Flutter qu'on remplace** plutôt que recopiées d'une documentation : boîte alpha mesurée
# à 94..929 × 100..939 sur 1024, c'est-à-dire une plaque de 824 à (100, 100) et une ombre
# qui déborde de six pixels. On garde cette géométrie — elle est celle de toutes les icônes
# du système, et s'en écarter ferait une icône qui ne flotte pas à la même hauteur que ses
# voisines.
#
# macOS 26 rogne de lui-même les icônes anciennes à la nouvelle forme. Une plaque déjà
# arrondie y survit sans dommage ; une image pleine page, elle, ne tiendrait que là. Le
# produit se déploie à partir de macOS 12 : le gabarit ancien est le seul qui vaille des
# deux côtés.
MACOS="$ROOT/apps/mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset"
PLAQUE="$(mktemp -t ghostcal-plaque).png"
GABARIT="$(mktemp -t ghostcal-macos).svg"
trap 'rm -f "$CADRE" "$PLAQUE" "$GABARIT"' EXIT

# **Aplatie sur blanc**, comme l'icône claire d'iOS : la plaque est le fond, et un fond
# transparent laisserait voir le bureau à travers le fantôme.
rsvg-convert -w 824 -h 824 -b '#ffffff' "$CADRE" -o "$PLAQUE"
{
  printf '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1024" height="1024" viewBox="0 0 1024 1024">\n'
  printf '<defs><clipPath id="plaque"><rect x="100" y="100" width="824" height="824" rx="185" ry="185"/></clipPath>\n'
  printf '<filter id="ombre" x="-12%%" y="-12%%" width="124%%" height="128%%"><feDropShadow dx="0" dy="12" stdDeviation="12" flood-color="#000000" flood-opacity="0.26"/></filter></defs>\n'
  printf '<g filter="url(#ombre)"><rect x="100" y="100" width="824" height="824" rx="185" ry="185" fill="#ffffff"/></g>\n'
  printf '<image clip-path="url(#plaque)" x="100" y="100" width="824" height="824" xlink:href="data:image/png;base64,'
  base64 < "$PLAQUE" | tr -d '\n'
  printf '"/>\n</svg>\n'
} > "$GABARIT"

# Les tailles sont celles que `Contents.json` nomme — lues, pas recopiées, pour la même
# raison que dans `icone-ios.py` : une taille ajoutée et oubliée ici donnerait une icône
# floue sans que rien ne le signale.
for taille in $(python3 -c '
import json, sys
from pathlib import Path
images = json.loads(Path(sys.argv[1], "Contents.json").read_text())["images"]
tailles = {int(round(float(i["size"].split("x")[0]) * float(i["scale"].rstrip("x")))) for i in images}
print(*sorted(tailles))
' "$MACOS"); do
  rsvg-convert -w "$taille" -h "$taille" "$GABARIT" -o "$MACOS/app_icon_$taille.png"
done
printf '  %-32s %s\n' "macos/…/AppIcon.appiconset" "16 → 1024 px, plaque arrondie"
