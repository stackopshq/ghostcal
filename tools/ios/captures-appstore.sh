#!/usr/bin/env bash
# Produit les captures d'écran de la fiche App Store, et **regarde** ce qu'elle a produit.
#
#   ./tools/ios/captures-appstore.sh                             # iPhone 17 Pro Max
#   GHOSTCAL_APPAREIL='iPad Pro 13-inch (M4)' ./tools/ios/captures-appstore.sh
#   ./tools/ios/captures-appstore.sh --mesurer   # relit les images déjà prises
#
# `--mesurer` existe pour que les contrôles soient **éprouvables** : on peut effacer une
# image, l'aplatir, et vérifier que le contrôle rougit — sans refaire trois minutes de
# construction. Un contrôle qu'on ne peut pas casser à volonté n'est jamais éprouvé, et
# un contrôle jamais éprouvé finit par être cru sur parole.
#
# Les fichiers atterrissent dans `apps/mobile/AppStore/captures/` (ou `captures-ipad/`),
# numérotés dans l'ordre où ils doivent être déposés.
#
# ─── Ce que le banc doit fournir ───
#
# `tools/banc-local.sh` doit tourner : un PostgreSQL jetable, le serveur sur 8099, et un
# compte amorcé. Un agenda vide se photographie très bien et ne montre rien.
#
# Ce script **vérifie** que le banc répond avant de démarrer un simulateur. Découvrir
# l'absence de serveur après trois minutes de construction, par un écran de connexion
# photographié cinq fois, est une façon coûteuse d'apprendre.
#
# ─── Pourquoi `simctl` et pas `binding.takeScreenshot()` ───
#
# Apple exige des dimensions exactes et refuse toute image redimensionnée après coup. Le
# simulateur 6,9 pouces rend nativement 1320 × 2868 ; `takeScreenshot` rendrait la surface
# Flutter, dont les dimensions suivent le rendu logique. Les vues sont donc **prises** dans
# le simulateur, jamais fabriquées — et les dimensions obtenues sont relevées à la prise de
# vue, non écrites d'avance.
#
# ─── Quel jeu de données, et pourquoi ça compte ───
#
# `./tools/banc-local.sh --vitrine`, **pas** le banc d'épreuve.
#
# Le jeu d'épreuve dépose exprès un événement scellé sous une autre clé, que l'agenda
# affiche en rouge « Contenu illisible — clé manquante ». C'est juste, et c'est ce qu'on
# veut éprouver : une ligne absente se lirait « libre ». En devanture, la même ligne se lit
# comme un bogue — et la première version de ces captures en portait une, sur une journée
# à deux entrées laissant les deux tiers de l'écran vides.
#
# Le jeu de vitrine pose en plus un horaire de disponibilité, une réunion réservée depuis
# la page publique et un sondage voté. Sans eux, « Réunions » et « Sondages » sont des
# écrans vides, et deux captures manquent.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MOBILE="$RACINE/apps/mobile"
PAQUET="ch.stackops.ghostcal"

API="${GHOSTCAL_API:-http://127.0.0.1:8099}"
EMAIL="${GHOSTCAL_EMAIL:-clara@example.com}"
PHRASE="${GHOSTCAL_PHRASE:-banc-local-ghostcal-jetable-2026}"
APPAREIL="${GHOSTCAL_APPAREIL:-iPhone 17 Pro Max}"

SORTIE="$MOBILE/AppStore/captures"
case "$APPAREIL" in
  iPad*) SORTIE="$MOBILE/AppStore/captures-ipad" ;;
esac

MESURER_SEULEMENT=0
[[ "${1:-}" == "--mesurer" ]] && MESURER_SEULEMENT=1

dire() { printf "\n\033[1m▸ %s\033[0m\n" "$*" >&2; }

# `timeout` n'existe pas de base sur macOS, et `gtimeout` suppose coreutils. On borne donc
# l'attente nous-mêmes : on lance `bootstatus` en fond et on le tue s'il s'éternise.
attendre_le_demarrage() {
  local appareil="$1" limite=180 attendu=0 pid
  xcrun simctl bootstatus "$appareil" -b >/dev/null 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if (( attendu >= limite )); then
      kill -9 "$pid" 2>/dev/null
      wait "$pid" 2>/dev/null || true
      return 1
    fi
    sleep 2
    attendu=$((attendu + 2))
  done
  wait "$pid" 2>/dev/null || true
  return 0
}
vert() { printf "\033[32m✓ %s\033[0m\n" "$*"; }
rouge() { printf "\033[31m✗ %s\033[0m\n" "$*"; }
gris() { printf "\033[33m· %s\033[0m\n" "$*"; }

