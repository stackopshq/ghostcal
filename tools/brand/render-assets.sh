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
# Pas de recadrage pour celle-ci : la plaque fournit déjà la marge, et l'y ajouter
# rapetisserait la silhouette dans son cadre sans raison.
MARQUE="$ROOT/apps/mobile/assets/marque"
mkdir -p "$MARQUE"
for facteur in 1 2 3; do
  taille=$((64 * facteur))
  rsvg-convert -w "$taille" -h "$taille" "$SOURCE" -o "$MARQUE/logo@${facteur}x.png"
done
cp "$MARQUE/logo@1x.png" "$MARQUE/logo.png"
printf '  %-32s %s\n' "assets/marque/logo*.png" "64/128/192 px, transparent"
