#!/usr/bin/env bash
# Monte un GhostCal jetable et l'amorce, pour éprouver les clients mobiles contre de
# vraies données. Laisse tout allumé et rend la main.
#
#   ./tools/banc-local.sh              # jeu d'épreuve
#   ./tools/banc-local.sh --vitrine    # jeu de vitrine, pour les captures App Store
#
# Les deux jeux ne servent pas la même chose, et les confondre s'est vu en image. Le jeu
# d'épreuve dépose exprès un événement illisible, pour vérifier qu'il s'affiche au lieu de
# disparaître ; en devanture, la même ligne rouge se lit comme un bogue. Voir l'en-tête de
# `tools/amorcer_vitrine.py`.
#
# ─── Pourquoi ce banc existe ───
#
# Le portage Flutter a cinq écrans et cinquante tests, et **aucun n'a jamais lu une donnée
# venue d'un serveur**. Des tests verts sur des requêtes simulées prouvent que le client
# est cohérent avec l'idée qu'on se fait du serveur ; ils ne prouvent rien sur le serveur.
#
# ─── Ce qu'il n'est pas ───
#
# Ce n'est pas la production : pas de Redis, donc pas de Celery, donc **ni rappels ni
# synchronisation d'agendas externes**. C'est délibéré — ces tâches de fond n'ont aucun
# effet sur ce que les écrans affichent.
#
# La grappe PostgreSQL vit dans le scratchpad, sur le port 55432, **sans socket Unix** : le
# chemin du scratchpad dépasse les 103 octets qu'accepte une socket de domaine Unix, et
# rien ne doit toucher un PostgreSQL que la machine hébergerait par ailleurs.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VITRINE=0
[[ "${1:-}" == "--vitrine" ]] && VITRINE=1

TRAVAIL="${GHOSTCAL_BANC:-${TMPDIR:-/tmp}/ghostcal-banc}"
PGDATA="$TRAVAIL/pgdata"
PGPORT=55432
APIPORT=8099
API="http://127.0.0.1:$APIPORT"

# `example.com` et non `.test` : le validateur d'adresses du serveur refuse les domaines
# réservés à usage spécial, dont `.test` fait partie. L'inscription échouait avec une
# erreur de validation sur le champ e-mail, que rien dans le script ne relayait.
EMAIL="clara@example.com"
# Pas « correct horse battery staple » : le serveur vérifie les mots de passe contre les
# fuites publiques et le refuse, à juste titre — il est dans toutes les listes.
MOTDEPASSE="banc-local-ghostcal-jetable-2026"
RECUPERATION="banc local phrase de recuperation jetable"

export PATH="/opt/homebrew/opt/postgresql@17/bin:$HOME/.cargo/bin:$PATH"

dire() { printf "\n\033[1m▸ %s\033[0m\n" "$*" >&2; }
jq_() { python3 -c "import json,sys;d=json.load(sys.stdin);print(d$1)"; }

for outil in initdb pg_ctl psql uv cargo curl; do
  command -v "$outil" >/dev/null || { echo "$outil introuvable" >&2; exit 1; }
done

dire "PostgreSQL jetable (port $PGPORT)"
mkdir -p "$TRAVAIL"
# On regarde le **port**, pas seulement notre propre dossier : une grappe montée à la
# main occuperait 55432 sans que `pg_ctl status` sur ce dossier-ci en sache rien, et
# `initdb` échouerait avec un message qui ne nomme pas la cause.
if ! psql -h 127.0.0.1 -p $PGPORT -U ghostcal -d postgres -tAc "select 1" >/dev/null 2>&1; then
  rm -rf "$PGDATA"
  initdb -D "$PGDATA" -U ghostcal --auth=trust >/dev/null
  pg_ctl -D "$PGDATA" -o "-p $PGPORT -c unix_socket_directories=" -l "$PGDATA/serveur.log" start >/dev/null
  for _ in $(seq 1 30); do
    psql -h 127.0.0.1 -p $PGPORT -U ghostcal -d postgres -tAc "select 1" >/dev/null 2>&1 && break
    sleep 1
  done
  psql -h 127.0.0.1 -p $PGPORT -U ghostcal -d postgres -c "create database ghostcal;" >/dev/null
fi

dire "Migrations"
export GHOSTCAL_ENVIRONMENT=development
export GHOSTCAL_DATABASE_URL="postgresql+asyncpg://ghostcal@127.0.0.1:$PGPORT/ghostcal"
export GHOSTCAL_REDIS_URL="redis://localhost:6379/0"
export GHOSTCAL_SECRET_KEY="banc-local-jetable-secret-de-plus-de-32-caracteres"
export GHOSTCAL_TOKEN_ENCRYPTION_KEY="banc-local-jetable-cle-de-plus-de-32-caracteres"
export GHOSTCAL_FRONTEND_BASE_URL="http://127.0.0.1:3001"
export GHOSTCAL_EMAIL_FROM="GhostCal <banc@ghostcal.test>"
cd "$RACINE"
uv sync --quiet
# `greenlet` manque à la résolution sur Python 3.14 alors que SQLAlchemy asynchrone
# l'exige : sans lui, la première requête échoue avec un message qui ne nomme pas la cause.
uv pip install --quiet greenlet
uv run alembic upgrade head >/dev/null

