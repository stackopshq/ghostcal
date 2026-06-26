# GhostCal — Architecture & Delivery Plan

> Status: **Draft for review** — no code written yet. This document is the contract we
> validate before scaffolding.

## 1. Goals & non-negotiables

GhostCal is a scheduling product (Calendly / Cal.com class). The product's value lives in
**one place**: a correct, fast availability engine. Everything else is plumbing.

Hard requirements that shape every decision below:

1. **Time correctness.** No timezone or DST bug is ever acceptable. All instants stored as
   `TIMESTAMPTZ` (UTC). Wall-clock availability rules are materialized per-day through an IANA
   timezone, handling DST gaps (spring-forward) and folds (fall-back).
2. **No double-booking, ever.** Guaranteed at the database level (exclusion constraint), not
   only by application-level locking.
3. **Booking page < 200 ms.** Availability is cacheable and cached; the public read path never
   touches a third-party API synchronously.
4. **External calendars can diverge.** Webhook-driven sync is best-effort; a periodic
   reconciliation job is the source of truth for "is this connection still correct".

## 2. Stack

| Layer            | Choice                                   | Rationale |
|------------------|------------------------------------------|-----------|
| API              | FastAPI (async)                          | Async-native for webhooks + concurrent calendar I/O; per ADR-0001 |
| DB               | PostgreSQL 16+                            | `TIMESTAMPTZ`, `tstzrange`, `EXCLUDE USING gist`, advisory locks |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic         | Mature, typed, async-capable |
| Schemas / config | Pydantic v2 + pydantic-settings          | Validated, fail-fast 12-factor config |
| Background jobs  | Celery (Redis broker)                    | Reminders, sync, token refresh. Sync workers: async calendar clients called via `async_to_sync` |
| Cache            | Redis                                    | Availability cache + Celery broker/result backend |
| Auth (app)       | Email/password + Google + Microsoft + generic OIDC SSO | We own the full auth stack; see §7 |
| Calendar OAuth   | Authlib                                  | Google + Microsoft OAuth2 token flows |
| Frontend         | Next.js (React) + TypeScript             | SSR for public booking pages (SEO + instant first paint) |
| Styling          | Tailwind + design tokens                 | Dark-mode-native design system (§8) |
| Email            | Resend (provider behind an interface)    | Swappable; abstract behind `EmailSender` port |
| Payments         | Stripe Checkout (Phase 3)                | PCI scope stays on Stripe |

Font note: **Inter** (OFL, no licensing friction). Geist Sans is Vercel-licensed — revisit only
if commercial terms are cleared.

## 3. Architecture style — hexagonal (ports & adapters)

The domain (availability math, booking rules) is **pure Python with zero I/O**, so it can be
exhaustively property-tested in milliseconds. I/O lives at the edges.

```
src/ghostcal/
  domain/            # PURE. No DB, no HTTP, no clock reads passed in as args.
    time/            #   TimeRange, Slot, value objects, interval math
    availability/    #   the slot-computation engine
    booking/         #   booking invariants, status transitions
  application/       # Use cases. Orchestrate domain + ports. No framework code.
    services/        #   GetAvailability, CreateBooking, SyncCalendar, ...
    ports/           #   Protocol interfaces: repositories, CalendarClient, EmailSender, Clock
  infrastructure/    # Adapters implementing the ports.
    db/              #   SQLAlchemy models, repositories, Alembic migrations
    calendars/       #   GoogleCalendarClient, MicrosoftCalendarClient
    email/           #   ResendEmailSender
    payments/        #   StripeClient
      cache/           #   RedisAvailabilityCache
  presentation/      # FastAPI: routers, request/response schemas, deps, auth
  config.py          # Pydantic Settings — validated, fail-fast at startup
  celery_app.py      # Celery app + task autodiscovery
```

Dependency rule: `presentation → application → domain`, and `infrastructure → application`
(adapters implement ports). The domain depends on nothing.

## 4. Data model (first cut)

All timestamps `TIMESTAMPTZ`. Times-of-day in availability rules are **local wall-clock** plus an
explicit IANA timezone on the owning schedule.

**Multi-tenant from day one.** A tenant is an **organization**. Every business object
(`event_types`, `availability_schedules`, `bookings`, `calendar_connections`, teams) carries an
`organization_id`. A user can belong to several organizations via `memberships`. A solo user is
just a one-member organization — no special case. All queries are organization-scoped at the
repository layer (enforced in code; Postgres RLS is a Phase 4 hardening option).

