# Runbook — backup and restore

## Why this one is not like other backups

GhostCal's server stores ciphertext it cannot read. Event titles, task content and invitee answers
are sealed to keys that exist only in users' browsers, so there is no plaintext copy anywhere else
in the system and nothing to reconstruct from — not from logs, not from emails, not from a support
tool. **A lost database is permanent, total data loss for every organization on the instance.**

The same property means a backup is *safe to hold*: what is sealed in the database is sealed in the
dump. The dump still contains email addresses, and encrypted-at-rest CalDAV credentials and meeting
links, so treat it as sensitive — but a stolen dump does not reveal calendar contents.

One consequence worth stating plainly: **a backup does not protect a user who forgets their
password.** That loses their wrapped private key, which is a key-management problem
([ADR-0007](../adr/0007-org-key-rotation-and-revocation.md)), not a backup problem. Restoring an
older dump does not bring their data back into readable form.

## Taking a backup

```sh
scripts/backup.sh                        # -> backups/ghostcal-<utc-timestamp>.dump
BACKUP_DIR=/srv/backups scripts/backup.sh
```

Connection comes from `GHOSTCAL_DATABASE_ADMIN_URL` (falling back to `GHOSTCAL_DATABASE_URL`), read
from `.env` if present — the same variables the app uses. The output is `pg_dump` custom format:
compressed, and selectively restorable with `pg_restore`.

The script refuses to report success on a dump containing no table data. A backup nobody has read
is a hypothesis, and the cheapest moment to discover a truncated file is now rather than during a
restore, when it is the only copy left.

Scheduling is deliberately left to the host — cron, a systemd timer, your platform's job runner.
Whatever you use, **check that it still runs**. An unattended backup that stopped six weeks ago is
the classic way to have no backups at all.

Retention is also yours to set, but keep more than one: the failure mode a single nightly dump does
not cover is corruption that gets faithfully backed up before anyone notices.

## Restoring

```sh
scripts/restore.sh backups/ghostcal-20260720T101500Z.dump
```

The script refuses to run against a database that already has tables, because the realistic way to
lose data during a restore is to aim it at the wrong one. Pass `FORCE=1` when you mean to replace a
populated database.

After restoring it verifies, and **fails** if RLS policies did not come back. Row-Level Security is
the multi-tenancy boundary: an instance that restored the tables but not the policies looks healthy
and leaks across organizations on the first request.

Stop the app and worker before a production restore. `pg_restore` is not atomic here (see the note
in the script about `--single-transaction`), so a live app can write into a half-restored schema.

## Restore drills

A backup you have never restored is not a backup. Restore into a scratch database — no downtime, no
risk to the live one:

```sh
createdb drill
TARGET_URL=postgresql://user:pass@host/drill scripts/restore.sh backups/<file>.dump
```

Expect table count, RLS policy count and the Alembic head to be reported. Compare the head against
`alembic current` on the live database: a dump older than your last migration restores an older
schema, and the app will refuse to start against it until you run `alembic upgrade head`.

Verified on 2026-07-20 against a full schema: 35 tables, 29 RLS policies, head `f2a4cec11a6c`,
including both the refusal path and `FORCE=1`.

## What is not covered

- **Redis** is a cache and a Celery broker; it is not backed up and does not need to be. Losing it
  drops queued tasks and cached availability, not data.
- **Point-in-time recovery.** These scripts give you dumps at the moments you took them. If your
  tolerance for lost bookings is measured in minutes rather than hours, configure WAL archiving
  (`archive_mode`/`archive_command`) or use a managed Postgres that does — that is a Postgres
  deployment decision, deliberately not scripted here.
- **Off-site copies.** `backups/` on the same host survives a bad migration, not a dead disk.
