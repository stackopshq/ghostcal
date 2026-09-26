#!/usr/bin/env bash
# Construit l'archive de diffusion de GhostCal, l'exporte en .ipa, et **mesure** ce qu'elle
# contient avant de dire qu'elle est prête.
#
#   ./tools/ios/archiver-appstore.sh              # archive + export + contrôles
#   ./tools/ios/archiver-appstore.sh --archive    # s'arrête après l'archive
#
# Ce script ne soumet rien. L'envoi est une décision qui se prend ailleurs ; la dernière
# section imprime les commandes, elle ne les lance pas.
#
# ─── Quel projet iOS ───
#
# Il en existe **deux** dans ce dépôt, et ils portent le même nom de produit :
#
#   apps/ios/Ghostcal.xcodeproj        SwiftUI, remplacé par le Flutter, ne part pas
#   apps/mobile/ios/Runner.xcodeproj   celui-ci
#
# Se tromper donnerait une archive qui se construit, se signe, et n'est pas l'application.
# Le chemin est donc écrit en dur et vérifié au démarrage, jamais découvert par un `find`.
#
# ─── Pourquoi `xcodebuild` et pas `flutter build ipa` ───
#
# `flutter build ipa` fait bien les deux étapes, mais avale la sortie d'`xcodebuild` et
# rend un message d'échec de signature qui ne dit pas quel profil manquait. Les deux
# commandes séparées laissent le diagnostic lisible — et c'est la signature qui casse, pas
# la compilation.
#
# `flutter build ios --config-only` reste nécessaire avant : il écrit
# `ios/Flutter/Generated.xcconfig`, où vivent `FLUTTER_BUILD_NAME` et
# `FLUTTER_BUILD_NUMBER` que l'Info.plist interpole. Sans lui, `xcodebuild` seul produit
# une version vide, qu'App Store Connect refuse sans dire pourquoi.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MOBILE="$RACINE/apps/mobile"
PROJET="$MOBILE/ios/Runner.xcodeproj"
EXPORT_OPTIONS="$MOBILE/ios/ExportOptions.plist"
SORTIE="$MOBILE/build/appstore"
ARCHIVE="$SORTIE/Runner.xcarchive"
EQUIPE="9WHCJ5W7S6"

ARRET_APRES_ARCHIVE=0
[[ "${1:-}" == "--archive" ]] && ARRET_APRES_ARCHIVE=1

dire() { printf "\n\033[1m▸ %s\033[0m\n" "$*" >&2; }
vert() { printf "\033[32m✓ %s\033[0m\n" "$*"; }
rouge() { printf "\033[31m✗ %s\033[0m\n" "$*"; }
gris() { printf "\033[33m· %s\033[0m\n" "$*"; }

[[ -d "$PROJET" ]] || { rouge "Projet introuvable : $PROJET"; exit 2; }
[[ -f "$EXPORT_OPTIONS" ]] || { rouge "ExportOptions.plist introuvable : $EXPORT_OPTIONS"; exit 2; }

# ── Archive ───────────────────────────────────────────────────────────────────
dire "Configuration Flutter (écrit Generated.xcconfig)"
(cd "$MOBILE" && flutter build ios --config-only --release)

dire "Archive Release, équipe $EQUIPE"
rm -rf "$ARCHIVE"
mkdir -p "$SORTIE"
# `-workspace`, pas `-project` : les greffons Flutter passent par CocoaPods, et le schéma
# ne se résout que depuis l'espace de travail.
#
# `DEVELOPMENT_TEAM` est **imposée** sur la ligne de commande et non laissée au projet : un
# certificat d'équipe personnelle vit dans le trousseau de cette machine, et la signature
# automatique peut le choisir sans le dire.
xcodebuild archive \
  -workspace "$MOBILE/ios/Runner.xcworkspace" \
  -scheme Runner \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE" \
  DEVELOPMENT_TEAM="$EQUIPE" \
  -allowProvisioningUpdates