Tenancy & identity:

- **organizations** — `id, name, slug (unique), created_at`
- **memberships** — `id, organization_id, user_id, role (owner|admin|member), created_at`
  (unique on `(organization_id, user_id)`)
- **users** — `id, email (unique), name, avatar_url, timezone (IANA), email_verified_at,
  created_at`
- **user_credentials** — `user_id, password_hash (Argon2)` (only for email/password users)
- **identities** — `id, user_id, provider (google|microsoft|oidc), subject, issuer`
  (federated login; unique on `(provider, issuer, subject)`) — distinct from
  `calendar_connections`: login identity ≠ calendar access grant
- **email_verification_tokens / password_reset_tokens** — short-lived, single-use, hashed

Business objects (all carry `organization_id`):

- **calendar_connections** — `id, organization_id, user_id, provider (google|microsoft),
  access_token (enc),
  refresh_token (enc), scopes, sync_token/delta_link, channel_id, channel_expires_at, status`
  - tokens encrypted at rest (app-level envelope encryption, key from env/KMS)
- **event_types** — `id, organization_id, owner_id, slug (unique per org), title, description,
  duration_min,
  buffer_before_min, buffer_after_min, min_notice_min, slot_interval_min, date_window_days,
  max_per_day, location_type, price_cents, currency, active`
- **availability_schedules** — `id, organization_id, owner_id, name, timezone (IANA)`
- **availability_rules** — `id, schedule_id, weekday (0-6), start_time, end_time` (local times)
- **availability_overrides** — `id, schedule_id, date, is_available, start_time, end_time`
  (holidays / one-off changes)
- **bookings** — `id, organization_id, event_type_id, host_id, invitee_name, invitee_email,
  invitee_timezone,
  start_at, end_at, period tstzrange GENERATED, status (confirmed|cancelled|rescheduled),
  location, meeting_url, payment_intent_id, created_at`
- **external_busy** — `id, connection_id, external_event_id, period tstzrange, etag, synced_at`
  (read model: third-party busy blocks projected for fast subtraction)
- **workflows / reminders** (Phase 3) — `id, event_type_id, trigger (J-1|H-2|...), channel
  (email|sms), template`
- **teams, team_members, round_robin_state** (Phase 3)

### Double-booking guarantee

```sql
ALTER TABLE bookings ADD CONSTRAINT no_overlap_per_host
  EXCLUDE USING gist (host_id WITH =, period WITH &&)
  WHERE (status = 'confirmed');
```

This is the real integrity guarantee. The booking transaction additionally takes a Postgres
**advisory lock** keyed on `(host_id, slot_start)` to serialize the read-availability →
insert path cleanly and return a friendly "slot just taken" instead of a constraint violation.

## 5. The availability engine (the hard part)

Pure function, no I/O. Inputs are plain data; the application layer fetches them and passes them in.

```
compute_slots(
  rules,              # weekly recurring ranges (local time + schedule tz)
  overrides,          # date-specific availability
  busy,               # list[tstzrange]: confirmed bookings + external_busy + buffers
  event_type,         # duration, buffers, min_notice, slot_interval, window, max_per_day
  now,                # injected Clock value (UTC) — never read inside domain
  window,             # [from_date, to_date] requested
  invitee_tz,         # for final presentation only
) -> list[Slot]
```

Algorithm:

1. **Materialize** each candidate day's rules into concrete UTC `tstzrange`s: combine `date +
   local_time` in the **schedule's IANA tz**, then convert to UTC. Per-day conversion is
   mandatory — the UTC offset changes across DST boundaries.
   - Spring-forward gap: a local time that does not exist → drop/clamp that sliver.
   - Fall-back fold: a local time that occurs twice → use `fold` semantics deterministically.
2. **Apply overrides** (replace/cancel a day's ranges).
3. **Subtract** all `busy` intervals (already inflated by buffers) via interval difference.
4. **Slice** remaining free intervals into `duration`-long slots stepping by `slot_interval`.
5. **Filter**: `start >= now + min_notice`, within `date_window_days`, respect `max_per_day`.
6. **Present** slots converted to `invitee_tz`.

Buffers are applied by **inflating busy blocks** (not by shrinking free time) so back-to-back
bookings respect gaps symmetrically.

### Testing strategy (built from day one)

- **Property-based** (Hypothesis): generated rules/busy across random IANA zones; invariants —
  no slot overlaps busy, every slot inside a rule, slots are duration-aligned, idempotent.
- **Golden DST cases**: `America/New_York` spring-forward & fall-back days, `Pacific/Chatham`
  (+12:45), `Australia/Lord_Howe` (30-min DST), slot straddling local midnight, invitee in a
  different hemisphere.
- Time is injected via a `Clock` port → tests are deterministic, no `freezegun` hacks in domain.

## 6. Calendar sync

- **Connect**: Authlib OAuth2 → store encrypted tokens + granted scopes (least privilege:
  read busy/free + write events for the chosen calendar only).
- **Push notifications**: Google `watch` channels / Microsoft Graph subscriptions → webhook
  endpoint marks the connection dirty and enqueues an ARQ delta-sync job.
- **Delta sync**: pull changes via `syncToken` / `deltaLink`, project into `external_busy`.
- **Reconciliation**: periodic ARQ cron re-syncs every connection and refreshes/rotates tokens
  and webhook channels before expiry. Webhooks are an optimization; this job is correctness.
- **Resilience**: revoked token → mark connection `needs_reauth`, surface in dashboard, never
  silently serve stale availability.

## 7. Auth & security

- **App auth — four methods at launch**: email/password (Argon2, email verification required),
  Google, Microsoft, and generic **OIDC SSO** (discovery URL + client creds per organization, for
  enterprise IdPs). All converge on the same `users` row via the `identities` table; a server-
  issued short-lived JWT access + rotating refresh in httpOnly cookies is the unified session.
  **Login identity is separate from calendar access** — signing in with Google does not grant
  calendar scopes; connecting a calendar is an explicit, separately-scoped consent.
- **Secrets**: all via env (pydantic-settings, fail-fast). Tokens encrypted at rest. No secret
  in the repo; `.env.example` only.
- **Input validation** at the boundary (Pydantic). Public booking endpoints rate-limited.
- **Webhooks**: verify signatures / channel tokens; treat payloads as untrusted (only a trigger
  to pull authoritative state).
- **Payments**: Stripe Checkout/Elements — card data never touches our servers.

## 8. Frontend (Next.js)

- **Public booking page**: server-rendered (SEO + instant paint), split layout — host panel left,
  neon-grid calendar right. Availability fetched from the cached read API.
- **Dashboard**: event-type cards, one-click copy link, schedule editor.
- **Design system**: dark-mode-native tokens — bg `#0B0F19`, accent `#00F0FF`, card `#1E293B`,
  muted `#94A3B8`; discreet glassmorphism (`rgba(255,255,255,0.05)` borders); Inter; subtle
  gradient only on primary CTAs.

## 9. Delivery plan (maps to the product roadmap)

**Phase 1 — Core engine (de-risk first).** DB schema + Alembic; availability engine with full
property + DST test suite; public booking read API; booking write path with exclusion constraint
+ advisory lock; minimal Next.js booking page + design tokens.

**Phase 2 — Sync & integrations.** Google + Microsoft OAuth/connect; webhook + delta sync +
reconciliation job; confirmation emails; auto meeting links (Meet/Teams/Zoom).

**Phase 3 — Differentiators.** Workflows (J-1 / H-2 reminders, email+SMS); team round-robin;
Stripe payments at booking time.

**Phase 4 — Hardening & launch.** OIDC hardening + scope review; availability cache + perf
budget (<200 ms); Podman containers, CI/CD, HA Postgres, observability (structured logs, traced
errors).

## 10. Resolved decisions

1. **Background jobs: Celery** (Redis broker/result backend). Sync workers; async calendar
   clients invoked via `async_to_sync`.
2. **App login at launch: four methods** — email/password, Google, Microsoft, generic OIDC SSO.
3. **SMS: deferred.** Phase 3 reminders ship email-only first; SMS provider chosen later.
4. **Multi-tenant from day one.** Organizations + memberships; every business object is
   organization-scoped. A solo user is a one-member organization.

Still open:

- Postgres **Row-Level Security** for tenant isolation — deferred to Phase 4 (code-level scoping
  first). Flag if you want RLS from the start.