APPAREIL_ID=""
SURVEILLANT=""

nettoyer() {
  local code=$?
  [[ -n "$SURVEILLANT" ]] && kill "$SURVEILLANT" 2>/dev/null || true
  # On n'éteint que ce qu'on a allumé : jamais un balayage, qui tuerait le simulateur
  # d'un autre travail en cours.
  if [[ -n "$APPAREIL_ID" ]]; then
    xcrun simctl shutdown "$APPAREIL_ID" >/dev/null 2>&1 || true
    xcrun simctl delete "$APPAREIL_ID" >/dev/null 2>&1 || true
  fi
  exit $code
}
trap nettoyer EXIT INT TERM

if (( MESURER_SEULEMENT )); then
  # On saute la prise de vue et on va droit aux contrôles, plus bas.
  :
else

# ── Le banc, avant tout le reste ──────────────────────────────────────────────
dire "Le banc répond-il ?"
JETON="$(curl -s --max-time 5 -X POST "$API/v1/auth/login" \
  -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PHRASE\"}" 2>/dev/null \
  | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["access_token"])
except Exception: pass' 2>/dev/null || true)"

if [[ -z "$JETON" ]]; then
  rouge "Pas de session sur $API."
  echo "  Montez le banc d'abord :  ./tools/banc-local.sh" >&2
  echo "  (Un simple 200 sur une autre route ne prouverait rien : seule une connexion" >&2
  echo "   réelle établit que le compte existe et que sa phrase est la bonne.)" >&2
  exit 2
fi
vert "connexion réelle établie sur $API"

# ── Simulateur à la bonne taille ──────────────────────────────────────────────
dire "Simulateur « $APPAREIL »"
# `export`, et non une affectation en tête de commande : celle-ci ne vaudrait que pour
# `xcrun`, à gauche du tuyau, alors que c'est `python3` qui lit la variable à droite.
# Le symptôme était un « KeyError: APPAREIL » à la première exécution.
export APPAREIL
TYPE="$(xcrun simctl list devicetypes -j | python3 -c '
import json, os, sys
nom = os.environ["APPAREIL"]
for d in json.load(sys.stdin)["devicetypes"]:
    if d["name"] == nom:
        print(d["identifier"]); break
else:
    sys.exit(f"appareil « {nom} » inconnu de ce Xcode")
')"
RUNTIME="$(xcrun simctl list runtimes -j | python3 -c '
import json, sys
r = [x for x in json.load(sys.stdin)["runtimes"] if x["isAvailable"] and "iOS" in x["name"]]
print(sorted(r, key=lambda x: [int(n) for n in x["version"].split(".")])[-1]["identifier"])
')"
APPAREIL_ID="$(xcrun simctl create "captures-appstore-ghostcal" "$TYPE" "$RUNTIME")"
xcrun simctl boot "$APPAREIL_ID" >/dev/null 2>&1 || true
# `bootstatus` **sans garde-fou se pend**, et il se pend en emportant le sous-système.
# Observé le 25 septembre après une vingtaine de cycles création/démarrage/suppression :
# deux processus `simctl bootstatus` restés en vie indéfiniment, que ni le `trap` de ce
# script ni un `pkill` sur son propre nom n'atteignaient — ils ne portent pas son nom. Le
# script suivant repartait, se bloquait au même endroit, et n'affichait rien de plus que
# « ▸ Simulateur ». Une attente muette ressemble à une construction lente.
#
# Trois minutes suffisent très largement à démarrer un simulateur ; au-delà, c'est qu'il
# ne démarrera pas. On le dit, et on continue : le `flutter drive` qui suit échouera de
# façon lisible, plutôt que de laisser ce script pendu pour toujours.
if ! attendre_le_demarrage "$APPAREIL_ID"; then
  gris "le simulateur n'a pas confirmé son démarrage en trois minutes — on tente quand même"
  gris "(si la suite échoue : killall -9 com.apple.CoreSimulator.CoreSimulatorService)"