APP="$ARCHIVE/Products/Applications/Runner.app"
[[ -d "$APP" ]] || { rouge "L'archive ne contient pas Runner.app"; exit 1; }

# ── Ce que l'archive prouve ───────────────────────────────────────────────────
#
# Chacun de ces contrôles a trois issues possibles, et le dit : vert, rouge, ou « je n'ai
# pas pu regarder ». Un contrôle qui rend vert quand il n'a rien lu est pire que pas de
# contrôle, puisqu'on le croit.
dire "Ce que contient l'archive"
fautes=0

controler() {
  local nom="$1" attendu="$2" obtenu="$3"
  if [[ -z "$obtenu" ]]; then
    gris "$nom — illisible : rien à mesurer"
    fautes=$((fautes + 1))
  elif [[ "$obtenu" == "$attendu" ]]; then
    vert "$nom — $obtenu"
  else
    rouge "$nom — attendu « $attendu », obtenu « $obtenu »"
    fautes=$((fautes + 1))
  fi
}

lire_plist() {
  /usr/libexec/PlistBuddy -c "Print :$1" "$APP/Info.plist" 2>/dev/null || true
}

controler "identifiant de paquet" "ch.stackops.ghostcal" "$(lire_plist CFBundleIdentifier)"
# `plutil -extract … json`, et non `PlistBuddy`. Le second imprime un tableau pour
# l'œil — « Array { 1 2 } » — et le découper à coups de `tr` donnait « Array{ 1 2 } ».
# Le contrôle rougissait sur une application parfaitement universelle : c'était
# l'instrument qui était faux, pas l'objet mesuré. `plutil` rend « [1,2] », une forme
# qui ne se lit pas de travers.
controler "famille d'appareils (1 = iPhone, 2 = iPad)" "[1,2]" \
  "$(plutil -extract UIDeviceFamily json -o - "$APP/Info.plist" 2>/dev/null)"

VERSION="$(lire_plist CFBundleShortVersionString)"
BUILD="$(lire_plist CFBundleVersion)"
if [[ -z "$VERSION" || -z "$BUILD" ]]; then
  gris "version — illisible dans l'Info.plist"
  fautes=$((fautes + 1))
elif [[ "$VERSION" == *'$'* || "$BUILD" == *'$'* ]]; then
  # Le symptôme d'un `Generated.xcconfig` absent : l'interpolation n'a pas eu lieu et la
  # version part littéralement comme « $(FLUTTER_BUILD_NAME) ».
  rouge "version — non interpolée : « $VERSION ($BUILD) ». Generated.xcconfig manquait."
  fautes=$((fautes + 1))
else
  vert "version — $VERSION ($BUILD)"
fi

# Le manifeste de confidentialité de l'application. Ceux des greffons vivent dans leurs
# propres bundles ; celui-ci doit être à la racine du paquet, et c'est celui qu'Apple
# réclame depuis mai 2024.
if [[ -f "$APP/PrivacyInfo.xcprivacy" ]]; then
  if plutil -lint "$APP/PrivacyInfo.xcprivacy" >/dev/null 2>&1; then
    vert "manifeste de confidentialité de l'application — présent et valide"
  else
    rouge "manifeste de confidentialité — présent mais illisible par plutil"
    fautes=$((fautes + 1))
  fi
else
  rouge "manifeste de confidentialité — ABSENT du paquet"
  echo "    Il ne suffit pas que le fichier existe dans ios/Runner/ : il doit figurer" >&2
  echo "    dans la phase « Resources » de la cible Runner du projet Xcode." >&2
  fautes=$((fautes + 1))
fi

# L'équipe de signature, relevée sur l'archive et non sur ce qu'on a demandé.
EQUIPE_LUE="$(codesign -dvv "$APP" 2>&1 | sed -n 's/^TeamIdentifier=//p')"
controler "équipe de signature" "$EQUIPE" "$EQUIPE_LUE"

