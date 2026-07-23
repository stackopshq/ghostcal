# GhostCal roadmap

GhostCal is a **privacy-first scheduler that became a private calendar** — the agenda layer of the
ghost suite. The through-line is the suite's promise: the server stores ciphertext it can never
read. This roadmap tracks where that promise has reached and where it's going.

## Shipped

### Scheduling core

Pure, property/DST-tested availability engine; booking pages (solo, round-robin, collective,
group); database-guaranteed no-double-booking (`EXCLUDE`); meeting polls; CalDAV busy sync; HMAC
webhooks; analytics. Multi-tenant Postgres RLS throughout. Full UI in EN/FR.
*(see [ADR-0001](adr/0001-stack-and-architecture.md))*

### Zero-knowledge

- **Invitee data.** Invitee name, custom-question answers and notes are sealed in the browser to
  the org public key; the server stores one blob it cannot read. Email/guest emails/meeting links
  are encrypted at rest; only slot times stay cleartext.
  *(see [ADR-0002](adr/0002-zero-knowledge-invitee-data.md))*
- **Team key sharing.** A teammate can decrypt org data: the org key travels in the invitation
  link fragment (`#k=`), never to the server; multi-org unlock at login.
  *(see [ADR-0003](adr/0003-team-zero-knowledge-key-sharing.md))*
- **Crypto stack.** X25519 ECDH + AES-256-GCM (ECIES) + hash-wasm Argon2id on WebCrypto — no
  heavyweight crypto dependency. CSP with `wasm-unsafe-eval`.
- **Security.** Full pentest hardening pass; org invitations are only acceptable by the verified
  owner of the invited email.
- **Self-hosting without weakening the egress guard.** The SSRF guard refuses every private
  address, which is right for a hosted deployment and left self-hosters unable to reach their own
  Nextcloud or Radicale on the LAN. `GHOSTCAL_CALENDAR_ALLOWED_PRIVATE_CIDRS` names ranges to open
  — empty by default, calendars only (never webhooks), and link-local stays refused however it is
  set, so no configuration can expose the cloud-metadata address.
  *(see [ADR-0011](adr/0011-private-network-allow-list-for-self-hosting.md))*

### Private calendar

- **Phase 1 — foundation.** `calendars`/`calendar_events`; a pure DST-correct recurrence engine;
  CRUD + unified agenda (events + bookings + external busy); a month view that seals/decrypts event
  content in-browser. *(see [ADR-0004](adr/0004-zero-knowledge-calendar.md))*
- **Phase 2 — sync & richness.** Event reminders (Celery, time-only); recurrence
  overrides/exceptions (edit/delete one occurrence); external CalDAV event titles in the agenda
  (encrypted at rest, read-only).
- **Phase 3 — shared calendars, read-only or read-write.** Share a calendar with org members, who
  decrypt it with the org key they already hold — so an editor unseals and re-seals exactly as the
  owner does, and the server sees ciphertext either way. Access is a property of the *calendar*, not
  of who created an event on it: that is the only rule under which an event an editor adds to your
  calendar is visible to you. *(see [ADR-0005](adr/0005-shared-calendars.md))*

### Personal calendar client (the Fantastical layer)

The daily-use core of a calendar client, all zero-knowledge unless noted:

- **Natural-language quick-add** (chrono-node, client-side, EN/FR): date, time, duration,
  recurrence, location — sealed in the browser.
- **Month, week and day views** (time grid), with multi-calendar overlays, per-calendar colours and
  visibility toggles.
- **To-do list** with due dates (reusing the quick-add parser) and content-less email reminders.
- **Attendees & RSVP** on personal events: the server stores guest email + status only; the
  organiser's browser supplies the cleartext title to build the ICS at send time, never persisted.
- **Browser notifications** for events and tasks (client-side, so they can show the *decrypted*
  title — unlike the content-less email reminders).
- **Keyboard UX**: command palette (⌘/Ctrl+K) and calendar shortcuts.
- **External calendars as a first-class overlay**: CalDAV events appear coloured and toggleable in
  the personal views, with a "Sync now" action. *Not* zero-knowledge — the server holds the CalDAV
  credentials; an honest, labelled trade-off.