fi

# La langue du simulateur, **après** le démarrage et pas avant.
#
# `simctl spawn` sur un appareil qui démarre encore ne rend pas une erreur : il **attend**,
# et il attend indéfiniment. Le `|| true` qui suivait protégeait le code de sortie, pas le
# blocage — la nuance a coûté quatre prises de vue, chacune restée quinze minutes sur
# « ▸ Simulateur » sans rien imprimer de plus. Une attente muette ressemble à une
# construction lente ; c'est ce qui la rend coûteuse.
#
# Le remède n'est pas un délai, c'est l'ordre : on ne parle à un simulateur qu'une fois
# qu'il a dit être prêt.
xcrun simctl spawn "$APPAREIL_ID" defaults write .GlobalPreferences AppleLanguages -array fr || true


# Barre d'état figée : c'est l'usage pour une fiche App Store, et cela évite qu'une heure
# ou un niveau de batterie différents à chaque prise fassent croire à des captures
# hétérogènes. 9 h 41 est l'heure des présentations d'Apple.
xcrun simctl status_bar "$APPAREIL_ID" override \
  --time "09:41" --batteryState charged --batteryLevel 100 \
  --cellularMode active --cellularBars 4 --wifiMode active --wifiBars 3 \
  >/dev/null 2>&1 || true

