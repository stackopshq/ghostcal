# GhostCal

Fast, correct scheduling — an open alternative to Calendly / Cal.com. Dark-mode-native,
API-first, built for instant booking pages and bulletproof time handling.

## What

A scheduling backend (FastAPI) and booking frontend (Next.js, separate package) whose core is a
**pure, exhaustively-tested availability engine**: timezone- and DST-correct slot computation,
and database-guaranteed no-double-booking. Multi-tenant (organizations) from day one.

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the design and
**[docs/adr/](docs/adr/)** for decision records.

## Features

- **Event types**: solo, **round-robin** (least-loaded host from a pool), **collective** (all hosts
  attend), and **group** (many invitees per slot, capacity). Buffers, minimum notice, bookable
  window, per-day caps, and **custom booking questions** (text/select/checkbox/…).
- **Booking page**: timezone picker, custom questions, additional guests; readable slug URLs; an
  **embeddable widget** (`/embed/...`) with a copy-paste iframe snippet.
- **Invitee self-service**: cancel / reschedule via a signed link (no account).
- **Teams**: organizations, members & roles (owner/admin/member), token invitations.
- **Meeting polls**: propose times → invitees vote → host finalizes and everyone is emailed.
- **Notifications**: confirmation/cancellation emails with `.ics`; automated **reminders** (Celery).
- **Calendar sync**: bidirectional **CalDAV** (read busy + write bookings).
- **Integrations**: outbound **webhooks** (HMAC-signed) for booking/poll events.
- **Ops**: per-IP rate limiting, Redis availability cache, booking **analytics** dashboard,
  structured JSON logs with request ids. Multi-tenant **Postgres RLS** throughout.

## Stack

Python 3.14 · FastAPI · PostgreSQL (RLS, tstzrange + EXCLUDE) · SQLAlchemy 2.0 (async) · Alembic ·
Celery (Redis) · Next.js 16 (frontend). Tooling: `uv`, `ruff`, `mypy`, `pytest` + Hypothesis.

## Run (development)

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Podman, and PostgreSQL + Redis (via the
provided compose file).

```bash
uv sync                                  # create .venv and install all deps
cp .env.example .env                     # then edit secrets
podman-compose up -d postgres redis      # local infra
uv run uvicorn ghostcal.presentation.api:app --reload
# → http://127.0.0.1:8000/health  and  /docs
```

Run the Celery worker and the beat scheduler (background jobs incl. periodic CalDAV sync):

```bash
uv run celery -A ghostcal.celery_app:celery_app worker -l info
uv run celery -A ghostcal.celery_app:celery_app beat -l info
```

### Full stack in containers

The whole backend runs as separate Podman containers — Postgres, Redis, the API, the Celery
worker and the Celery beat scheduler (app and Celery are independent containers sharing one
image). Set the secrets in `.env` (see `.env.example`, including `GHOSTCAL_APP_DB_PASSWORD`),
then:

```bash
podman-compose up -d --build
# postgres provisions the non-privileged app role; the one-shot `migrate` service runs
# `alembic upgrade head`; then app (:8000), worker and beat start.
```

To send real emails, set `GHOSTCAL_RESEND_API_KEY` (otherwise emails are logged).

## Test

```bash
uv run ruff check .          # lint
uv run ruff format --check . # format
uv run mypy                  # types (strict)
uv run pytest                # tests + coverage
```

## Deploy

Container image is built with Podman (`Containerfile`). CI lints, type-checks, tests, scans
dependencies (`osv-scanner`) and secrets (`gitleaks`), and builds the image. Production targets
HA PostgreSQL + Redis; see the architecture doc, Phase 4.

## Architecture

Hexagonal (ports & adapters): `domain/` (pure logic, no I/O) → `application/` (use cases +
ports) ← `infrastructure/` (adapters) ; `presentation/` (FastAPI). The domain never reads the
clock — "now" is injected — so availability is deterministic and property-testable.

## License

[GNU AGPL-3.0-or-later](LICENSE). Network use is distribution: anyone interacting with a modified
GhostCal over a network must be offered the corresponding source.