- **Public ICS subscriptions** (fetch → cache) and a **daily weather forecast** in the calendar.
- **Several CalDAV accounts** per member (work + personal + family), each its own coloured overlay.
  Bookings mirror onto exactly one of them — a partial unique index makes "exactly one" true in the
  database, not merely by convention.
- **Five views**: month, week, day, **year** (twelve months, busy days marked — a year has no room
  for titles, and the server could not read them anyway) and **list** ("what is next?", which is the
  question people actually open a calendar to ask).
- **Publish a calendar to CalDAV** — your GhostCal events on your phone, with the server still unable
  to read one. It cannot build the VEVENT, so the browser does: it opens each event and hands the
  cleartext over at push time, and the server relays it and stores none of it. The honest price is
  that a push waits for a browser; a queue makes that liveable.
  *(see [ADR-0008](adr/0008-calendar-publication-without-server-reads.md))*
- **Share a calendar outside the organization**, by secret link — with someone who has no GhostCal
  account at all. The link carries its own keypair; its private half lives in the URL fragment and
  never reaches the server. ADR-0005 had parked this as "grant them the org key", which would have
  handed an outsider the encrypted contents of the *entire organization* to show them one calendar.
  *(see [ADR-0009](adr/0009-sharing-a-calendar-outside-the-organization.md))*

### Suite integration

- **SSO / OIDC login** against GhostAuth (backend + frontend).
- **Ghostboard portal**: a GhostAuth *resource server* on the portal-facing routes only (the app's
  own API keeps its local session), a public `ghostapp.yaml`, and two widgets. They are `stat`
  widgets and will stay `stat` widgets — the server holds event and task titles as ciphertext, so a
  "your next meetings" list is not a widget we chose not to build but one we *cannot* build.
- **GhostMail bridges**, both directions and fully decoupled deep-links (no cross-app backend
  calls, zero-knowledge preserved on both sides): "add to calendar" from a detected date in an
  email → GhostCal quick-add prefill; "email guests" from an event → GhostMail composer.
- **Meeting invitations** (`.ics`) read out of an email and imported exactly. The natural-language
  bridge above *guesses* — and a sentence cannot carry an end time, a location or a recurrence rule,
  so a 90-minute meeting arrived as the default hour. An `.ics` states all three. GhostMail parses
  the attachment in the tab (it is sealed, so only the browser can) and hands the event over through
  a **structured** import link; GhostCal opens the event form, and nothing is saved until the user
  confirms. An invitation email *is* an `.ics`, so this is also how invitations land in the
  calendar — there was never a second feature to build there.
- **Free-busy sharing** (ADR-0010): a link that shows *when* you are busy and never *what* you are
  doing, plus "email it" straight into the GhostMail composer. It needs no sealing at all — busy
  times are already cleartext on the server, because the booking engine has to reason about them —
  so it carries no key and has no fragment, and whoever finds it learns strictly what the server
  already knows.
  Building it is what exposed that the scheduler **could not see your own events**: "Dentist, 14:00"
  in your calendar did not stop a stranger booking you at 14:00. There is now one definition of
  busy, and both the booking page and the free-busy link read it.
- **Ghost-suite app switcher** (Calendar ↔ Mail).

### Account lifecycle

Erasure, portability and storage limitation — the three things a privacy-first product cannot
plausibly ship without. Account deletion (an org you are the sole member of goes with you; in a
shared one you are anonymized out of the records you co-own), data export **assembled in the
browser** (the server holds ciphertext it cannot open, so a server-side export would hand you
base64), and an opt-in booking retention window with a purge job.
*(see [ADR-0006](adr/0006-account-lifecycle-and-erasure.md))*

### Key rotation & revocation

Removing a member used to revoke *nothing*: they kept the org key, and the org's public key never
changed, so everything created **after** they left was still sealed to a key they held. Now each
user has their own keypair, an admin can rotate the org keypair — sealing the new key directly to
every remaining member, who do nothing — and the backlog of already-sealed records is re-sealed in
the browser, batch by batch, resumably. When the backlog reaches zero, the old key opens nothing at
all. *(see [ADR-0007](adr/0007-org-key-rotation-and-revocation.md))*

### Hardening

A pass over the boundaries the product's central claim rests on. Each of these was a real defect
with a test that fails against the unfixed code, not a tidy-up.

