#!/usr/bin/env bash
# Restore a GhostCal database from a dump produced by scripts/backup.sh.
#
# Refuses to run against a non-empty database unless FORCE=1, because the realistic way to lose
# data during a restore is to aim it at the wrong one.
#
# Usage:
#   scripts/restore.sh backups/ghostcal-20260720T101500Z.dump
#   TARGET_URL=postgresql://... scripts/restore.sh <dump>     # restore elsewhere (drill)
#   FORCE=1 scripts/restore.sh <dump>                         # overwrite a populated database
set -euo pipefail

cd "$(dirname "$0")/.."

dump="${1:-}"
if [[ -z "$dump" || ! -f "$dump" ]]; then
  echo "usage: scripts/restore.sh <dump-file>" >&2
  exit 1
fi

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a && . ./.env && set +a
fi

url="${TARGET_URL:-${GHOSTCAL_DATABASE_ADMIN_URL:-${GHOSTCAL_DATABASE_URL:-}}}"
if [[ -z "$url" ]]; then
  echo "error: set TARGET_URL or GHOSTCAL_DATABASE_ADMIN_URL" >&2
  exit 1
fi
url="${url/+asyncpg/}"

existing="$(psql "$url" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
if [[ "$existing" -gt 0 && "${FORCE:-0}" != "1" ]]; then
  echo "refusing: target already has $existing tables in public. Re-run with FORCE=1 to overwrite." >&2
  exit 1
fi

echo "restoring $dump"
# --clean --if-exists so a FORCE=1 restore replaces objects instead of erroring on every one.
# Not --single-transaction: the dump replays RLS policies and SECURITY DEFINER functions, and one
# benign "already exists" should not roll back an entire restore.
pg_restore --dbname="$url" --no-owner --no-acl --clean --if-exists "$dump"

echo "--- verifying ---"
psql "$url" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" \
  | xargs -I{} echo "tables: {}"
# RLS is the multi-tenancy boundary. A restore that silently dropped the policies would look
# healthy and leak across organizations on the first request, so fail here instead.
policies="$(psql "$url" -tAc "SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")"
echo "RLS policies: $policies"
if [[ "$policies" -eq 0 ]]; then
  echo "error: no RLS policies after restore — tenant isolation is gone, do not serve this" >&2
  exit 1
fi
echo "alembic head: $(psql "$url" -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null || echo '(none)')"
echo "ok"
