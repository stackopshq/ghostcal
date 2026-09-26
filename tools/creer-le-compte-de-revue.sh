#!/usr/bin/env bash
# Crée — et amorce — le compte de démonstration que l'examinateur d'Apple utilisera.
#
#   GHOSTCAL_PHRASE='…' ./tools/creer-le-compte-de-revue.sh <adresse> [serveur]
#
# Exemple :
#   GHOSTCAL_PHRASE="$(openssl rand -base64 24)" \
#     ./tools/creer-le-compte-de-revue.sh appstore-review@stackops.ch
#
# ─── Le secret ne touche pas le dépôt ───
#
# La phrase se passe par l'environnement, jamais en argument ni dans un fichier. Un secret
# en clair dans un dépôt reste dans son historique même retiré, et le balayage de secrets
# le refuserait à juste titre. Elle ne s'imprime pas non plus : c'est vous qui l'avez
# tapée, vous l'avez déjà.
#
# Après publication, **changez-la**. Elle aura transité par App Store Connect, dont ce
# n'est pas le métier de garder des secrets.
#
# ─── L'étape qu'aucun script ne peut franchir ───
#
# Le serveur exige une adresse vérifiée : `POST /v1/auth/login` répond
# `403 email not verified` tant que le lien reçu par courriel n'a pas été suivi. Le banc
# local contourne cela en écrivant directement dans PostgreSQL — ici, il n'y a pas de base
# sous la main, et il ne devrait pas y en avoir.
#
# Ce script s'arrête donc et **attend**, en réessayant la connexion. Ouvrez le courriel,
# suivez le lien, et il repart tout seul. C'est la seule étape manuelle, et elle est là par
# construction : un compte qu'un script pourrait vérifier seul ne prouverait rien de
# l'adresse.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADRESSE="${1:-}"
API="${2:-https://cal.ghostsuite.cloud}"
PHRASE="${GHOSTCAL_PHRASE:-}"

dire() { printf "\n\033[1m▸ %s\033[0m\n" "$*" >&2; }
vert() { printf "\033[32m✓ %s\033[0m\n" "$*"; }
rouge() { printf "\033[31m✗ %s\033[0m\n" "$*"; }
gris() { printf "\033[33m· %s\033[0m\n" "$*"; }

if [[ -z "$ADRESSE" ]]; then
  rouge "Adresse manquante."
  echo "  Passez une adresse dont vous savez lire la boîte : le lien de vérification y" >&2
  echo "  part, et sans lui le compte ne se connecte pas. L'adresse est par ailleurs" >&2
  echo "  **immobilisée** dès l'inscription — une seconde tentative rend 409." >&2
  exit 2
fi
if [[ -z "$PHRASE" ]]; then
  rouge "GHOSTCAL_PHRASE manquante."
  echo "  Douze caractères au moins, et le serveur refuse les mots de passe connus des" >&2
  echo "  fuites publiques. Par exemple :  GHOSTCAL_PHRASE=\"\$(openssl rand -base64 24)\"" >&2
  exit 2
fi

jq_() { python3 -c "import json,sys;d=json.load(sys.stdin);print(d$1)" 2>/dev/null || true; }

# ── Le serveur répond-il, et est-ce bien GhostCal ? ───────────────────────────
dire "Serveur"
# ─── `/api`, et pourquoi ce n'est pas un détail ───
#
# Le serveur de production sert le CLIENT à la racine et l'API sous `/api`. Un appel à
# `$API/v1/me/organizations` ne rend donc pas une erreur : il rend **la page HTML du
# client**, avec un code 200. `jq` n'y trouve rien, la variable reste vide, et le script
# annonce « le compte n'est pas exploitable » — en accusant le compte, qui va très bien.
#
# Deux chemins échappaient à la règle et masquaient le défaut : `/v1/auth/register` et
# `/v1/auth/login` fonctionnent nus, relayés par le client pour son propre usage. Le début
# du parcours passait donc, et seule l'étape des données trébuchait.
#
# Constaté le 2026-09-25 sur `cal.ghostsuite.cloud`. La spécification servie à
# `/api/openapi.json` fait foi : elle liste bien `/v1/me/organizations`.
# Le préfixe se DÉCOUVRE, il ne se suppose pas : c'est un fait de déploiement, pas une
# propriété de l'application. En production, un proxy monte l'API sous `/api` et sert le
# client à la racine. Le banc local, lui, expose uvicorn directement — `/health` répond,
# `/api/health` rend 404. Coder `/api` en dur réparerait la production et casserait le banc.
BASE=""
for CANDIDAT in "$API" "$API/api"; do
  if [[ "$(curl -s --max-time 10 "$CANDIDAT/health" || true)" == *'"status":"ok"'* ]]; then
    BASE="$CANDIDAT"
    break
  fi
done
if [[ -z "$BASE" ]]; then
  rouge "Pas de GhostCal en bonne santé sur $API ni sur $API/api"
  echo "  Ni /health ni /api/health ne rendent « ok ». Le serveur est-il lancé ?" >&2
  exit 1
fi
[[ "$BASE" == "$API" ]] || gris "API trouvée sous /api"

SANTE="$(curl -s --max-time 10 "$BASE/health" || true)"
if [[ "$SANTE" != *'"status":"ok"'* ]]; then
  rouge "Pas de GhostCal en bonne santé sur $API — obtenu : ${SANTE:0:120}"
  exit 1
fi
vert "$API répond « ok »"

