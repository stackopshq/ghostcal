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
# La langue de la prise de vue. App Store Connect réclame un jeu **par langue** déclarée
# sur la fiche : une fiche bilingue dont une langue n'a pas de captures ne se soumet pas.
# Le français reste le défaut, c'est la langue source du produit.
LANGUE="${GHOSTCAL_LANGUE:-fr}"
case "$LANGUE" in
  fr|en) ;;
  *) echo "GHOSTCAL_LANGUE doit valoir fr ou en, pas « $LANGUE »" >&2; exit 2 ;;
esac
case "$APPAREIL" in
  iPad*) SORTIE="$MOBILE/AppStore/captures-ipad" ;;
esac
# Un répertoire par langue, pour la même raison qu'un répertoire par appareil : sans lui
# la seconde passe écraserait la première, et on s'en apercevrait devant App Store Connect.
[ "$LANGUE" = fr ] || SORTIE="$SORTIE-$LANGUE"

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

# ── Le banc parle-t-il la même langue que la prise de vue ? ───────────────────
#
# L'interface suit la langue du simulateur ; les **données** suivent celle de l'amorçage.
# Rien ne les lie, et c'est ainsi que le jeu anglais du 21 octobre est sorti avec des
# libellés anglais au-dessus d'un agenda français — « October 21 », « All calendars », et
# « Renouveler le passeport ». Aucun contrôle ne l'a vu : l'image était pleine, nette, aux
# bonnes dimensions. Il a fallu l'ouvrir.
#
# On compare donc le titre du premier type de rendez-vous à celui que
# `tools/amorcer_vitrine.py` dépose dans cette langue. C'est une donnée que l'amorçage
# pose toujours, et son titre diffère franchement d'une langue à l'autre.
ATTENDU="$([ "$LANGUE" = en ] && echo '30-minute interview' || echo 'Entretien de 30 minutes')"
TITRES="$(curl -s --max-time 5 "$API/v1/me/event-types" -H "authorization: Bearer $JETON" \
  | python3 -c 'import json,sys
try: print("\n".join(t.get("title","") for t in json.load(sys.stdin)))
except Exception: pass' 2>/dev/null || true)"

if ! printf '%s' "$TITRES" | grep -qxF "$ATTENDU"; then
  rouge "Le banc n'est pas amorcé en « $LANGUE »."
  echo "  Attendu un type de rendez-vous « $ATTENDU » ; le banc propose :" >&2
  printf '%s\n' "$TITRES" | sed 's/^/    /' >&2
  echo "  Réamorcez dans la bonne langue :" >&2
  echo "    GHOSTCAL_LANGUE=$LANGUE ./tools/banc-local.sh --vitrine" >&2
  echo "  (Photographier par-dessus donnerait des libellés d'une langue et des données" >&2
  echo "   de l'autre — ce que ni les dimensions ni le compte de teintes ne voient.)" >&2
  exit 2
fi
vert "banc amorcé en « $LANGUE »"

# ── …et amorcé AUJOURD'HUI ───────────────────────────────────────────────────
#
# La langue ne suffit pas : le semeur ancre ses événements sur **le jour où il tourne**.
# Jour 0 en porte cinq, jour +1 deux, jour +3 un seul. Un banc laissé debout de la veille
# reste donc dans la bonne langue, répond parfaitement — et l'agenda du jour n'affiche
# plus que les deux rendez-vous du lendemain d'hier.
#
# C'est ce qui est arrivé aux jeux anglais du 23 octobre, amorcés le 22 : la première
# image de la fiche, celle qui décide si quelqu'un fait défiler, montrait une journée aux
# trois quarts vide. Aucun contrôle ne l'a vu, et pour la même raison que d'habitude —
# l'image était pleine, nette, aux bonnes dimensions. Une journée creuse a autant de
# teintes qu'une journée chargée.
#
# On compte donc les événements du jour. Cinq sont attendus ; en dessous de quatre, le
# banc est d'un autre jour ou n'a pas fini de semer.
# `/v1/me/calendar/agenda`, et **pas** `/v1/me/calendar/events` : la seconde ne répond
# qu'au POST — un GET y rend 405, que le premier jet de ce contrôle a pris pour « zéro
# événement ». Il a donc crié au loup sur un banc parfaitement frais, ce qui est pire que
# de ne rien contrôler. Les bornes sont des horodatages ISO, pas des dates : avec des
# dates nues la route rend une liste vide sans se plaindre.
AUJOURD_HUI="$(date +%Y-%m-%d)"
DEMAIN="$(date -v+1d +%Y-%m-%d 2>/dev/null || date -d '+1 day' +%Y-%m-%d)"
NOMBRE="$(curl -s --max-time 5 \
  "$API/v1/me/calendar/agenda?from=${AUJOURD_HUI}T00:00:00Z&to=${DEMAIN}T00:00:00Z" \
  -H "authorization: Bearer $JETON" \
  | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(len(d if isinstance(d, list) else d.get("items", d.get("events", []))))
