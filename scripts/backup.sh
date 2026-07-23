#!/usr/bin/env bash
# Back up the GhostCal database.
#
# Why this matters more here than elsewhere: the server stores ciphertext it cannot read. There is
# no plaintext copy of an event title, an invitee's answers or a task anywhere else in the system,
# so a lost database is not "restore from the last export" — it is unrecoverable, permanently, for
# every organization. This script is the only thing standing between a bad afternoon and that.
#
# Usage:
#   scripts/backup.sh                       # writes backups/ghostcal-<utc-timestamp>.dump
#   BACKUP_DIR=/srv/backups scripts/backup.sh
#
# Connection comes from GHOSTCAL_DATABASE_ADMIN_URL (falling back to GHOSTCAL_DATABASE_URL), the
# same variables the app uses, read from .env if present. Custom format (-Fc): compressed, and
# restorable selectively with pg_restore.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a && . ./.env && set +a
fi

url="${GHOSTCAL_DATABASE_ADMIN_URL:-${GHOSTCAL_DATABASE_URL:-}}"
if [[ -z "$url" ]]; then
  echo "error: set GHOSTCAL_DATABASE_ADMIN_URL or GHOSTCAL_DATABASE_URL" >&2
  exit 1
fi

# The app speaks SQLAlchemy's dialect URL; libpq does not understand '+asyncpg'.
url="${url/+asyncpg/}"

backup_dir="${BACKUP_DIR:-backups}"
mkdir -p "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$backup_dir/ghostcal-$stamp.dump"

echo "backing up to $out"
pg_dump --format=custom --no-owner --no-acl --file="$out" "$url"

# A backup nobody has read is a hypothesis. Listing the archive is cheap and catches a truncated or
# unreadable dump now, rather than during a restore when it is the only copy left.
tables="$(pg_restore --list "$out" | grep -c 'TABLE DATA' || true)"
if [[ "$tables" -eq 0 ]]; then
  echo "error: $out contains no table data — refusing to call this a backup" >&2
  exit 1
fi

echo "ok: $out ($(du -h "$out" | cut -f1), $tables tables with data)"
