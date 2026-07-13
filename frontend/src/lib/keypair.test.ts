import { describe, expect, it } from "vitest";
import { membersWithoutKeys } from "@/lib/keypair";
import {
  generateUserKeypair,
  openOrgKeyForMe,
  sealOrgKeyToMember,
  unlockUserPrivateKey,
} from "@/lib/zk";
import { generateKeyMaterial, unlockWithPassword } from "@/lib/zk";

// Real crypto, not mocks: what is being checked is the one move the whole rotation design rests on —
// an admin can hand a member the org private key by sealing it to that member's public key, and the
// server, which sees only the ciphertext, learns nothing. See ADR-0007.

const ALICE_PW = "alice-password";
const BOB_PW = "bob-password";
const ORG_PW = "org-owner-password";
const RECOVERY = "aaaa-bbbb-cccc-dddd";

describe("per-user keypair", () => {
  it("round-trips: wrapped under the password, unwrapped with it, and not with another", async () => {
    const kp = await generateUserKeypair(ALICE_PW);

    const priv = await unlockUserPrivateKey(
      ALICE_PW,
      kp.wrapped_private_key,
      kp.wrap_salt,
    );
    expect(priv).toBeTruthy();

    // AES-GCM authenticates, so a wrong password fails loudly rather than returning garbage.
    await expect(
      unlockUserPrivateKey(
        "not-the-password",
        kp.wrapped_private_key,
        kp.wrap_salt,
      ),
    ).rejects.toThrow();
  });

  it("carries no recovery copy — a lost password means a re-grant, not a recovery", async () => {
    const kp = await generateUserKeypair(ALICE_PW);
    expect(kp.recovery_wrapped_private_key).toBe("");
    expect(kp.recovery_salt).toBe("");
  });
});

describe("sealing an org key to a member (the move a rotation is built on)", () => {
  it("lets the member open the org key, and nobody else", async () => {
    // The org's keypair, as an owner holds it.
    const org = await generateKeyMaterial(ORG_PW, RECOVERY);
    const orgPrivate = await unlockWithPassword(
      ORG_PW,
      org.wrapped_private_key,
      org.wrap_salt,
    );

    const alice = await generateUserKeypair(ALICE_PW);
    const bob = await generateUserKeypair(BOB_PW);

    // The admin seals the org private key to Alice's public key. This blob is what the server
    // stores; it can read neither the org key nor Alice's.
    const forAlice = await sealOrgKeyToMember(orgPrivate, alice.public_key);

    const alicePrivate = await unlockUserPrivateKey(
      ALICE_PW,
      alice.wrapped_private_key,
      alice.wrap_salt,
    );
    expect(await openOrgKeyForMe(forAlice, alicePrivate)).toBe(orgPrivate);

    // Bob holds a perfectly good keypair — and it opens nothing that was not sealed to him.
    const bobPrivate = await unlockUserPrivateKey(
      BOB_PW,
      bob.wrapped_private_key,
      bob.wrap_salt,
    );
    await expect(openOrgKeyForMe(forAlice, bobPrivate)).rejects.toThrow();
  });

  it("a rotated org key is a different key — that is the point of rotating", async () => {
    const before = await generateKeyMaterial(ORG_PW, RECOVERY);
    const after = await generateKeyMaterial(ORG_PW, RECOVERY);
    expect(after.public_key).not.toBe(before.public_key);
  });
});

describe("membersWithoutKeys", () => {
  it("names who a rotation would lock out rather than silently passing them by", () => {
    const members = [
      { user_id: "1", name: "Alice", email: "a@x.test", public_key: "pk" },
      { user_id: "2", name: "Bob", email: "b@x.test", public_key: null },
    ];
    expect(membersWithoutKeys(members).map((m) => m.name)).toEqual(["Bob"]);
  });
});