except Exception:
    print(-1)' 2>/dev/null || echo -1)"

if [ "$NOMBRE" = "-1" ]; then
  # On ne bloque pas sur une route qu'on ne sait pas lire : le contrôle doit protéger la
  # prise de vue, pas l'empêcher parce que l'API a changé de forme. Mais on le dit.
  echo "  (impossible de compter les événements du jour — contrôle de fraîcheur ignoré)" >&2
elif [ "$NOMBRE" -lt 4 ]; then
  rouge "Le banc n'a pas été amorcé aujourd'hui."
  echo "  $NOMBRE événement(s) le $AUJOURD_HUI, cinq attendus." >&2
  echo "  Le semeur ancre ses dates sur le jour où il tourne : un banc de la veille" >&2
  echo "  montre la journée du lendemain, qui est presque vide." >&2
  echo "  Arrêtez-le et réamorcez :" >&2
  echo "    pg_ctl -D \"\$TMPDIR/ghostcal-banc/pgdata\" stop ; pkill -f 'uvicorn ghostcal'" >&2
  echo "    GHOSTCAL_LANGUE=$LANGUE ./tools/banc-local.sh --vitrine" >&2
  exit 2
else
  vert "banc amorcé aujourd'hui — $NOMBRE événements le $AUJOURD_HUI"
fi

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
xcrun simctl spawn "$APPAREIL_ID" defaults write .GlobalPreferences AppleLanguages -array "$LANGUE" || true
# La **région**, et pas seulement la langue.
#
# `AppleLanguages` gouverne l'interface ; c'est `AppleLocale` qui date la barre d'état.
# Sur iPad — le seul appareil dont la barre porte une date — le jeu anglais du 22 octobre
# affichait « Jeudi 22 octobre » au-dessus d'une application entièrement anglaise. Ni le
# compte de teintes ni les dimensions ne voient ça, et l'application n'y est pour rien :
# c'est iOS qui écrit cette ligne, d'après une région restée française.
case "$LANGUE" in
  en) REGION="en_US" ;;
  *) REGION="fr_CH" ;;
esac
xcrun simctl spawn "$APPAREIL_ID" defaults write .GlobalPreferences AppleLocale -string "$REGION" || true

# Et on relance SpringBoard, sans quoi la barre d'état garde la langue d'avant.
#
# L'ordre impose cette gymnastique : on ne peut parler à un simulateur qu'une fois
# démarré — `simctl spawn` sur un appareil qui démarre encore **attend indéfiniment** —
# mais à ce moment-là SpringBoard a déjà dessiné sa barre. L'application, elle, lit ses
# préférences à son propre lancement et suit donc la nouvelle langue : d'où un écran
# entièrement anglais surmonté de « Jeudi 22 octobre ».
#
# Seul l'iPad porte une date dans sa barre, donc seul lui montrait le défaut. Le relancer
# coûte quelques secondes et vaut pour les deux appareils.
xcrun simctl spawn "$APPAREIL_ID" launchctl stop com.apple.SpringBoard >/dev/null 2>&1 || true
sleep 8


