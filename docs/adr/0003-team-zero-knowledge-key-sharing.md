# ADR-0003: Team zero-knowledge key sharing

- Status: Accepted
- Date: 2026-06-30

## Context

[ADR-0002](0002-zero-knowledge-invitee-data.md) made invitee data zero-knowledge: it is sealed to
an **organization** X25519 public key, and the org private key is wrapped per member under their
password (Argon2id). That ADR shipped the **solo** case only — the founder holds the wrapped key.

For a **team**, a newly invited member has no wrapped copy of the org private key, so they cannot
decrypt invitee answers. The server must never see the org private key, so it cannot wrap it for
them. An existing key-holder has to hand it over without the server learning it.

## Decision

**Carry the key in the invitation link fragment — the ghostbit model.** When an admin (whose
browser has the org private key unlocked) invites a member:

1. The browser generates a random **grant key** and seals the org private key under it
   (`wrapped_org_key = secretbox(org_sk, grant_key)`).
2. `wrapped_org_key` is stored on the `organization_invitations` row. The **grant key** is placed
   in the invitation link **fragment** (`/invitations/<token>#k=<grant_key>`) — the fragment is
   never sent to any server.
3. The admin shares that link with the invitee (the dashboard surfaces it to copy). The
   server-sent invitation email carries only the plain `/invitations/<token>` link, which grants
   membership but no decryption access.

When the invitee accepts:

4. They join the org (existing `accept_organization_invitation`), then their browser reads the
   `#k` fragment, fetches `wrapped_org_key`, recovers `org_sk = secretbox_open(wrapped_org_key,
   grant_key)`, re-wraps it under **their** password and stores it in `org_member_keys` via a
   membership-checked `store_member_org_key` helper. They can now decrypt invitee data for that org.

This reuses the existing invitation flow and the suite's signature "key in the URL fragment". No
per-user keypairs, no separate grant table.

## Consequences

- **The grant key travels by email** if the secure link is emailed — the same exposure as the
  invitation token itself, which already grants membership. The recommended UX surfaces the secure
  link for the admin to share over their own channel; the server email stays keyless. This is a
  deliberate, ghostbit-consistent tradeoff: convenience over the stronger (and much heavier)
  per-user-keypair scheme. An org can rotate its keypair to revoke leaked grants.
- **Granted access is re-grantable.** A member's granted key is wrapped under their password only
  (no recovery copy): if they forget their password, an admin simply re-invites/re-grants. So
  `org_member_keys.recovery_*` becomes nullable; the founder still keeps a recovery copy.
- **The admin must be unlocked to invite** with a key (the org private key must be in their tab
  session). Inviting without it still works but grants no decryption access.
- **Acceptance needs the invitee's password** once, to wrap the recovered key — prompted on the
  accept page. After that it unlocks normally on login.
- **Revocation of a removed member's access** is not retroactive: they may have cached `org_sk`.
  True revocation requires rotating the org keypair and re-sealing — out of scope here, noted for a
  future ADR.
