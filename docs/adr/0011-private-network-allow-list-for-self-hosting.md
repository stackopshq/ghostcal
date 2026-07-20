# ADR-0011 — Letting a self-hoster reach their own CalDAV server

Status: accepted
Date: 2026-07-20

## Context

The SSRF guard (`assert_public_url`) resolves every user-supplied URL before the server connects to
it, and refuses loopback, link-local, private, reserved, multicast and unspecified addresses. For a
hosted deployment that is exactly right: a booking form is a stranger-facing surface, and "add a
CalDAV calendar" is otherwise an invitation to make the server probe its own network.

It also makes GhostCal unusable for the people most likely to want it. GhostCal is self-hostable,
and a self-hoster's Nextcloud or Radicale lives at `192.168.1.x`. Under the blanket refusal they can
never connect their own calendar — the one calendar they certainly have the right to read. The
privacy-first product is the one that will not talk to your own machine.

This was left open deliberately rather than patched, because loosening a security control is a
decision, not a bug fix.

## Decision

**An opt-in allow-list of private networks, named by the operator, scoped to calendars.**

`GHOSTCAL_CALENDAR_ALLOWED_PRIVATE_CIDRS` takes a list of CIDRs, empty by default. An address
inside one of them passes the guard; everything else is refused exactly as before.

Three properties make this defensible rather than merely convenient:

1. **Empty by default.** A hosted deployment that never sets it is unchanged, byte for byte. The
   permissive configuration cannot be arrived at by accident — only by an operator writing down a
   range.
2. **Named ranges, not a boolean.** `ALLOW_PRIVATE_NETWORKS=true` would open `10/8`, `172.16/12`,
   `192.168/16` and loopback in one stroke — the whole internal network to reach one host on it. A
   CIDR opens what it covers and nothing more, so the blast radius is the operator's to choose and
   to see.
3. **Calendars only.** CalDAV connections and ICS subscriptions pass the allow-list; webhook
   targets do not. A webhook URL is settable by any org manager and is the more attacker-shaped
   surface of the two, so it keeps the strict guard whatever the operator configures.

**Link-local is never openable.** It is checked before the allow-list, so `169.254.169.254` — the
cloud-metadata endpoint, and the single highest-value SSRF target on any cloud host — stays refused
even if an operator explicitly lists `169.254.0.0/16`. Configuration validation rejects such an
entry at startup rather than ignoring it silently, so the refusal is visible rather than surprising.
Multicast, reserved and unspecified addresses are likewise never openable: no calendar server lives
there, so allowing them could only ever serve an attacker.

Loopback and the private ranges *are* openable, because the single-host self-hoster is a real user
and refusing them would push them to disable the guard wholesale — the worse outcome.

## Consequences

- A self-hoster sets one variable and connects their LAN calendar. Nothing else changes for them.
- An operator who lists a range on an internet-facing deployment has widened their own attack
  surface, and the `.env.example` comment says so plainly. This is a control we hand over
  deliberately, with its cost written next to it.
- The guard still resolves DNS and checks every returned address, so a hostname pointing into an
  allowed range works and one pointing outside it does not. The check remains time-of-check rather
  than time-of-use: it validates the resolved addresses, and does not pin them into the connection
  that follows. An allow-list widens what a DNS-rebinding window could reach, bounded by the ranges
  named. Closing that properly means pinning the resolved IP into the request, which is a change to
  every outbound client and belongs on its own.
- `assert_public_url` takes the allowed networks as an argument rather than reading configuration
  itself, so the guard stays a pure function and its tests need no environment.