# ── Laisser passer les notifications de premier démarrage ────────────────────
#
# Un simulateur **neuf** — et ce script en crée un à chaque passe — reçoit ses
# notifications système d'accueil dans la minute qui suit son démarrage. Mesuré le
# 22 octobre : « Prêt pour Apple Intelligence » est tombé en plein sur la capture
# « 02-nouvel-evenement », barrant le tiers supérieur de l'écran et emportant avec lui
# l'habillage de la barre d'état.
#
# Aucun contrôle automatique ne voit un bandeau : l'image a les bonnes dimensions et des
# centaines de teintes. Seule l'ouvrir l'a montré, et il a fallu refaire les quatre jeux.
#
# Quatre-vingt-dix secondes coûtent six minutes sur l'ensemble et valent mieux qu'une
# reprise complète. Ce n'est pas un délai de confort : c'est le temps que met le système
# à dire ce qu'il a à dire.
dire "On laisse le système finir de se présenter (90 s)"
sleep 90

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
      # L'habillage de la barre d'état, **réappliqué avant chaque vue**.
      #
      # Mesuré le 21 octobre, et c'est une mesure et non une impression : sur les douze
      # images du jeu iPhone, « 02-nouvel-evenement » portait 88,6 % de pixels noirs dans
      # la bande centrale du haut, et les onze autres 0,0 %. Une capsule noire à la place
      # de l'Îlot dynamique, sur cette vue-là seulement, dans les deux langues.
      #
      # La cause est l'écran lui-même : il change le style de la barre d'état par le canal
      # natif ajouté pour corriger le contraste, iOS redessine alors la vraie barre, et le
      # dessin de `simctl status_bar override` posé au démarrage est perdu dans cette
      # région. L'heure figée à 9 h 41 survivait, ce qui rendait la perte invisible à tout
      # contrôle qui aurait regardé l'horloge.
      #
      # Réappliquer coûte quelques millisecondes et vaut pour toutes les vues, y compris
      # celles qui ne changent rien : un habillage qu'on repose est un habillage qu'on
      # n'a pas à supposer intact.
      xcrun simctl status_bar "$APPAREIL_ID" override \
        --time "09:41" --batteryState charged --batteryLevel 100 \
        --cellularMode active --cellularBars 4 --wifiMode active --wifiBars 3 \
        >/dev/null 2>&1 || true
      sleep 0.3
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

# La bande centrale du haut : là où l'Îlot dynamique se dessine en noir quand l'habillage
# de `simctl` a été perdu. Mesuré le 21 octobre : 88,6 % de pixels noirs sur l'écran
# fautif, 0,0 % sur les onze autres. Un seuil à 20 % sépare les deux sans ambiguïté.
#
# Ce contrôle existe parce que le précédent ne voyait rien : une capsule noire ne change
# ni les dimensions ni le nombre de teintes. Sur iPad il n'y a pas d'îlot, et la mesure
# rend naturellement zéro.
noirs = -1.0
bande = fichier + ".bande.png"
bandebmp = fichier + ".bande.bmp"
try:
    L, H = int(largeur), int(hauteur)
    subprocess.run(
        ["sips", "--cropOffset", str(int(H * 0.012)), str(int(L * 0.36)),
         "-c", str(max(1, int(H * 0.040))), str(max(1, int(L * 0.28))),
         fichier, "--out", bande],
        capture_output=True, text=True,
    )
    subprocess.run(["sips", "-s", "format", "bmp", bande, "--out", bandebmp],
                   capture_output=True, text=True)
    d = open(bandebmp, "rb").read()
    depart = int.from_bytes(d[10:14], "little")
    pas = int.from_bytes(d[28:30], "little") // 8
    if depart and pas:
        px = d[depart:]
        points = [px[i:i + 3] for i in range(0, len(px) - pas, pas)]
        if points:
            noirs = sum(1 for q in points if max(q) < 40) / len(points)
except (OSError, ValueError):
    noirs = -1.0
for f in (bande, bandebmp):
    try: os.remove(f)
    except OSError: pass

print(f"{largeur} {hauteur} {couleurs} {noirs:.3f}")
PY
)"

  if [[ "$mesure" == "ILLISIBLE" || -z "$mesure" ]]; then
    gris "$nom — illisible : `sips` n'a pas rendu de dimensions. Rien n'est mesuré."
    fautes=$((fautes + 1))
    continue
  fi

  read -r largeur hauteur couleurs noirs <<<"$mesure"

  if (( couleurs < 0 )); then
    gris "$nom — ${largeur}×${hauteur}, mais le contenu n'a pas pu être examiné"
    fautes=$((fautes + 1))
  elif (( couleurs < 50 )); then
    # Une capture d'application en compte des milliers. Cinquante est très large : le seuil
    # n'est pas là pour juger du graphisme, seulement pour distinguer une image d'un aplat.
    rouge "$nom — ${largeur}×${hauteur}, mais seulement $couleurs couleurs : image vide"
    fautes=$((fautes + 1))
  elif awk -v n="$noirs" 'BEGIN { exit !(n > 0.20) }'; then
    rouge "$nom — ${largeur}×${hauteur} : une capsule noire en haut au centre"
    echo "    $(awk -v n="$noirs" 'BEGIN { printf "%.1f", n * 100 }') % de pixels noirs là où l'Îlot dynamique se dessine." >&2
    echo "    L'habillage de la barre d'état a été perdu — un écran qui change son style," >&2
    echo "    ou un bandeau système passé par-dessus. Refaites cette passe." >&2
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
