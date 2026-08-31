/**
 * A password change must leave the account readable — measured by reading, not by a 204.
 *
 * The defect this pins was invisible to every test that existed. `rewrapAllForNewPassword` re-wrapped
 * the org keys and never `users.zk_wrapped_private_key`, so the change itself succeeded, every request
 * returned 204, and the account carried on working. The damage surfaced at the NEXT login, inside a
 * `catch` that swallowed it — and it was permanent, because the keypair is write-once and the envelope
 * on file could only ever be opened by the old password.
 *
 * So these tests call the real `rewrapAllForNewPassword`, intercept what it puts on the wire, and then
 * **replay those envelopes with the new password and decrypt an actual record**. A test that asserted
 * "the rotation resolved" would have passed against the broken version, which is precisely what the
 * suite did for months.
 *
 * Real Argon2id throughout, no crypto mocks: what is under test is whether the bytes still open.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { rewrapAllForNewPassword } from "@/lib/auth";
import {
  generateKeyMaterial,
  generateUserKeypair,
  openContent,
  openOrgKeyForMe,
  sealContent,
  sealOrgKeyToMember,
  storeUnlockedKey,
  storeUserKeys,
  unlockUserPrivateKey,
  unlockWithPassword,
} from "@/lib/zk";

const OLD_PW = "the-password-before-the-change";
const NEW_PW = "the-password-after-the-change";
const ORG_ID = "11111111-2222-4333-8444-555555555555";

type Sent = { path: string; body: Record<string, string> };

let sent: Sent[];
let realFetch: typeof globalThis.fetch;

beforeEach(() => {
  sent = [];
  realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    sent.push({
      path: String(url),
      body: JSON.parse(String(init?.body ?? "{}")) as Record<string, string>,
    });
    return new Response(null, { status: 204 });
  }) as typeof globalThis.fetch;
  sessionStorage.clear();
});

afterEach(() => {
  globalThis.fetch = realFetch;
  sessionStorage.clear();
});

/** An account as a browser holds it: its own keypair, plus an org key sealed TO that keypair. */
async function anAccountWithASealedOrgKey() {
  const keypair = await generateUserKeypair(OLD_PW);
  const userPrivate = await unlockUserPrivateKey(
    OLD_PW,
    keypair.wrapped_private_key,
    keypair.wrap_salt,
  );

  // A rotated organisation: the current generation reaches members by being sealed to their
  // keypair, not by being wrapped under their password. That is the generation a broken re-wrap
  // loses, and the reason "log in again" never brought it back.
  const org = await generateKeyMaterial(OLD_PW, "unused-recovery-phrase");
  const orgPrivate = await unlockWithPassword(
    OLD_PW,
    org.wrapped_private_key,
    org.wrap_salt,
  );

  storeUserKeys({ publicKey: keypair.public_key, privateKey: userPrivate });
  storeUnlockedKey(ORG_ID, {
    publicKey: org.public_key,
    privateKey: orgPrivate,
  });

  return {
    keypair,
    sealedOrgKey: await sealOrgKeyToMember(orgPrivate, keypair.public_key),
    record: await sealContent(
      { title: "Quarterly review", description: "", location: "" },
      org.public_key,
    ),
  };
}

function envelopeFor(path: string): Sent {
  const match = sent.find((s) => s.path.endsWith(path));
  expect(match, `nothing was sent to ${path}`).toBeDefined();
  return match as Sent;
}

describe("rewrapAllForNewPassword", () => {
  it("re-wraps the user keypair, so what is sealed to it still opens afterwards", async () => {
    const { sealedOrgKey, record } = await anAccountWithASealedOrgKey();

    await rewrapAllForNewPassword(NEW_PW);

    // Replay the envelope the browser actually sent, with only the new password — this is the
    // next login. Nothing here knows the old one.
    const put = envelopeFor("/v1/me/keypair/rewrap");
    const userPrivate = await unlockUserPrivateKey(
      NEW_PW,
      put.body.wrapped_private_key,
      put.body.wrap_salt,
    );
    const orgPrivate = await openOrgKeyForMe(sealedOrgKey, userPrivate);

    expect((await openContent(record, orgPrivate)).title).toBe(
      "Quarterly review",
    );
  });

  it("sends the public key it holds, and never asks for it to be changed", async () => {
    const { keypair } = await anAccountWithASealedOrgKey();

    await rewrapAllForNewPassword(NEW_PW);

    // The route matches on this rather than writing it. Sending a different one would mean the
    // browser is re-wrapping something other than what is stored, and the server refuses.
    expect(envelopeFor("/v1/me/keypair/rewrap").body.public_key).toBe(
      keypair.public_key,
    );
  });

  it("still re-wraps the org keys, which is all it used to do", async () => {
    const { record } = await anAccountWithASealedOrgKey();

    await rewrapAllForNewPassword(NEW_PW);

    const org = envelopeFor("/v1/auth/zk-rewrap");
    expect(org.body.organization_id).toBe(ORG_ID);
    const orgPrivate = await unlockWithPassword(
      NEW_PW,
      org.body.wrapped_private_key,
      org.body.wrap_salt,
    );
    expect((await openContent(record, orgPrivate)).title).toBe(
      "Quarterly review",
    );
  });
});
