# ADR-0001: Stack and architecture

- Status: Proposed
- Date: 2026-06-26
- Superseded in part on 2026-08-31: the licence decision recorded below (AGPL-3.0-or-later)
  no longer holds. GhostCal is MIT, aligned with the rest of the Ghost suite. See
  [ADR-0013](0013-relicense-to-mit.md). Everything else in this record still stands, and the
  original wording is kept intact so the change of mind stays visible.

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
  `organization_id`. A solo user is a one-member organization. Tenant isolation enforced by
  **Postgres RLS from the start** (per-request `SET LOCAL app.current_org_id`; app role is
  non-`BYPASSRLS`), with repository-layer scoping as defence in depth.
- **License: GNU AGPL-3.0-or-later.** Network use counts as distribution, so SaaS modifications
  must offer their source — matching the open-alternative positioning (as Cal.com does).
  *(Superseded 2026-08-31 by ADR-0013: MIT.)*
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
- Organization-scoping every query is a standing discipline, but RLS is the backstop: a missing
  `organization_id` filter degrades to a wrong-result bug, not a cross-tenant data leak.
- Every request and background task must bind `app.current_org_id` before touching the DB;
  schema migrations and the session/transaction layer own this from Phase 1.
- AGPL obliges us (and any operator of a modified GhostCal) to offer source on network use;
  third-party dependencies must stay license-compatible (no proprietary/Apache-incompatible-only).
  *(Superseded 2026-08-31 by ADR-0013. Under MIT there is no source-disclosure obligation;
  the dependency-compatibility duty remains, now against strong copyleft.)*