- **A public link could publish another calendar's events.** ADR-0009's premise is "a link is one
  calendar" — the reason sharing outside the org is not "hand them the org key" — and nothing
  enforced it. A member with read access to a colleague's shared calendar could mint a link on their
  own, seal the colleague's event into it, and publish that event's `start_at`, `rrule` and
  `exdates` to an anonymous URL, with no trace on the colleague's side. Content stayed sealed, so
  this was metadata; but a weekly recurrence on a private appointment is a standing commitment, and
  the exposure was to the open internet. Closed at both ends: the write path filters incoming event
  ids to the link's own calendar, and the SECURITY DEFINER function re-derives the event set instead
  of trusting a table the application writes.
- **SSO could take over an account.** `upsert_oidc_identity` linked an OIDC login to any local
  account sharing its email, on the strength of a comment saying the IdP had verified it — the
  `email_verified` claim appeared nowhere in the codebase. Two takeovers followed, needing two
  checks: the provider must assert the address (absent counts as unverified), and the *local*
  account must already be verified, or someone could register a victim's address, never verify it,
  and wait to be seated in an organization whose key is wrapped under their own passphrase. The
  first also closed a bypass of the invitation binding, since the provisioning branch wrote
  `email_verified_at` on the IdP's say-so and that timestamp is exactly the invitation's proof.
- **A password change broke in any rotated organization.** `rewrap_zk_key` predates ADR-0007
  generations: its UPDATE matched every row for (user, org), which was right when there was one and
  wrong the moment an org rotated. Members of exactly the organizations that used the revocation
  feature could not change their password without a 500 that left the org key wrapped under the old
  one. No attacker required. Now scoped to `sealed_org_key IS NULL`.
- **Reminder claims did not have to belong to the org they named.** Both claim functions took a
  caller-supplied organization id nobody checked against the target's owner, making each a
  cross-tenant denial-of-notification primitive — take the unique constraint under your own org id
  and the worker suppresses the real reminder. Unreachable through any route today, which is routing
  rather than a control.
- **`FORCE ROW LEVEL SECURITY` on the four tables that only `ENABLE`d it.** Defence in depth rather
  than a live hole — the app connects as a non-owner, so isolation held — but the schema disagreed
  with itself, and the test now asserts the property over the whole catalogue so the next table
  cannot quietly join the exceptions.
- **A password floor of 12, and breached passwords refused.** Here a password is not only the
  account: it wraps the private key that decrypts the calendar. The policy now lives in one place
  both registration and change call, and new passwords are checked against Have I Been Pwned's
  k-anonymity range API — five hex characters of a SHA-1 and nothing else, off by one setting, and
  failing open so a third party's bad day is an advisory rather than an outage.
- **An append-only audit log.** There was no trail at all — no logins, role changes, member
  removals, deletions or key rotations. Append-only in the database rather than by convention: the
  app role holds INSERT and SELECT and is denied UPDATE and DELETE, so whoever reaches that
  connection can add noise but cannot remove the entry recording what they did. It records that
  something happened and never the content it happened to, because an audit log is the worst place
  to start accumulating the plaintext this product exists not to hold. Key rotation is wired; the
  remaining call sites follow (see *Next*).

### Operations

- **Backup and restore, drilled rather than assumed.** There was no script and no runbook, which
  matters more here than elsewhere: the server stores ciphertext it cannot read, so a lost database
  is permanent total loss, not "restore from an export". The backup refuses to call itself one if it
  contains no table data; the restore refuses a non-empty target without `FORCE=1` and **fails** if
  no RLS policies came back, since an instance that restored tables but not policies looks healthy
  and leaks across organizations on the first request. The runbook is explicit about what it does
  not cover — no PITR, no off-site copies — and about the one thing no backup fixes: a forgotten
  password loses a wrapped private key, which is key management, not recovery.
- **Bounded connections and a clean shutdown.** Statement and idle-in-transaction timeouts on every
  connection, a pool sized against `max_connections` with the arithmetic written down, and a
  lifespan handler that disposes the pool — without which a rolling restart overlaps the old
  process's slots with the new one's, which is how a deploy exhausts a comfortably-provisioned
  database.
