# GhostCal

Fast, correct scheduling — an open alternative to Calendly / Cal.com. Dark-mode-native,
API-first, built for instant booking pages and bulletproof time handling.

## What

A scheduling backend (FastAPI) and booking frontend (Next.js, separate package) whose core is a
**pure, exhaustively-tested availability engine**: timezone- and DST-correct slot computation,
and database-guaranteed no-double-booking. Multi-tenant (organizations) from day one.

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the design and
**[docs/adr/](docs/adr/)** for decision records.

## Stack

Python 3.14 · FastAPI · PostgreSQL · SQLAlchemy 2.0 (async) · Alembic · Celery (Redis) ·
Authlib · Next.js (frontend, later). Tooling: `uv`, `ruff`, `mypy`, `pytest` + Hypothesis.

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

Run the Celery worker (background jobs):

```bash
uv run celery -A ghostcal.celery_app:celery_app worker -l info
```

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

TBD — see open question at the end of setup.
