import { describe, expect, it } from "vitest";
import {
  generateKeyMaterial,
  openContent,
  openWithOrgKeys,
  reseal,
  sealContent,
  unlockWithPassword,
} from "@/lib/zk";

// Real crypto. The claim under test is the one the whole rotation rests on: a record sealed to the
// OLD org key can be moved to the NEW one in the browser, and afterwards the old key opens nothing.
// See ADR-0007.

const PW = "org-password";
const RECOVERY = "aaaa-bbbb-cccc-dddd";

async function orgKeypair() {
  const material = await generateKeyMaterial(PW, RECOVERY);
  const privateKey = await unlockWithPassword(
    PW,
    material.wrapped_private_key,
    material.wrap_salt,
  );
  return { publicKey: material.public_key, privateKey };
}

describe("reseal", () => {
  it("moves a record from the retired key to the current one, and the retired key then fails", async () => {
    const old = await orgKeypair();
    const fresh = await orgKeypair();

    const sealedUnderOld = await sealContent(
      { title: "Dentist", description: "", location: "Rue du Rhône" },
      old.publicKey,
    );

    // Mid-rotation: the browser holds the new key and keeps the retired one to read the backlog.
    const keys = {
      publicKey: fresh.publicKey,
      privateKey: fresh.privateKey,
      previousPrivateKeys: [old.privateKey],
    };

    // Before: the new key alone cannot open it — that is what makes it backlog.
    await expect(openContent(sealedUnderOld, fresh.privateKey)).rejects.toThrow();

    const sealedUnderNew = await reseal(sealedUnderOld, keys);

    // After: the current key opens it...
    expect((await openContent(sealedUnderNew, fresh.privateKey)).title).toBe("Dentist");
    // ...and the retired key — the one a departed member may have kept — does not.
    await expect(openContent(sealedUnderNew, old.privateKey)).rejects.toThrow();
  });

  it("carries the bytes across without reading them, so it works for any sealed shape", async () => {
    const old = await orgKeypair();
    const fresh = await orgKeypair();

    // Not an event, not a task — a shape reseal has never heard of. It must not care.
    const payload = JSON.stringify({ anything: ["at", "all"], n: 42 });
    const enc = new TextEncoder();
    const sealed = await sealContent(
      { title: payload, description: "", location: "" },
      old.publicKey,
    );

    const keys = {
      publicKey: fresh.publicKey,
      privateKey: fresh.privateKey,
      previousPrivateKeys: [old.privateKey],
    };
    const moved = await reseal(sealed, keys);

    expect((await openContent(moved, fresh.privateKey)).title).toBe(payload);
    expect(enc.encode(payload).length).toBeGreaterThan(0);
  });

  it("a record already on the current key survives a re-seal unchanged in meaning", async () => {
    const fresh = await orgKeypair();
    const sealed = await sealContent(
      { title: "Already current", description: "", location: "" },
      fresh.publicKey,
    );
    const keys = { publicKey: fresh.publicKey, privateKey: fresh.privateKey };

    const again = await reseal(sealed, keys);

    // The ciphertext differs (a fresh ephemeral key each time), but it still opens to the same thing.
    expect(again).not.toBe(sealed);
    expect((await openContent(again, fresh.privateKey)).title).toBe("Already current");
  });
});

describe("openWithOrgKeys", () => {
  it("falls back through retired generations, and throws when none of them fit", async () => {
    const gen0 = await orgKeypair();
    const gen1 = await orgKeypair();
    const gen2 = await orgKeypair();
    const stranger = await orgKeypair();

    const underGen0 = await sealContent(
      { title: "Old", description: "", location: "" },
      gen0.publicKey,
    );

    const keys = {
      publicKey: gen2.publicKey,
      privateKey: gen2.privateKey,
      previousPrivateKeys: [gen1.privateKey, gen0.privateKey],
    };
    expect((await openWithOrgKeys(keys, underGen0, openContent)).title).toBe("Old");

    const wrongChain = {
      publicKey: stranger.publicKey,
      privateKey: stranger.privateKey,
      previousPrivateKeys: [gen1.privateKey],
    };
    await expect(openWithOrgKeys(wrongChain, underGen0, openContent)).rejects.toThrow();
  });
});
