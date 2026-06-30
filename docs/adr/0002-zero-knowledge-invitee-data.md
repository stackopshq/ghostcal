# ADR-0002: Zero-knowledge invitee data

- Status: Accepted
- Date: 2026-06-30

## Context

A plain Calendly clone has no reason to exist. GhostCal belongs to the **ghost suite**
(`ghostbit`, `ghostmon`), whose shared reason to exist is **privacy**: the server stores
ciphertext it cannot read, and decryption keys never reach it. GhostCal must carry the same
property or it is just another scheduler.

Scheduling, however, is not a paste bin. The server **must** read some fields to do its job:

- the invitee's **email** — to send confirmation/reminder emails and write the `.ics` ATTENDEE,
- the **slot** (`start_at`/`end_at`) — the no-double-booking `EXCLUDE` constraint, reminders, and
  CalDAV mirroring all operate on it,
- additional **guest emails** — the server emails them,
- the **invitee name** and **timezone** — embedded in emails and the `.ics`.

So full zero-knowledge ("the server can never read *anything*") is impossible here, and pretending
otherwise would be dishonest. We define an explicit, defensible boundary instead — exactly as
`ghostmon` does, where only items flagged *private* are zero-knowledge.

## Decision

Push zero-knowledge as far as the product allows, and encrypt the rest at rest. Three tiers:

**Tier 1 — zero-knowledge (the server can never read it).** Sealed into one opaque blob
(`bookings.invitee_private`):

- the invitee's **name**,
- the invitee's **answers to the custom questions** (phone, address, "what do you want to
  discuss", case/reference numbers, medical context for a clinician's page, …), and
- a free-text **notes / agenda** field.

The server stores and returns the blob and cannot read it. Consequence: server-sent emails and the
host's external calendar cannot show the invitee's name — they show the email (Tier 2) and the
host sees the name only after decrypting in the dashboard.

**Tier 2 — encrypted at rest (server holds the key; a stolen DB dump reveals nothing).** Envelope
encryption with the application key (the `SecretBox`/Fernet already used for CalDAV passwords), via
transparent SQLAlchemy `TypeDecorator`s, so application code keeps seeing plaintext:

- **invitee email** and **additional guest emails** — the server must email them (including async
  reminders days later), so it needs the key; but the database never holds them in cleartext,
- **meeting URL** and **location**.

**Tier 3 — cleartext, irreducible.** The **slot** (`start_at`/`end_at`/`period`): it is the
backbone of the no-double-booking `EXCLUDE` constraint and drives reminder scheduling and CalDAV.
Encrypting it would forfeit the database integrity guarantee. Times without identities leak little.

### Cryptography

- **Sealed box** (`crypto_box_seal`, libsodium): anonymous-sender public-key encryption. The
  invitee has **no account and no key** — they encrypt to a published **organization public key**
  (X25519). Only the holder of the org private key can open it. This works uniformly for solo,
  round-robin, collective, and group event types: the booking page never needs to know which host
  will be assigned.
- **Org keypair, per-member wrapped private key.** The org private key is wrapped per member:
  `wrapped_sk = secretbox(org_sk, key = Argon2id(password, salt))` (libsodium `pwhash`,
  ghostbit parameters). The server stores only `zk_public_key`, the wrapped blobs, and salts —
  **never** `org_sk` or the password-derived key. At login the browser already holds the password,
  re-derives the wrapping key, unwraps `org_sk` into session memory, and decrypts blobs in the
  dashboard. Key generation and wrapping happen **client-side at registration**; the server
  receives only public material and ciphertext.
- **Recovery key (ProtonMail-style).** Because a forgotten password would otherwise make all
  historical answers undecryptable, registration also shows a one-time high-entropy **recovery
  phrase** and stores a second copy of the key wrapped under it
  (`recovery_wrapped_sk = secretbox(org_sk, Argon2id(recovery_phrase, recovery_salt))`). On
  password reset the host enters the phrase to recover `org_sk` and re-wrap it under the new
  password. No data loss; the phrase never reaches the server.

### Scope for this iteration

- **Solo organizations (one member) are fully zero-knowledge now** — the overwhelming majority of
  users. Each org gets a keypair at the owner's registration.
- **Teams (multiple members) are a follow-up.** Distributing the org private key to additional
  members (an existing key-holder re-wrapping `org_sk` to a new member's public key at
  invite-accept) is deferred; it is the classic E2E key-distribution problem and is scoped out of
  this iteration.

## Consequences

- **Required-answer validation moves to the client.** The server can no longer inspect answers to
  enforce that required questions are filled — it stores an opaque blob. The booking page enforces
  required fields before sealing; the server only checks that a blob is present when the event type
  has questions. This is inherent to zero-knowledge and accepted.
- **Server-sent copy cannot name the invitee.** Confirmation/reminder emails, the `.ics`
  `ATTENDEE`, the host's CalDAV event, and outbound webhooks drop the invitee name (the server
  no longer has it); they fall back to the email where one was shown. The host notification
  becomes "New booking: <event>" and the host opens the dashboard to see who. The host sees the
  decrypted name and answers **only in the dashboard**, in their browser.
- **At-rest encryption is transparent but bypassed by raw SQL.** The `TypeDecorator`s
  encrypt/decrypt through the ORM; the one raw-SQL read path (the `due_booking_reminders` SECURITY
  DEFINER function used by the reminder worker) decrypts the email explicitly. Encrypted columns
  cannot be filtered or uniquely constrained in SQL — acceptable, as none are queried by value.
- **Invitee self-service is limited.** A sealed box is one-way to the host; the invitee keeps no
  key, so the manage page (cancel/reschedule via signed link) shows time/status but not the
  previously-submitted answers. Acceptable for v1.
- **Password reset requires the recovery phrase** to retain decryptability. A host who loses both
  password and recovery phrase loses access to historical encrypted answers — the irreducible cost
  of the server never holding the key. Stated plainly in the UI.
- **New frontend dependency:** `libsodium-wrappers` (sealed box, secretbox, Argon2id `pwhash`).
  The backend needs **no** new crypto: it only stores and serves base64 strings, reinforcing that
  it can never read them.
- **Data model:** `organizations.zk_public_key`, a new `org_member_keys` table (wrapped private
  keys + salts, RLS-scoped), and `bookings.invitee_private` (the sealed blob). Migration is
  reversible (`down` drops them); GhostCal is pre-launch, so no ciphertext backfill is required.