# Le **type** d'identité, et non l'équipe. Les deux sont indépendants : une archive
# correctement signée par l'équipe 9WHCJ5W7S6 l'est normalement avec une identité
# « Apple Development » — c'est l'export qui la resigne en « Apple Distribution ».
# Relevé ici pour information, tranché plus bas sur l'IPA, qui est ce qui part.
IDENTITE="$(codesign -dvv "$APP" 2>&1 | sed -n 's/^Authority=//p' | head -1)"
if [[ -z "$IDENTITE" ]]; then
  gris "identité de signature — illisible"
  fautes=$((fautes + 1))
else
  gris "identité de signature — $IDENTITE (l'export la remplace par une identité de diffusion)"
fi

if codesign --verify --deep --strict "$APP" 2>/dev/null; then
  vert "signature — codesign --verify --deep --strict passe"
else
  rouge "signature — codesign --verify --deep --strict échoue"
  fautes=$((fautes + 1))
fi

# La déclaration de chiffrement. Elle est **délibérément absente** — voir docs/appstore.md.
if /usr/libexec/PlistBuddy -c 'Print :ITSAppUsesNonExemptEncryption' "$APP/Info.plist" >/dev/null 2>&1; then
  rouge "ITSAppUsesNonExemptEncryption est présente — elle doit être absente"
  echo "    Avec YES et sans code de conformité, l'envoi est refusé (90592)." >&2
  fautes=$((fautes + 1))
else
  vert "déclaration de chiffrement — clé absente, les questions se posent dans l'interface"
fi

dire "Ce que l'application ne doit pas contenir"
"$RACINE/tools/ios/verifier-l-autonomie.sh" "$APP" || fautes=$((fautes + 1))

if (( fautes > 0 )); then
  rouge "$fautes contrôle(s) en défaut — l'archive n'est pas prête à partir."
  exit 1
fi

(( ARRET_APRES_ARCHIVE )) && { dire "Archive prête : $ARCHIVE"; exit 0; }

# ── Export ────────────────────────────────────────────────────────────────────
#
# C'est ici que ça casse quand ça casse, et le message d'erreur d'Xcode le dit mal :
#
#   error: No profiles for 'ch.stackops.ghostcal' were found
#   error: Unable to log in with account '…'
#
# Les profils posés par la signature automatique lors d'une installation sur iPhone sont
# des profils de **développement**. L'export `app-store-connect` réclame des profils de
# **distribution**, qu'Xcode crée en se connectant au compte — et cette connexion échoue
# quand la session a expiré ou que l'authentification à deux facteurs attend une réponse.
# Le remède est de se reconnecter dans Xcode (Settings > Accounts), pas de changer ce
# script.
dire "Export en .ipa"
rm -rf "$SORTIE/export"
if ! xcodebuild -exportArchive \
  -archivePath "$ARCHIVE" \
  -exportOptionsPlist "$EXPORT_OPTIONS" \
  -exportPath "$SORTIE/export" \
  -allowProvisioningUpdates; then
  rouge "L'export a échoué."
  echo
  echo "Si le message parle de profils manquants ou de connexion au compte : ouvrez Xcode," >&2
  echo "Settings > Accounts, reconnectez-vous à l'équipe $EQUIPE, puis relancez. L'archive" >&2
  echo "est déjà construite, elle n'est pas à refaire :" >&2
  echo "    $ARCHIVE" >&2
  exit 1
fi

IPA="$(find "$SORTIE/export" -name '*.ipa' | head -1)"
[[ -n "$IPA" ]] || { rouge "Export terminé sans produire de .ipa"; exit 1; }

dire "Ce que prouve le .ipa"
TRAVAIL="$(mktemp -d)"
trap 'rm -rf "$TRAVAIL"' EXIT
unzip -q "$IPA" -d "$TRAVAIL"
APP_IPA="$(find "$TRAVAIL/Payload" -maxdepth 1 -name '*.app' | head -1)"

