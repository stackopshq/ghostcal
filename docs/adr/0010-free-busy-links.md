# ADR-0010 — Sharing availability, without sharing a calendar

Status: accepted
Date: 2026-07-13

Companion to [ADR-0009](0009-sharing-a-calendar-outside-the-organization.md).

## Context

ADR-0009 shares a *calendar* outside the organization. The events are sealed, so the link must carry
a key, and that key rides in the URL fragment where the server can never see it. Sealed copies, a
keypair per link, a trigger to invalidate stale copies: all of that machinery exists **because the
content is secret**.

Free-busy asks a smaller question — *when is this person occupied?* — and it is tempting to answer it
with the same machinery, minus the titles.

**That would be a mistake, and an expensive one.** Not because it fails, but because it dresses a
small disclosure in the costume of a large one, and invites the two to be confused.

## Decision

**A separate link, a separate table, and no key at all.**

The answer to "when is this person occupied?" is **already cleartext on the server**. It has to be:
the booking engine reasons about busy time to decide which slots it may offer, and it cannot reason
about ciphertext. `bookings.start_at`, `external_busy.start_at`, `calendar_events.start_at` — all of
them, plainly readable, and none of them ever sealed.

So there is nothing to encrypt, nothing to hand over, and no fragment:

- **No keypair.** A busy link discloses strictly what the server already knows.
- **No sealed copies**, and therefore no "pending" state, no re-sealing browser, no invalidation
  trigger. Minting the link shares the availability *immediately*, which an ADR-0009 link cannot do.
- **No `#` in the URL.** The whole link is the link.

### Why a separate table, and not a `kind` column on `calendar_links`

Because almost nothing is shared. The two links differ in what they point at, what they carry, what
the visitor receives, and what losing one means. What they have in common is "a token grants read
access" — which is not a reason to make one table pretend to be two things.

And they point at different things: a busy link points at a **person**, not a calendar. *"Am I
free?"* cannot be answered by one calendar while the others are ignored, and a per-calendar busy link
would confidently report you free during a meeting you had put on a different calendar.

### What it discloses, said plainly

Whoever finds this link learns **when** the owner is occupied, and **never once what occupies them**.
That is a materially smaller bargain than an ADR-0009 link — losing this one is not the same event as
losing that one — and the UI says so in those words rather than showing two links that look alike.

### Merged blocks, not raw ones

The busy intervals are merged before they leave the server. Unmerged, their *shape* is itself
information: three meetings stacked on one hour say something about how in demand someone is that a
single "busy" does not. Touching intervals are merged too — a seam between two back-to-back meetings
is a fact about your day that nobody asked for.

### One definition of busy

The blocks come from `scheduling.busy_for` — **the same function the booking page uses** to decide
which slots to offer. Not a copy of it.

This matters more than it looks. Building this feature is what exposed that the scheduler's notion of
busy did not include the host's own events: "Dentist, 14:00" in your GhostCal calendar did not stop a
stranger booking you at 14:00. The product held two contradictory answers to *"am I free?"*, and the
one facing strangers was the wrong one. That is fixed, and the fix is upstream of both callers, so it
cannot drift apart again.

## Consequences

- `busy_links` (organization, user, token hash, name). Revocation is deleting the row.
- The visitor has no account and no RLS context, so they get exactly one SECURITY DEFINER door —
  `busy_link_by_token` — and it resolves a token to **a person**, returning no times at all. The
  times are then read through the ordinary, RLS-scoped query the scheduler itself runs, which is how
  the single definition of "busy" is enforced by construction rather than by discipline.
- A window, not a lifetime: 14 days by default, 62 at most. The answer is "here is my next
  fortnight", not a map of someone's year.
- Read-only, obviously. There is nothing here to write to.