# ── Le surveillant du dossier d'échange ───────────────────────────────────────
#
# L'application dépose `<nom>.demande` dans son propre `tmp` quand elle est prête à être
# photographiée, puis attend que le fichier disparaisse. Ce surveillant tire la photo et
# efface le témoin.
#
# Le conteneur n'existe qu'une fois l'application installée : le chemin est donc résolu à
# chaque tour, jamais mémorisé.
mkdir -p "$SORTIE"
surveiller() {
  local conteneur=""
  while true; do
    if [[ -z "$conteneur" ]]; then
      conteneur="$(xcrun simctl get_app_container "$APPAREIL_ID" "$PAQUET" data 2>/dev/null || true)"
      [[ -z "$conteneur" ]] && { sleep 1; continue; }
    fi
    local echange="$conteneur/tmp/ghostcal-captures"
    for demande in "$echange"/*.demande; do
      [[ -e "$demande" ]] || continue
      local nom
      nom="$(basename "$demande" .demande)"
      # Un instant de repos : le témoin est écrit depuis le fil de l'interface, et la
      # dalle peut avoir un cadre de retard sur ce que Flutter croit avoir posé.
      sleep 0.4
      xcrun simctl io "$APPAREIL_ID" screenshot --type png "$SORTIE/$nom.png" >/dev/null 2>&1
      printf '  📷 %s\n' "$nom" >&2
      rm -f "$demande"
    done
    sleep 0.3
  done
}
surveiller &
SURVEILLANT=$!

# ── Le tour de la boutique ────────────────────────────────────────────────────
dire "Construction, installation, et promenade"
# `127.0.0.1` vu depuis le simulateur est bien le Mac : le simulateur partage sa pile
# réseau. Un appareil réel, lui, ne l'atteindrait pas.
(cd "$MOBILE" && flutter drive \
  --driver=test_driver/integration_test.dart \
  --target=integration_test/captures_test.dart \
  -d "$APPAREIL_ID" \
  --dart-define=GHOSTCAL_SERVEUR="${API#http://}" \
  --dart-define=GHOSTCAL_EMAIL="$EMAIL" \
  --dart-define=GHOSTCAL_PHRASE="$PHRASE")

kill "$SURVEILLANT" 2>/dev/null || true
SURVEILLANT=""

fi  # fin de la prise de vue

# ── Regarder ce qu'on a produit ───────────────────────────────────────────────
#
# **La partie qui compte.** GhostPass a versé dans son dépôt cinq images blanches, de la
# bonne taille et du bon nom, avant que quiconque ne les ouvre. Un fichier qui existe n'est
# pas une capture ; une capture de la bonne taille n'est pas une capture qui montre
# quelque chose.
#
# Trois contrôles, et le troisième est celui qui aurait attrapé les images blanches.
dire "Ce que valent les images"
fautes=0
attendues=(01-agenda 02-nouvel-evenement 03-taches 04-reunions 05-rendez-vous 06-reglages)

for nom in "${attendues[@]}"; do
  fichier="$SORTIE/$nom.png"
  if [[ ! -f "$fichier" ]]; then
    rouge "$nom — ABSENTE : la prise de vue n'a pas eu lieu"
    fautes=$((fautes + 1))
    continue
  fi

  mesure="$(FICHIER="$fichier" python3 <<'PY'
import os, subprocess, sys

fichier = os.environ["FICHIER"]
sortie = subprocess.run(
    ["sips", "-g", "pixelWidth", "-g", "pixelHeight", fichier],
    capture_output=True, text=True,
)
dims = {}
for ligne in sortie.stdout.splitlines():
    if ":" in ligne:
        cle, _, val = ligne.strip().partition(":")
        dims[cle.strip()] = val.strip()
largeur, hauteur = dims.get("pixelWidth"), dims.get("pixelHeight")
if not largeur or not hauteur:
    print("ILLISIBLE")
    sys.exit()

# Combien de couleurs distinctes ? Une image blanche — ou noire — en a une poignée.
# C'est le contrôle qui manquait à GhostPass : ses cinq images avaient la bonne taille,
# le bon nom, et rien dedans.
#
# On passe par un BMP réduit à 64 pixels de côté. Deux raisons, la seconde mesurée :
#
# · lire 3,7 millions de pixels pour compter des couleurs serait long pour une réponse
#   qui tient en un ordre de grandeur ;
# · **`sips` ne sait pas écrire de `rgbs`.** Le premier jet le lui demandait ; la
#   conversion échouait, le fichier brut n'existait pas, et le contrôle rendait « le
#   contenu n'a pas pu être examiné » sur cinq images parfaitement lisibles. Il avait au
#   moins la décence de le dire en jaune plutôt qu'en vert — mais il ne mesurait rien.
#   `bmp` et `tiff` passent ; `bmp` se décode en quatre lignes sans dépendance.
mini = fichier + ".mesure.png"
bmp = fichier + ".mesure.bmp"
subprocess.run(["sips", "-Z", "64", fichier, "--out", mini], capture_output=True, text=True)
subprocess.run(["sips", "-s", "format", "bmp", mini, "--out", bmp], capture_output=True, text=True)
couleurs = -1
try:
    d = open(bmp, "rb").read()
    depart = int.from_bytes(d[10:14], "little")
    pas = int.from_bytes(d[28:30], "little") // 8
    if depart and pas:
        px = d[depart:]
        couleurs = len({px[i:i + 3] for i in range(0, len(px) - pas, pas)})
except OSError:
    couleurs = -1
for f in (mini, bmp):
    try: os.remove(f)
    except OSError: pass

print(f"{largeur} {hauteur} {couleurs}")
PY
)"

  if [[ "$mesure" == "ILLISIBLE" || -z "$mesure" ]]; then
    gris "$nom — illisible : `sips` n'a pas rendu de dimensions. Rien n'est mesuré."
    fautes=$((fautes + 1))
    continue
  fi

  read -r largeur hauteur couleurs <<<"$mesure"

  if (( couleurs < 0 )); then
    gris "$nom — ${largeur}×${hauteur}, mais le contenu n'a pas pu être examiné"
    fautes=$((fautes + 1))
  elif (( couleurs < 50 )); then
    # Une capture d'application en compte des milliers. Cinquante est très large : le seuil
    # n'est pas là pour juger du graphisme, seulement pour distinguer une image d'un aplat.
    rouge "$nom — ${largeur}×${hauteur}, mais seulement $couleurs couleurs : image vide"
    fautes=$((fautes + 1))
  else
    vert "$nom — ${largeur}×${hauteur}, $couleurs teintes"
  fi
done

echo
echo "Dossier : ${SORTIE#"$RACINE"/}"
cat >&2 <<'FIN'

Ces contrôles distinguent une image vide d'une image pleine. Ils ne savent pas dire si un
texte est **coupé sous la ligne de flottaison** : une section tronquée à mi-ligne a autant
de couleurs qu'une section entière, et se lit comme complète tant qu'on ne l'ouvre pas.
GhostPass a livré une capture iPad dans cet état.

Ouvrez chaque image et regardez-la. C'est la seule mesure qui reste à faire à la main.
FIN

exit $(( fautes > 0 ))
