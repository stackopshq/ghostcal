# ADR-0001: Stack and architecture

- Status: Proposed
- Date: 2026-06-26

## Context

GhostCal is a scheduling product competing with Calendly / Cal.com. The dominant technical risk
is time correctness (timezones, DST) and booking concurrency, not UI. The product must serve
public booking pages fast (<200 ms) and integrate with Google / Microsoft calendars.

## Decision

- **Backend: FastAPI (async).** Async-native suits concurrent third-party calendar I/O and
  webhook handling. Trade-off accepted: more wiring than Django (ORM, auth, migrations chosen
  explicitly) in exchange for a lean, async, API-first core.
- **Database: PostgreSQL.** Required features: `TIMESTAMPTZ`, `tstzrange`,
  `EXCLUDE USING gist` (the real no-double-booking guarantee), advisory locks.
- **ORM/migrations: SQLAlchemy 2.0 (async) + Alembic.**
- **Architecture: hexagonal (ports & adapters).** The domain (availability engine, booking
  rules) is pure, I/O-free Python so it can be exhaustively property-tested. Adapters
  (DB, calendars, email, payments) implement application-layer ports.
- **Frontend: Next.js (React + TypeScript).** SSR for public booking pages (SEO + instant first
  paint).
- **Background jobs: Celery (Redis broker).** Mature ecosystem (scheduling, retries, routing).
  Trade-off: Celery workers are synchronous, so async calendar clients are called via
  `async_to_sync` inside tasks.
- **Multi-tenant from day one.** Organizations + memberships; every business object carries
  `organization_id`. A solo user is a one-member organization. Tenant scoping enforced in the
  repository layer (Postgres RLS deferred to Phase 4).
- **Auth owned in-house, four methods at launch:** email/password (Argon2), Google, Microsoft,
  generic OIDC SSO — all converging on one `users` row via an `identities` table. Login identity
  is kept separate from calendar OAuth grants.

## Consequences

- We own auth, migrations, and admin tooling rather than getting them for free (Django). Owning
  auth is also a deliberate choice: four login methods + per-org SSO need full control.
- The pure-domain boundary forces a `Clock` port (no clock reads inside the domain), enabling
  deterministic time tests.
- Postgres exclusion constraints make double-booking a database invariant, independent of
  application code paths.
- Organization-scoping every query is a standing discipline; a missing `organization_id` filter
  is a tenant-isolation bug. Repository base classes enforce it.
