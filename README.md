<p align="center">
  <img src="frontend/public/logo.png" alt="GhostCal" width="90">
</p>

<h1 align="center">GhostCal</h1>

<p align="center">
  A <strong>privacy-first</strong> calendar: the scheduling of Calendly, the daily client of Fantastical.<br>
  What your invitees tell you — and what you put in your own calendar — is <strong>end-to-end encrypted</strong>.<br>
  The server knows <strong>when</strong> you are busy. It can never know <strong>what</strong> you are doing.
</p>

<p align="center">
  <a href="docs/roadmap.md">Roadmap</a>
  &nbsp;·&nbsp;
  <a href="docs/ARCHITECTURE.md">Architecture</a>
  &nbsp;·&nbsp;
  <a href="docs/adr/0002-zero-knowledge-invitee-data.md">Zero-knowledge (ADR)</a>
  &nbsp;·&nbsp;
  <a href="#privacy--the-differentiator">Privacy</a>
  &nbsp;·&nbsp;
  <a href="#screenshots">Screenshots</a>
  &nbsp;·&nbsp;
  <a href="#run-development">Self-hosting</a>
</p>

<p align="center">
  <a href="https://github.com/stackopshq/ghostcal/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/stackopshq/ghostcal/ci.yml?style=flat-square&label=CI&logo=githubactions&logoColor=white&color=00F0FF"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.14-00F0FF?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-async-00F0FF?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-RLS-00F0FF?style=flat-square&logo=postgresql&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-16-00F0FF?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="Crypto" src="https://img.shields.io/badge/crypto-WebCrypto%20%2B%20hash--wasm-00F0FF?style=flat-square">
  <img alt="Lint: Ruff" src="https://img.shields.io/badge/lint-ruff-00F0FF?style=flat-square&logo=ruff&logoColor=white">
  <img alt="Types: mypy strict" src="https://img.shields.io/badge/types-mypy%20strict-00F0FF?style=flat-square">
  <img alt="License: AGPL-3.0" src="https://img.shields.io/badge/license-AGPL--3.0-00F0FF?style=flat-square">
</p>

---

