# ADR-0006 — Account lifecycle and erasure in a zero-knowledge product

Status: accepted
Date: 2026-07-13

## Context

GhostCal ships zero-knowledge invitee data, a zero-knowledge calendar and team key sharing, but has
no account lifecycle at all: no deletion, no export, no retention. For a product whose entire
argument is privacy, missing the **right to erasure** (GDPR art. 17) and **portability** (art. 20)
is not a missing feature — it is a contradiction of the promise.

Two properties of the existing design make this harder than a `DELETE FROM users`:

1. **Records have two data subjects.** A booking belongs to the *host* (a user, who may want
   erasure) and to the *invitee* (not a user at all — no account, no login). It also belongs to the
   *organization*, which may be a company with a legitimate interest in its own meeting history.
2. **The server cannot read most of the data.** Invitee answers, calendar event content and task
   content are sealed to the org public key. The server holds ciphertext it can never open.

The schema also constrains the solution: `bookings.host_id` and `event_types.owner_id` are
`ON DELETE RESTRICT` (deliberately — they stop bookings being silently orphaned), so deleting a user
who ever hosted anything fails at the database level.

## Decision

### 1. Deletion erases the natural person, not the organization's history

Deleting an account takes one of two paths per organization the user belongs to:

- **Sole member** → the organization is deleted. Everything cascades: event types, bookings,
  webhooks, polls. Nobody else has an interest in it; erasure is total.
- **Shared organization** → the person is *anonymized out of* the organization's records. Everything
  strictly personal is deleted (credentials, identities, tokens, memberships, wrapped org keys,
  calendars and their events, tasks, schedules, CalDAV connections, subscriptions, polls) by the
  existing `ON DELETE CASCADE`. Records co-owned with the organization survive with the person
  removed from them.

**Sole owner of a shared organization → the deletion is refused (409).** An organization must remain
administrable; the user must promote another owner first. This is a precondition, not a denial of
the erasure right.

### 2. A single tombstone user carries the anonymized records

Rather than making `host_id`/`owner_id` nullable (which turns every join into a `LEFT JOIN` with a
display fallback, and changes the semantics of the `no_overlap_per_host` exclusion constraint), we
introduce **one** global tombstone user, created by migration with a fixed UUID:

- email `deleted-user@ghostcal.invalid` — RFC 2606 reserved TLD, so it can never receive mail,
- name `Deleted user`,
- **no** `user_credentials` row, **no** `identities` row, **no** `memberships` row.

It therefore cannot authenticate by any path, and never appears in a member list (membership is what
member lists are built from). Existing joins keep working and render "Deleted user".

### 3. Tombstoning must take bookings out of the exclusion constraint

`bookings` carries `EXCLUDE USING gist (host_id WITH =, period WITH &&) WHERE (status = 'confirmed'
AND blocks_host)` — the no-double-booking guarantee. Funnelling *many* deleted users' bookings onto
*one* tombstone `host_id` would make two formerly-unrelated overlapping meetings collide, and the
deletion would fail on a constraint violation.

So, when reassigning a booking to the tombstone:

- **future** confirmed bookings are **cancelled**, and their invitees notified (the host no longer
  exists — the meeting genuinely will not happen; the invitee needs to know);
- **all** reassigned bookings get `blocks_host = false` (a deleted host blocks nothing).

Both changes take the rows out of the constraint's `WHERE` clause, so the exclusion constraint can
never fire on the tombstone. This is the subtle part of the whole design.

### 4. Event types are deactivated, not deleted

Bookings reference `event_types` with `RESTRICT`, so a departing user's event types cannot be
deleted while their historical bookings exist. They are instead reassigned to the tombstone and set
`active = false`: the booking page stops accepting new bookings (there is no host behind it), while
the row survives to keep the historical bookings referentially intact.

### 5. Export is assembled in the browser, not on the server

This is the direct consequence of zero-knowledge. A server-side export endpoint could only hand the
user a file full of base64 blobs — the server cannot decrypt invitee answers, event content or task
content. That would satisfy portability on paper and be worthless in practice.

Instead: the API returns the user's complete record set **including the sealed blobs**, and the
**browser** — which holds the org private key, unwrapped at login — decrypts them and assembles the
final archive (JSON + `.ics`). Portability is real, and zero-knowledge is not weakened to obtain it.

A zero-knowledge product cannot export server-side. It has to be said out loud, because the
temptation to "just add an endpoint that returns everything" is exactly how the property gets lost.

## Consequences

- Deletion runs in a **single transaction** that rebinds the `app.current_org_id` GUC per
  organization (RLS is default-deny when the GUC is unset, and `FORCE`d even for the table owner),
  then deletes the global `users` row. Atomic across organizations.
- The `RESTRICT` foreign keys stay as they are. They are not an obstacle to work around — they are
  what forces the reassignment to be explicit and correct.
- The UI must render a tombstone host as "Deleted user" wherever a host is shown.
- Cancellation emails are sent **after** the transaction commits: the erasure must not be rolled
  back by a failing SMTP server.
- Retention/auto-purge of old bookings is a separate, org-level policy and is specified separately.