# ── Le matériel de clés, fabriqué par le cœur Rust ────────────────────────────
#
# Jamais réimplémenté ici. Un compte dont l'enveloppe Argon2id serait fabriquée en shell
# prouverait la cohérence du script avec lui-même, et rien sur le produit : c'est le même
# cœur que l'application qui doit produire ces octets.
dire "Clés"
AMORCER="$RACINE/apps/mobile/rust/target/debug/amorcer"
if [[ ! -x "$AMORCER" ]]; then
  cargo build --quiet --manifest-path "$RACINE/apps/mobile/rust/Cargo.toml" --bin amorcer
fi
[[ -x "$AMORCER" ]] || { rouge "Binaire « amorcer » introuvable : $AMORCER"; exit 1; }
# La phrase de récupération est dérivée de la phrase principale plutôt que tirée au sort :
# ce compte est jetable et personne n'aura à s'en servir. En tirer une seconde au hasard
# obligerait à la transmettre aussi, pour rien.
RECUPERATION="recuperation-$PHRASE"
MATERIEL="$("$AMORCER" cles "$PHRASE" "$RECUPERATION")"
vert "matériel X25519 + enveloppe Argon2id produits par le cœur"

# ── Inscription ───────────────────────────────────────────────────────────────
dire "Inscription de $ADRESSE"
CORPS="$(ADRESSE="$ADRESSE" PHRASE="$PHRASE" MATERIEL="$MATERIEL" python3 -c '
import json, os
print(json.dumps({
    "email": os.environ["ADRESSE"],
    "name": "App Review",
    "password": os.environ["PHRASE"],
    "zk_keys": json.loads(os.environ["MATERIEL"]),
}))')"
REPONSE="$(curl -s -w '\n%{http_code}' --max-time 20 -X POST "$BASE/v1/auth/register" \
  -H 'content-type: application/json' -d "$CORPS")"
CODE="$(printf '%s' "$REPONSE" | tail -1)"
CORPS_REPONSE="$(printf '%s' "$REPONSE" | sed '$d')"

case "$CODE" in
  201) vert "compte créé" ;;
  409) gris "l'adresse est déjà inscrite — on poursuit avec la phrase fournie" ;;
  *)   rouge "inscription refusée ($CODE) : ${CORPS_REPONSE:0:250}"; exit 1 ;;
esac

# ── L'attente ─────────────────────────────────────────────────────────────────
dire "Vérification de l'adresse"
echo "  Ouvrez le courriel envoyé à $ADRESSE et suivez le lien." >&2
echo "  Ce script réessaie la connexion toutes les cinq secondes." >&2
ACCES=""
for _ in $(seq 1 120); do   # dix minutes
  SORTIE="$(curl -s -w '\n%{http_code}' --max-time 15 -X POST "$BASE/v1/auth/login" \
    -H 'content-type: application/json' \
    -d "$(ADRESSE="$ADRESSE" PHRASE="$PHRASE" python3 -c '
import json, os
print(json.dumps({"email": os.environ["ADRESSE"], "password": os.environ["PHRASE"]}))')" || true)"
  C="$(printf '%s' "$SORTIE" | tail -1)"
  B="$(printf '%s' "$SORTIE" | sed '$d')"
  case "$C" in
    200) ACCES="$(printf '%s' "$B" | jq_ "['access_token']")"; break ;;
    403) printf '.' >&2 ;;
    401)
      # Ni « pas vérifiée » ni « en attente » : la phrase ne correspond pas. Réessayer
      # dix minutes n'y changerait rien, et attendre en silence ferait croire à une
      # lenteur du courriel.
      rouge ""
      rouge "401 : la phrase ne correspond pas au compte. Si l'adresse était déjà"
      rouge "inscrite (409 plus haut), c'est son ancienne phrase qu'il faut fournir."
      exit 1 ;;
    *) printf '?' >&2 ;;
  esac
  sleep 5
done

if [[ -z "$ACCES" ]]; then
  rouge ""
  rouge "Toujours pas vérifiée au bout de dix minutes."
  echo "  Le compte **existe** : reprenez ce script avec la même adresse et la même" >&2
  echo "  phrase quand le lien aura été suivi. Il repartira du 409 et poursuivra." >&2
  exit 1
fi
echo >&2
vert "connexion réelle établie — l'adresse est vérifiée"

# ── Amorçage de vitrine ───────────────────────────────────────────────────────
#
# Le même jeu que celui des captures : un seul jeu de données à tenir, et il est crédible
# par construction puisque c'est celui qu'on photographie.
dire "Données de vitrine"
AUTH=(-H "authorization: Bearer $ACCES")
PUBLIQUE="$(curl -s "${AUTH[@]}" "$BASE/v1/auth/zk-keys" | jq_ "[0]['public_key']")"
ORG="$(curl -s "${AUTH[@]}" "$BASE/v1/me/organizations" | jq_ "[0]['id']")"
SLUG="$(curl -s "${AUTH[@]}" "$BASE/v1/me/organizations" | jq_ "[0]['slug']")"
CAL="$(curl -s "${AUTH[@]}" -H "x-organization-id: $ORG" "$BASE/v1/me/calendars" | jq_ "[0]['id']")"
for nom in PUBLIQUE ORG SLUG CAL; do
  [[ -n "${!nom}" ]] || { rouge "$nom introuvable — le compte n'est pas exploitable"; exit 1; }
done

python3 "$RACINE/tools/amorcer_vitrine.py" "$BASE" "$ACCES" "$ORG" "$PUBLIQUE" "$CAL" "$AMORCER" "$SLUG"

dire "Prêt"
cat >&2 <<FIN

  À coller dans App Store Connect, section « Informations pour l'examen » :

    Serveur     $API
    Adresse     $ADRESSE
    Phrase      celle que vous avez passée dans GHOSTCAL_PHRASE

  Ce script ne l'imprime pas, et le dépôt ne la contient pas.

  Après publication : changez la phrase, ou supprimez le compte. Elle aura transité par
  App Store Connect.
FIN