dire "API (port $APIPORT)"
if ! curl -sf --max-time 2 "$API/health" >/dev/null 2>&1; then
  uv run uvicorn ghostcal.presentation.api:app --host 127.0.0.1 --port $APIPORT \
    > "$TRAVAIL/api.log" 2>&1 &
  for _ in $(seq 1 40); do
    curl -sf --max-time 2 "$API/health" >/dev/null 2>&1 && break
    sleep 1
  done
fi
curl -sf --max-time 2 "$API/health" >/dev/null || { echo "L'API n'a pas démarré ; voir $TRAVAIL/api.log" >&2; exit 1; }

dire "Clés de chiffrement — fabriquées par le cœur Rust"
cargo build --quiet --manifest-path apps/mobile/rust/Cargo.toml --bin amorcer
AMORCER="apps/mobile/rust/target/debug/amorcer"
MATERIEL="$("$AMORCER" cles "$MOTDEPASSE" "$RECUPERATION")"

dire "Compte"
# Les clés voyagent **avec** l'inscription : le serveur n'accepte pas un compte sans
# matériel de chiffrement, ce qui est cohérent avec le produit — un compte sans clé
# n'aurait rien à ouvrir. Ce n'est écrit nulle part, et l'erreur de validation ne dit que
# « champ requis ».
curl -s -X POST "$API/v1/auth/register" -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$MOTDEPASSE\",\"name\":\"Clara\",\"zk_keys\":$MATERIEL}" \
  >/dev/null || true
# L'inscription exige une vérification par courriel, et il n'y a pas de boîte aux lettres
# ici. On marque l'adresse vérifiée en base : c'est un banc, l'identité n'y est pas l'objet.
psql -h 127.0.0.1 -p $PGPORT -U ghostcal -d ghostcal -c \
  "update users set email_verified_at = now() where email = '$EMAIL';" >/dev/null

JETONS="$(curl -s -X POST "$API/v1/auth/login" -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$MOTDEPASSE\"}")"
ACCES="$(printf '%s' "$JETONS" | jq_ "['access_token']")"
[[ -n "$ACCES" ]] || { echo "Connexion impossible : $JETONS" >&2; exit 1; }
AUTH=(-H "authorization: Bearer $ACCES")

PUBLIQUE="$(curl -s "${AUTH[@]}" "$API/v1/auth/zk-keys" | jq_ "[0]['public_key']")"
ORG="$(curl -s "${AUTH[@]}" "$API/v1/me/organizations" | jq_ "[0]['id']")"
ORGH=(-H "x-organization-id: $ORG")
CAL="$(curl -s "${AUTH[@]}" "${ORGH[@]}" "$API/v1/me/calendars" | jq_ "[0]['id']")"

sceller() { "$AMORCER" sceller "$PUBLIQUE" "$1"; }
horodate() { python3 -c "
import datetime as d
print((d.datetime.now(d.timezone.utc) + d.timedelta(hours=$1)).strftime('%Y-%m-%dT%H:%M:%S+00:00'))"; }

dire "Données"
if (( VITRINE )); then
  # Le slug de l'organisation : la réservation passe par la route publique
  # `/v1/orgs/{slug}/…`, comme un invité le ferait. Le prendre ici plutôt que de le
  # deviner — il est tiré du nom du compte et porte un suffixe aléatoire.
  SLUG="$(curl -s "${AUTH[@]}" "$API/v1/me/organizations" | jq_ "[0]['slug']")"
  [[ -n "$SLUG" ]] || { echo "Slug d'organisation introuvable" >&2; exit 1; }
  python3 "$RACINE/tools/amorcer_vitrine.py" "$API" "$ACCES" "$ORG" "$PUBLIQUE" "$CAL" "$AMORCER" "$SLUG"
else
  python3 "$RACINE/tools/amorcer_donnees.py" "$API" "$ACCES" "$ORG" "$PUBLIQUE" "$CAL" "$AMORCER"
fi

printf '\n\033[1mTout est prêt.\033[0m\n' >&2
cat >&2 <<FIN

  Dans l'application, saisir :

    serveur         127.0.0.1:$APIPORT
    adresse         $EMAIL
    mot de passe    $MOTDEPASSE

  Le simulateur atteint 127.0.0.1 directement ; un appareil réel, non — il lui faudrait
  l'adresse de ce Mac sur le réseau, et le serveur écoute en clair, ce que l'application
  refuse hors boucle locale.

  Ce qu'on regarde, JEU D'ÉPREUVE (sans --vitrine) :

    Agenda    trois événements, dont un scellé sous une autre clé. Il doit s'AFFICHER
              comme illisible, pas disparaître — une ligne absente se lit « libre ».
    Tâches    une en retard, une à venir, une sans échéance, et l'ordre qui va avec.
    RDV       un type actif, dont le lien public se copie.
    Réunions  vide tant que personne n'a réservé depuis la page publique.
    Réglages  profil, disponibilités, équipe.

  Ce qu'on regarde, JEU DE VITRINE (--vitrine) :

    Agenda    cinq entrées sur la journée, trois sur les suivantes. AUCUNE illisible :
              en devanture, la ligne rouge se lit comme un bogue.
    Tâches    cinq, dont une en retard — un état normal, pas une panne.
    RDV       deux liens actifs, un inactif.
    Réunions  une réservation réellement prise depuis la page publique, avec son nom
              et ses réponses scellés à l'organisation.
    Réglages  profil, horaire « Heures de bureau », équipe.

  Pour tout couper :

    pg_ctl -D "$PGDATA" stop ; pkill -f "uvicorn ghostcal"

FIN
