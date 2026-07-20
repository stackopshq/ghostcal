# ADR-0007 — Org key rotation and revocation (per-user keypairs)

Status: accepted
Date: 2026-07-13

Supersedes the key-distribution decision of [ADR-0003](0003-team-zero-knowledge-key-sharing.md),
which explicitly deferred this: *"True revocation requires rotating the org keypair and re-sealing —
out of scope here, noted for a future ADR."*

## Context

Today, removing a member from an organization **revokes nothing**. Their org private key reached
them through an invitation-link fragment (ADR-0003); their browser unwrapped it and re-wrapped it
under their password. Nothing stops them from having kept a copy.

Worse than the obvious: the organization's **public key does not change** when they leave, so every
booking, event and task created *after their departure* is still sealed to a key they hold. This is
not merely a failure to erase the past — it is an ongoing leak of the future.

Rotating the org keypair fixes that, and immediately raises the question ADR-0003 dodged: **the
remaining members have to obtain the new private key.** The server can never see it, and we do not
have their passwords, so it cannot wrap it for them.

## Decision

### 1. Every user gets their own keypair

Each user gains an X25519 keypair: the public key is stored in the clear (the server may read it —
that is what public keys are for), and the private key is wrapped under a key derived from their
password (Argon2id), exactly as the org key already is.

This is the scheme ADR-0003 rejected as *"much heavier"*. That judgement was right for its problem
and wrong for this one. With per-user keypairs, an admin rotating the org key can **seal the new org
private key directly to each remaining member's public key**. Members do nothing. They log in, their
browser unwraps their own private key with their password, opens the sealed org key, and carries on.

The alternative — one re-grant link per member, distributed out of band — makes a rotation so
laborious that it would never actually be performed. **A revocation nobody executes is not a
revocation.** The heavier scheme is the one that gets used, which makes it the lighter one.

It also removes the weakness ADR-0003 admitted in writing: for a member who already has an account,
the org key no longer needs to travel in a URL fragment that may end up in an email.

Existing users have no keypair. One is generated **at their next login**, which is the only moment
their password is in the browser. Until then they simply have no keypair, and an org cannot rotate
past them (see §4).

### 2. Rotation is not atomic, and must not try to be

The instinct is to re-seal everything inside one transaction. That is the wrong shape, and unpicking
why is what makes the rest simple:

- Flipping the org **public key** protects every record created from that moment on. That is the
  urgent half, and it is a single UPDATE.
- The **backlog** of already-sealed rows is *already* readable by the departed member. Re-sealing it
  does not restore a secret they never lost — it only narrows what they can still read later. That
  is worth doing, but it is not urgent, and it can take as long as it takes.

So: flip the public key first, then re-seal the backlog progressively, in the rotating admin's
browser — the only place both keys exist. A rotation interrupted halfway leaves the organization in
a sound state, not a broken one.

### 3. Old keys are kept, and a blob is opened by trying keys in turn

Members keep their wrapped copy of **every** past org key, so they can still read rows that have not
been re-sealed yet. A key generation is retired only when nothing is sealed to it any more.

Sealed blobs carry no key identifier (`{epk, iv, ct}` — see `frontend/src/lib/e2e.ts`), and we are
not adding one: AES-GCM authenticates, so opening with the wrong key *fails loudly* rather than
returning garbage. The browser therefore tries the current key, then falls back through the older
generations. Wrong keys cost a failed decryption, not a wrong answer.

Keeping the old private key available is not a hole. The departed member already has it; retaining
it for the remaining members grants nobody anything new.

### 4. An organization cannot rotate past a member who has no keypair

If a remaining member has never logged in since per-user keypairs shipped, the rotator has no public
key to seal the new org key to. Rotation is refused, naming them, rather than silently locking them
out of their own organization's data. They log in once, and the rotation proceeds.

### 5. What invitations still do

> **Corrected 2026-07-20.** This section previously claimed that inviting someone who already has an
> account seals the org key to their user public key, "no fragment, no key in a link", and that only
> brand-new invitees fell back to ADR-0003. **That branch was never built.** The paragraph described
> an intention as though it were behaviour, which in a document about key handling is worse than
> describing no behaviour at all. What follows is what the code does.

**Every invitation uses the ADR-0003 fragment grant**, whether or not the invitee already has an
account. The inviter's browser wraps the org key under a random grant key, the wrapped copy goes on
the invitation row, and the grant key travels in the URL fragment — so an invitation link emailed to
someone carries, in that email, the means to open the organization's data. There is one code path
and no conditional: `organization_invitations` has no column for a key sealed to a user, and there
is no endpoint that looks up a public key by email.

Rotation, by contrast, does seal to member public keys (§2). `sealOrgKeyToMember` exists and is
correct; invitations simply never call it.

Two things stand between here and an invitation that carries no key:

- **The invitee has no keypair when they register.** It is generated at *first login*, not at
  registration, so a freshly registered invitee still has `users.zk_public_key IS NULL` and there is
  nothing to seal to.
- **Only a member holding the org key unlocked can seal it.** The server cannot, by construction.
  So the grant cannot happen at the moment the invitee arrives; someone who already holds the key
  must perform a second, later step, and the invitee waits in a "pending access" state until they
  do.

That is a change to the invitation UX on both sides, and it needs its own ADR rather than a
paragraph here.

## Consequences

- `users` gains `zk_public_key`, `zk_wrapped_private_key`, `zk_wrap_salt` — all nullable, since
  existing accounts have none until their next login.
- `org_member_keys` gains a **generation**, so a member can hold several org keys at once. With
  per-user keypairs the org key no longer needs password-wrapping there at all: it is simply
  **sealed to the member's public key**, which is one mechanism instead of two.
- Rotation is an admin action, performed in a browser that holds the current org key unlocked.
- Re-sealing walks `bookings.invitee_private`, `calendar_events.content` and `tasks.content` — the
  three sealed columns — in batches, with progress, and is resumable.
- A user who forgets their password loses their own private key, and with it the sealed copies of
  the org keys. They are re-granted, exactly as ADR-0003 already provides for. The founder's
  recovery copy of the org key is unaffected.
- The server still never sees an org private key, a user private key, or any password-derived key.
  Rotation changes who can decrypt; it does not change who the server can decrypt for, which remains
  nobody.
