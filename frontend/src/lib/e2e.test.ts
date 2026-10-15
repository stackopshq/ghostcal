import { describe, expect, it } from "vitest";

import { decryptSymmetric, encryptSymmetric, fromB64, generateKeypair, openSealed, sealToPublicKey } from "@/lib/e2e";

// Envelopes this client wrote with WebCrypto before moving to the shared core (AES-256-GCM,
// 12-byte nonce, no `v`). Production accounts hold them: they must keep opening.
const PLAINTEXT = "Déjeuner avec Camille — 12:30";
// Test-only key for the vectors below, like PRIVATE_PKCS8; it protects nothing.
const SYM_KEY = "5E3SquTSlTahdmhKCCLIW1cyIr5Lzi0Ob8LTn17twk8="; // gitleaks:allow
const SYM_BLOB =
  '{"nonce":"bL8neOr/ZsrCOUgY","encrypted_target":"t/S8oeLyaj0u1S4yRLY3gYz2vbH8O71vj7wCHHU0jVDtbNIFkSt5P7yVdgCsTzcp"}';
// Throwaway key generated for these vectors only; it protects nothing.
const PRIVATE_PKCS8 = "MC4CAQAwBQYDK2VuBCIEICgZYk9PD9l9b63sJ4+ZuQlqD8SbUtRE2L4SoXut2wFy"; // gitleaks:allow
const SEAL_BLOB =
  '{"nonce":"S7zH0JfXlYxxIfYu","encrypted_target":"WB+N2vaTKcWIgMhnbnoYqo4U+CPBnyZ52lhqsUWAzeEHK/scb/HIjsRxD7Hp6CR9","epk":"mYFpBqLknLyvNHmzG7buBrJU6IKFxmw+cSTBXiTY7Bk="}';

const text = (b: Uint8Array) => new TextDecoder().decode(b);
const utf8 = (s: string) => new TextEncoder().encode(s);

describe("e2e on the shared core", () => {
  it("opens what the WebCrypto client wrote", async () => {
    expect(text(await decryptSymmetric(fromB64(SYM_KEY), SYM_BLOB))).toBe(PLAINTEXT);
    expect(text(await openSealed(PRIVATE_PKCS8, SEAL_BLOB))).toBe(PLAINTEXT);
  });

  it("writes versioned envelopes and reads them back", async () => {
    const key = fromB64(SYM_KEY);
    const blob = await encryptSymmetric(key, utf8("x"));
    expect(JSON.parse(blob).v).toBe(1);
    expect(text(await decryptSymmetric(key, blob))).toBe("x");

    const pair = await generateKeypair();
    const sealed = await sealToPublicKey(pair.publicKey, utf8("y"));
    expect(JSON.parse(sealed).v).toBe(1);
    expect(text(await openSealed(pair.privateKey, sealed))).toBe("y");
  });

  it("refuses a wrong key instead of returning garbage", async () => {
    await expect(decryptSymmetric(new Uint8Array(32), SYM_BLOB)).rejects.toThrow();
  });
});