> **Project status — v0.1.** A working scheduler (FastAPI) and booking frontend (Next.js) built on a
> pure, exhaustively-tested availability engine: timezone- and DST-correct slot computation with
> **no-double-booking guaranteed by the database**, not by the application. Multi-tenant from day one
> (Postgres RLS), **zero-knowledge** invitee data and calendar content throughout, and part of the
> [ghost suite](https://github.com/stackopshq) — it talks to GhostMail, and neither app ever calls the
> other's backend.

## Privacy — the differentiator

A plain Calendly clone has no reason to exist. GhostCal's reason is **privacy**, in the spirit of
the ghost suite ([ghostbit](https://github.com/stackopshq/ghostbit) for pastes,
[ghostmon](https://github.com/stackopshq/ghostmon) for monitoring). Scheduling isn't a paste bin —
the server *must* email people and prevent double-booking — so we push zero-knowledge as far as the
product allows and encrypt the rest at rest. Three honest tiers:

**🔒 Tier 1 — zero-knowledge (the server can never read it).** The invitee's **name**, their
**answers to your custom questions** (phone, address, "what's this about", case numbers, medical
context…) and a free-text **notes / agenda** field are sealed in the browser
(WebCrypto X25519 ECDH → AES-256-GCM) to your organization's public key. The server
stores one opaque blob and **cannot decrypt it** — only you can, in your browser.

```
Invitee's browser  ──seal(name+answers+notes, ORG_PUBLIC_KEY)──▶  server stores ciphertext only
Your browser       ──open(blob, ORG_PRIVATE_KEY)──▶  decrypted on the dashboard, never on the server
```

Your org **private key** never reaches the server: it is wrapped with a key derived from your
password (Argon2id) and again under a one-time **recovery key** (ProtonMail-style), so a forgotten
password is recoverable but the server still holds nothing usable.

**🛡️ Tier 2 — encrypted at rest (a stolen database dump reveals nothing).** Fields the server
genuinely needs — invitee **email**, additional **guest emails**, the **meeting link**/location —
are envelope-encrypted with the application key (transparent SQLAlchemy `TypeDecorator`s). The
server can decrypt them to send a reminder days later; a leaked dump cannot.

**⏱️ Tier 3 — cleartext, irreducible.** Only the **slot time** stays in the clear — it is the
backbone of the Postgres `EXCLUDE` no-double-booking constraint and drives reminders and calendar
sync. Times without identities leak little.

| Data | What the server can do | Where it's readable |
|---|---|---|
| Name, answers, notes | **Nothing** — ciphertext only | Your browser (dashboard) |
| Invitee & guest emails, meeting link | Decrypt with the app key to send mail | App memory at send time; never a plain dump |
| Slot time, status | Read (integrity + scheduling) | Database |

No telemetry, no third-party calls on the booking path, multi-tenant **Postgres Row-Level
Security** everywhere, signed stateless links for invitee self-service. See
**[ADR-0002](docs/adr/0002-zero-knowledge-invitee-data.md)** for the full design and its limits.

## Screenshots

**Recovery key (zero-knowledge sign-up).** The org keypair is generated in the browser; the private
key is wrapped under your password and a one-time recovery key — shown once, never sent to the
server:

![Zero-knowledge recovery key at sign-up](docs/assets/register-recovery.png)

**Optional SSO / OIDC.** Sign in with your identity provider (Authlib + PKCE). SSO proves *who* you
are; a separate encryption passphrase — which the server never sees — is what decrypts your content,
so single sign-on never weakens the zero-knowledge guarantee:

![Sign in with password or SSO](docs/assets/login-sso-dark.png)

**Host dashboard — decrypted in your browser.** The booking row's name and the "Decrypted details"
panel (phone, topic, notes) are opened client-side; the server only ever held ciphertext:

| Dark | Light |
| --- | --- |
| ![Meetings, decrypted, dark](docs/assets/meetings-decrypted-dark.png) | ![Meetings, decrypted, light](docs/assets/meetings-decrypted-light.png) |

**Booking page — sealed before it leaves the browser.** Timezone-aware slots, custom questions and
a notes field; everything personal is end-to-end encrypted on submit:

| Dark | Light |
| --- | --- |
| ![Booking page, dark](docs/assets/booking-page-dark.png) | ![Booking page, light](docs/assets/booking-page-light.png) |

**Event types & availability.** Solo / round-robin / collective / group events with buffers, notice
and custom questions; a weekly, timezone-correct availability editor:

| Event types | Availability |
| --- | --- |
| ![Event types](docs/assets/event-types-dark.png) | ![Availability editor](docs/assets/availability-dark.png) |

**Private calendar — the server knows *when*, never *what*.** A zero-knowledge month view: event
titles, locations and notes are sealed in your browser; only the times are cleartext (so free-busy
and reminders still work). The foundation for ghostmail:

| Dark | Light |
| --- | --- |
| ![Calendar, dark](docs/assets/calendar-dark.png) | ![Calendar, light](docs/assets/calendar-light.png) |

**Share *when* you are free, never *what* you are doing.** Three ways to share, and they are not the
same promise — the UI says so in as many words. A **calendar link** carries its decryption key in the
URL fragment (the server never sees it). An **availability link** carries **no key at all**: your busy
*times* are already cleartext on the server (the booking engine has to know them to offer slots), so
there is nothing to hand over. Whoever finds it learns *when* you are occupied, and never once *what*
occupies you — and "Email it" drops it straight into the GhostMail composer:

| Sharing, three ways — dark | Light |
| --- | --- |
| ![Share panel with availability links, dark](docs/assets/busy-share-dark.png) | ![Share panel, light](docs/assets/busy-share-light.png) |

**What the recipient sees.** No account, no key, no titles. The seven meetings behind this page are
sealed; the server could not name them if it wanted to, and it was never asked to:

| Availability, as a visitor sees it — dark | Light |
| --- | --- |
| ![Free-busy page, dark](docs/assets/busy-visitor-dark.png) | ![Free-busy page, light](docs/assets/busy-visitor-light.png) |

**A free, open-source, privacy-first Fantastical.** Month / **week** / **day** views, plus
**natural-language quick-add** — type *“Lunch with Sam tomorrow 12:30 for 1h at Café”* and the event
is parsed in your browser (EN/FR) and sealed before it’s saved:

| Week view — dark | Week view — light |
| --- | --- |
| ![Week view, dark](docs/assets/calendar-week-dark.png) | ![Week view, light](docs/assets/calendar-week-light.png) |

**Public calendars & weather, right in the grid.** Subscribe to any public **iCal/ICS feed**
(holidays, sports fixtures, a shared calendar) — it becomes a read-only, toggleable overlay. Add a
location and the **daily forecast** overlays the month cells and week/day headers. The feed is
fetched server-side (SSRF-guarded); the weather location stays on your device and is never persisted:

| Month + weather + subscription — dark | Light |
| --- | --- |
| ![Calendar with weather and an ICS subscription, dark](docs/assets/calendar-weather-month-dark.png) | ![Calendar with weather and an ICS subscription, light](docs/assets/calendar-weather-month-light.png) |

| Week view with forecast in the headers — dark | Light |
| --- | --- |
| ![Week view with weather, dark](docs/assets/calendar-weather-week-dark.png) | ![Week view with weather, light](docs/assets/calendar-weather-week-light.png) |

**Tasks — a zero-knowledge to-do list.** The Fantastical companion you use daily: natural-language
quick-add (*“Call the dentist tomorrow 3pm”* sets the due date), check to complete, due-date sort.
Titles and notes are sealed client-side; only the due date is cleartext:

| Dark | Light |
| --- | --- |
| ![Tasks, dark](docs/assets/tasks-dark.png) | ![Tasks, light](docs/assets/tasks-light.png) |

## Features

- **Event types** — solo, **round-robin** (least-loaded host), **collective** (all hosts attend),
  and **group** (many invitees per slot, capacity). Buffers, minimum notice, bookable window,
  per-day caps, and **custom booking questions** (text/select/checkbox/…) — answers are
  zero-knowledge.
- **Booking page** — timezone picker, custom questions, a notes field, additional guests; readable
  slug URLs; an **embeddable widget** (`/embed/...`) with a copy-paste iframe snippet.
- **Private calendar** — a zero-knowledge month view: create recurring events whose
  title/location/notes are sealed in the browser; the server stores ciphertext and only reads the
  times (for free-busy and reminders). Unified agenda over your events + bookings + external busy.
- **Privacy** — zero-knowledge invitee name/answers/notes and calendar content (WebCrypto X25519
  ECDH + AES-256-GCM, Argon2id-wrapped org key + recovery key); at-rest envelope encryption for
  emails and meeting links; multi-tenant Postgres RLS; no telemetry, no third-party calls on the
  booking path.
- **Sharing** — inside the team (read-only or read-write, decrypted with the team key they already
  hold); **outside** it by secret link, the key riding in the URL fragment so the server can serve a
  calendar it cannot read ([ADR-0009](docs/adr/0009-sharing-a-calendar-outside-the-organization.md));
  and **free-busy links** that show when you are busy and never what you are doing — no key, because
  there is nothing to decrypt ([ADR-0010](docs/adr/0010-free-busy-links.md)).
- **Meeting invitations** — an `.ics` in a GhostMail message is parsed in the browser and imported
  *exactly*: end time, location and recurrence survive, where a natural-language guess would have
  flattened a 90-minute weekly stand-up into a one-off hour. A cancellation offers no button.
- **Account lifecycle** — deletion (with tombstoned shared bookings), data export, retention and
  auto-purge ([ADR-0006](docs/adr/0006-account-lifecycle-and-erasure.md)).
- **Key rotation** — rotate the organization keypair and re-seal, so removing a member truly revokes
  the key they had cached ([ADR-0007](docs/adr/0007-per-user-keypairs-and-org-key-rotation.md)).
- **Invitee self-service** — cancel / reschedule via a signed link (no account).
- **Teams** — organizations, members & roles (owner/admin/member), token invitations.
- **SSO / OIDC** — optional single-provider sign-in (Authlib, PKCE), off by default. Authentication
  only: the zero-knowledge content stays sealed and is unlocked by a **separate encryption
  passphrase** the server never sees (Proton/Bitwarden-style), so SSO never weakens the guarantee.
- **Meeting polls** — propose times → invitees vote → host finalizes and everyone is emailed.
- **Notifications** — confirmation/cancellation emails with `.ics`; automated **reminders**
  (Celery). Server-sent mail never names the invitee — that stays encrypted.
- **Calendar sync** — bidirectional **CalDAV** (read busy + write bookings).
- **Public calendar subscriptions** — subscribe to any public **iCal/ICS feed** (holidays,
  fixtures, a shared calendar); read-only, colour-coded, toggleable overlays, refreshed by a
  background worker. Fetched server-side behind the SSRF guard; event summaries encrypted at rest.
- **Weather** — an optional **daily forecast** (Open-Meteo, keyless) overlaid on the month cells
  and week/day headers. Proxied server-side to keep the CSP strict; the location stays on-device.
- **Integrations** — outbound **webhooks** (HMAC-signed) for booking/poll events.
- **i18n** — full UI in English and French, with a light/dark theme toggle.
- **Ops** — per-IP rate limiting, Redis availability cache, booking **analytics** dashboard,
  structured JSON logs with request ids.

## Roadmap

**Shipped:** the scheduler; zero-knowledge invitee data and team key sharing; the zero-knowledge
calendar and the personal client on top of it (natural-language quick-add, month/week/day/year views,
tasks, attendees & RSVP, external CalDAV and ICS calendars, notifications, command palette); account
lifecycle and GDPR erasure; organization **key rotation** (so removing a member revokes the key they
cached); sharing **outside** the organization by secret link, and **free-busy** links; and the suite
integration — SSO, the ghostboard portal widget, the app switcher, and the GhostMail bridges in both
directions (`.ics` invitation import in, "email guests" and "email my availability" out).

A self-hoster whose CalDAV server lives on their own LAN can now reach it: set
`GHOSTCAL_CALENDAR_ALLOWED_PRIVATE_CIDRS` to the range it sits on. Empty by default, so a hosted
deployment keeps refusing every private address, and the cloud-metadata address stays refused
however it is set. *(see [ADR-0011](docs/adr/0011-private-network-allow-list-for-self-hosting.md))*

**Next** — see **[docs/roadmap.md](docs/roadmap.md)**: invitations that carry no key in the link.

## Stack

Python 3.14 · FastAPI · PostgreSQL (RLS, `tstzrange` + `EXCLUDE`) · SQLAlchemy 2.0 (async) ·
Alembic · Celery (Redis) · Next.js 16 + WebCrypto/hash-wasm (frontend). Tooling: `uv`, `ruff`, `mypy`,
`pytest` + Hypothesis. Containers built and run with **Podman**.

## Run (development)

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Podman, and PostgreSQL + Redis (via the
provided compose file).

```bash
uv sync                                  # create .venv and install all deps
cp .env.example .env                     # then edit secrets
podman-compose up -d postgres redis      # local infra
uv run alembic upgrade head              # apply migrations
uv run uvicorn ghostcal.presentation.api:app --reload
# → http://127.0.0.1:8000/health  and  /docs
```

Run the Celery worker and the beat scheduler (background jobs incl. periodic CalDAV sync and
reminders):

```bash
uv run celery -A ghostcal.celery_app:celery_app worker -l info
uv run celery -A ghostcal.celery_app:celery_app beat -l info
```

The frontend (Next.js) runs separately:

```bash
cd frontend && npm install && npm run dev   # → http://localhost:3001  (proxies /api to :8000)
```

### Full stack in containers

The whole backend runs as separate Podman containers — Postgres, Redis, the API, the Celery worker
and the Celery beat scheduler (app and Celery share one image). Set the secrets in `.env` (see
`.env.example`, including `GHOSTCAL_APP_DB_PASSWORD` and `GHOSTCAL_TOKEN_ENCRYPTION_KEY`), then:

```bash
podman-compose up -d --build
# postgres provisions the non-privileged app role; the one-shot `migrate` service runs
# `alembic upgrade head`; then app (:8000), worker and beat start.
```

To send real emails, set `GHOSTCAL_BREVO_API_KEY` or `GHOSTCAL_RESEND_API_KEY` (otherwise emails are logged, not sent). Brevo is used when both are present.

> **Key management note.** `GHOSTCAL_TOKEN_ENCRYPTION_KEY` decrypts the at-rest (Tier 2) data; keep
> it stable and backed up. The zero-knowledge (Tier 1) keys are derived in the browser — the server
> never has them, so rotating the app key never exposes invitee answers.

## Test

```bash
uv run ruff check .          # lint
uv run ruff format --check . # format
uv run mypy                  # types (strict)
uv run pytest                # unit + integration (skips integration when no DB is reachable)
cd frontend && npm run lint && npm run build
```

## Architecture

Hexagonal (ports & adapters): `domain/` (pure logic, no I/O) → `application/` (use cases + ports) ←
`infrastructure/` (adapters); `presentation/` (FastAPI). The domain never reads the clock — "now"
is injected — so availability is deterministic and property-testable. See
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** and **[docs/adr/](docs/adr/)**.

## License

[GNU AGPL-3.0-or-later](LICENSE). Network use is distribution: anyone interacting with a modified
GhostCal over a network must be offered the corresponding source.