- **A background layer that survives a bad day.** Webhook delivery retries with jittered doubling
  backoff, but only on 5xx, 429 and transport errors — a 4xx is the subscriber saying no. Deliveries
  carry a stable `X-GhostCal-Event-Id`, because delivery is at-least-once by construction and what
  consumers are owed is the means to deduplicate. Task time limits, and the beat schedule moved off
  the container's ephemeral layer, where the 24 h retention purge — the one job with a GDPR
  obligation behind it — would silently never run on a beat container restarting more often than
  daily.
- **Observability.** 500s used to be absent from the access log, the one class of request that meant
  something was wrong. Prometheus metrics, self-hosted and pull-based, labelled by **route template
  and never request path** — a privacy rule before a cardinality one, since these URLs carry org
  slugs and invitation and booking-management tokens, and a metrics store is somewhere nobody thinks
  of as holding secrets. The request id now travels into the queue, so a webhook delivery can be
  traced back to the booking that caused it.
- **Rate limiting on an address the client cannot choose.** `_client_ip` honoured `X-Forwarded-For`
  from any peer, so every request could land in a fresh bucket and the auth limiter counted nothing.
  Only peers inside `GHOSTCAL_TRUSTED_PROXY_CIDRS` are believed now.

### Engineering

Ruff + mypy strict; pytest backend suite; Vitest frontend suite; CI (lint, format check, tests,
build, security scan).

CI runs the **whole** backend suite, integration included. It used to run 91 of 210 tests and
report success: without a database the integration fixtures skip, and CI had no Postgres. Everything
RLS, invitations, key rotation and reseal rely on was covered only by whoever happened to have a
local database running. The job now provisions Postgres the way compose does — application role
first, then schema, because the migrations' `GRANT EXECUTE` statements are guarded on that role
existing — and `GHOSTCAL_TESTS_REQUIRE_DB=1` makes an unreachable database a failure instead of a
silent skip.

**The deployed artefact is scanned, and the bases it is built from are pinned.** osv-scanner covers
`uv.lock` and `frontend/package-lock.json` — our dependencies, not the operating system underneath
them, which was the largest unscanned surface in what actually ships. Trivy now scans the built
image for HIGH/CRITICAL, with `ignore-unfixed` on, because a build that cannot be made green is a
build people learn to ignore. Both base images are pinned by digest: a tag is mutable, so an
unpinned build is neither reproducible nor meaningfully scannable.

**CI runs on a self-hosted runner, and deliberately uses no `docker` CLI.** GitHub-hosted minutes
are unavailable on the account, which is worth knowing before reading a red check: a job that never
got a runner fails in three seconds with no steps and an empty `runner_name`, and the reason appears
only in the check-run annotation. The runner has rootless podman and no `docker` binary, and the
Actions runner shells out to that binary rather than speaking to a container API — so `services:`
blocks and Docker actions cannot be used at all. Postgres is started by an explicit podman step with
a readiness wait and a teardown that also runs on failure, `bootstrap_roles.sql` is piped into the
container's own psql, and osv-scanner runs as a checksum-verified binary. Two properties of a
long-lived runner are load-bearing here and were each learned the hard way: leftover state must be
cleared *before* a step, not only after, and anything written to `/tmp` outlives the job.

## Next

1. **Invitations without a key in the link.** *Every* invitation still uses the ADR-0003 fragment
   grant — including invitations to people who already have an account, which ADR-0007 §5 wrongly
   claimed were already sealed to their public key. (That section has been corrected; the branch it
   described was never built.) So an invitation link emailed to someone carries, in that email, the
   means to open the organization's data.

   Closing it is a real redesign, not a patch. The invitee's keypair is generated at first *login*,
   not at registration, and only a member holding the org key unlocked can seal it — never the
   server. So the grant must happen after the invitee arrives, performed by someone who already
   holds the key, with the invitee in a "pending access" state until they do. It needs its own ADR.

2. **Finish wiring the audit log.** The table, the append-only grants and `AuditLog.record` are
   shipped, and org key rotation writes to it. Login, role changes, member removal and account
   deletion do not yet — they are the events the log exists for, and each is a few lines calling the
   same recorder. Until they land, the log answers "who rotated the key" and nothing else, which is
   a fraction of what its own docstring promises.

## Later

- **"This calendar counts towards my availability."** Your own events now block your booking page —
  they always should have (see Shipped). But the toggle is all-or-nothing, and not every calendar is
  a claim on your time: an "Anniversaries" calendar should not empty your booking page. The Cal.com
  model is a `blocks_availability` flag per calendar, defaulting to on. Additive, no painful
  migration — worth doing when someone actually complains, and not before.