if [[ -z "$APP_IPA" ]]; then
  gris "contenu du .ipa — illisible : pas de Payload/*.app"
  fautes=$((fautes + 1))
else
  # `security cms -D` rend un plist sur la sortie standard, et `PlistBuddy` **ne sait pas
  # lire /dev/stdin** : il répond « Error Reading File: /dev/stdin » sur sa sortie
  # normale, avec un code de retour nul. Le contrôle affichait donc ce message d'erreur
  # comme s'il s'agissait du nom du profil, et concluait « ce n'est pas un profil de
  # distribution » — sur un IPA parfaitement signé. Sixième instrument à mentir.
  PROFIL_PLIST="$TRAVAIL/profil.plist"
  if security cms -D -i "$APP_IPA/embedded.mobileprovision" > "$PROFIL_PLIST" 2>/dev/null; then
    PROFIL="$(/usr/libexec/PlistBuddy -c 'Print :Name' "$PROFIL_PLIST" 2>/dev/null || true)"
  else
    PROFIL=""
  fi

  if [[ -z "$PROFIL" ]]; then
    gris "profil embarqué — illisible : le contrôle n'a pas pu regarder"
    fautes=$((fautes + 1))
  elif [[ "$PROFIL" == *Store* || "$PROFIL" == *Distribution* ]]; then
    vert "profil embarqué — « $PROFIL » (distribution)"
  else
    # Un profil de développement s'exporte, s'installe, et se fait refuser à l'envoi.
    rouge "profil embarqué — « $PROFIL » : ce n'est pas un profil de distribution"
    fautes=$((fautes + 1))
  fi

  # L'identité de signature de ce qui part réellement. Sur l'archive elle est
  # « Apple Development » et c'est normal ; ici, elle ne doit plus l'être.
  IDENTITE_IPA="$(codesign -dvv "$APP_IPA" 2>&1 | sed -n 's/^Authority=//p' | head -1)"
  if [[ -z "$IDENTITE_IPA" ]]; then
    gris "identité de signature du .ipa — illisible"
    fautes=$((fautes + 1))
  elif [[ "$IDENTITE_IPA" == *Distribution* ]]; then
    vert "identité de signature — $IDENTITE_IPA"
  else
    rouge "identité de signature — « $IDENTITE_IPA » : ce n'est pas une identité de diffusion"
    fautes=$((fautes + 1))
  fi

  # Deux états dans un vert n'en font pas deux : ce contrôle imprimait
  # « ✓ … — ABSENT » quand le fichier manquait. Un absent annoncé en vert se lit comme
  # un présent.
  if [[ -f "$APP_IPA/PrivacyInfo.xcprivacy" ]]; then
    vert "manifeste de confidentialité dans le .ipa — présent"
  else
    rouge "manifeste de confidentialité dans le .ipa — ABSENT"
    fautes=$((fautes + 1))
  fi
fi

if (( fautes > 0 )); then
  rouge "$fautes contrôle(s) en défaut sur le .ipa — ne l'envoyez pas en l'état."
  exit 1
fi

printf '\n\033[1m%s\033[0m\n' "IPA prêt : $IPA  ($(du -h "$IPA" | cut -f1))"

cat <<'FIN'

Ce script s'arrête ici. L'envoi est une décision, pas une étape.

Pour valider sans consommer de numéro de version — App Store Connect refuse deux fois le
même CURRENT_PROJECT_VERSION, et un envoi rejeté brûle le numéro :

    xcrun altool --validate-app -f <le .ipa> -t ios --apiKey <ID> --apiIssuer <ISSUER>

Pour envoyer :

    xcrun altool --upload-app -f <le .ipa> -t ios --apiKey <ID> --apiIssuer <ISSUER>

La clé API (.p8) se dépose dans ~/.appstoreconnect/private_keys/. Elle est préférable au
mot de passe d'application : elle ne partage aucun identifiant de compte et se révoque
seule.
FIN