- **An expiry on shared links.** Neither a calendar link (ADR-0009) nor a free-busy link (ADR-0010)
  ever dies on its own. Revocation is deletion, and that is honest, but "share my availability with
  this recruiter for two weeks" is the normal case and today it means remembering to come back.
- **True two-way CalDAV sync.** Publication is one-way; changes made on the phone come back through
  the busy-sync, not through a reconciliation. A real merge would need the server to read both
  sides — which is exactly what ADR-0008 declines to let it do.

## Debt and traps

Things a newcomer would otherwise rediscover the hard way. None of them is urgent; all of them are
real.

- **`alembic revision --autogenerate` no longer proposes DROPs, and here is why it did.** Half this
  schema is created by hand-written SQL inside migrations — RLS policies, SECURITY DEFINER
  functions, triggers, partial and GiST indexes — and is declared on no model, so autogenerate read
  it as deletable. Unfiltered it proposed dropping the `calendar_event_reminders` table, six indexes
  (including `uq_caldav_one_mirror_per_user`) and three trigger-maintained `updated_at` columns. An
  `include_object` filter in `migrations/env.py` now ignores anything reflected that no model
  claims, so autogenerate is **additive only**. The corollary: removing a model does not generate
  its `DROP` either. Write removals by hand, where the RLS and trigger fallout is visible.
- **`next build` does not type-check your tests.** It checks what the app imports, so a type error
  in a test file passed eslint, vitest and build alike — five were sitting in two files, all from
  `vi.fn(async () => ...)` inferring a zero-parameter mock. CI now runs `tsc --noEmit` as its own
  step, which is the only one of the four that sees them.
- **`bootstrap_roles.sql` will silently un-revoke a grant you took away.** It ends with a blanket
  `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES`, and it is idempotent by design because it is
  how the app role's password is rotated. Re-running it therefore restored UPDATE and DELETE on
  `audit_events` and destroyed the append-only property, with no error and no failing test. The
  script now re-asserts that revoke last. Any future table that needs narrower grants than the
  blanket has to be handled there too, or the next password rotation quietly widens it.
- **A new tenant table must use `NULLIF(current_setting(...), '')::uuid` in its RLS policy.**
  `set_config(is_local => true)` reverts a custom GUC to the empty string, not to unset, so the raw
  form raises on `''::uuid` instead of matching nothing — and an unbound read on a recycled pooled
  connection 500s. Migration `b2d8f30c17ae` swept every policy to the safe form; `audit_events` was
  written nine revisions later and reintroduced the bug, which is how easily this comes back. Copy
  the pattern from a recent tenant table, not from an old one.
- **A test that only drives the honest path proves nothing about the dishonest one.** Three separate
  defects in this batch survived a passing test that exercised a route production does not take, or
  sealed only what the client offered it, or asserted the vulnerable behaviour as correct. Where the
  fix is a boundary check, the test has to take the path an attacker would.
- **Ghostboard's registry stub still promises a widget we cannot serve.** Its local
  `apps_registry/ghostcal.yaml` declares an "upcoming events" **list** widget. Event titles are
  ciphertext, so the server can serve a *count* and never a list — fix the registry, not the
  architecture. It is **inert in the normal case**: the portal fetches our published manifest and
  replaces its stub's widgets wholesale. It goes live only when that fetch fails and the portal
  falls back, at which point it renders a permanently empty card rather than an error. The fix
  belongs in the ghostboard repo.
  On our side the manifest is now pinned by a test asserting every path it declares resolves to a
  route this app serves — added after finding it advertised a `/healthz` that never existed.

## Exploring

- **Desktop shell.** Only worth building for what a browser cannot do: a tray/menubar agenda, a
  **global hotkey** on the existing natural-language quick-add, native notifications when the app is
  closed, launch-at-login, offline. Leaning **Electron over Tauri**: the zero-knowledge layer relies
  on native WebCrypto **X25519**, whose support in system webviews (WebKitGTK, WKWebView) is recent
  and version-dependent, while Electron ships its own Chromium. One shell for the whole suite, not
  one per app. Without the tray + hotkey + notifications trio, a PWA gets most of the value for a
  fraction of the cost.
