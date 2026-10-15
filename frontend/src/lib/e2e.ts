// End-to-end crypto for GhostCal: the suite's shared core (ghostsuite `ghost-crypto`) compiled
// to WebAssembly, behind the API this module has always exported (ADR-0001). No primitive is
// implemented here; this file only loads the module and converts encodings.
//
// What the core does:
//   - XChaCha20-Poly1305 (24-byte nonce) for symmetric encryption, envelopes versioned `v: 1`.
//   - X25519 ECDH → HKDF-SHA256 (info = GhostCal's domain) → XChaCha20-Poly1305 for the
//     anonymous "seal to a public key" (ECIES), so an invitee with no key can encrypt to an
//     organization's public key.
//   - Argon2id to derive a 256-bit key from a password or recovery phrase.
//   - It still OPENS the envelopes this client wrote before the move (AES-256-GCM, 12-byte nonce,
//     no `v`), so existing accounts keep working; it never writes them.
//
// Encodings: raw keys travel base64url; ciphertext envelopes are base64 JSON
// ({ v, nonce, encrypted_target } for symmetric, plus { epk } for the ECDH seal).

import init, * as core from "@/vendor/ghost-crypto/ghost_crypto_wasm";

// ArrayBuffer-backed views (not SharedArrayBuffer), the type the DOM lib expects for byte input.
type Bytes = Uint8Array<ArrayBuffer>;

const KEY_BYTES = 32;
/** HKDF domain separation: a GhostCal seal does not open as a GhostMail one. */
const DOMAIN = "ghostcal-zk-v1";

let loading: Promise<unknown> | null = null;

/** Loads the WebAssembly module once; every operation awaits it. */
function ready(): Promise<unknown> {
  loading ??= init().catch((e: unknown) => {
    loading = null; // let a later call retry (e.g. after a transient network failure)
    throw e;
  });
  return loading;
}

function bytes(out: Uint8Array): Bytes {
  return new Uint8Array(out);
}

// --- base64 / base64url ---------------------------------------------------------------------

export function toB64(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

export function fromB64(b64: string): Bytes {
  const s = atob(b64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export function toB64Url(bytes: Uint8Array): string {
  return toB64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromB64Url(b64url: string): Bytes {
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
  return fromB64(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
}

export function randomKey(): Bytes {
  return crypto.getRandomValues(new Uint8Array(KEY_BYTES));
}

// --- Symmetric -----------------------------------------------------------------------------

export type Envelope = { v?: number; nonce: string; encrypted_target: string };

/** Encrypt bytes under a raw 256-bit key. Returns a base64 JSON envelope. */
export async function encryptSymmetric(keyBytes: Bytes, plaintext: Bytes): Promise<string> {
  await ready();
  return core.encryptSymmetric(keyBytes, plaintext);
}

export async function decryptSymmetric(keyBytes: Bytes, blob: string): Promise<Bytes> {
  await ready();
  return bytes(core.decryptSymmetric(keyBytes, blob));
}

// --- Argon2id (password / recovery-phrase derived key) --------------------------------------

export const ARGON2_SALT_BYTES = 16;

export async function deriveKey(passphrase: string, salt: Bytes): Promise<Bytes> {
  await ready();
  return bytes(core.deriveKey(passphrase, salt));
}

// --- X25519 keypair + ECDH "seal to public key" (ECIES) -------------------------------------

export type SerializedKeypair = { publicKey: string; privateKey: string };

/** Generate an X25519 keypair. Public key is raw (32 bytes); private key is PKCS#8 — both base64. */
export async function generateKeypair(): Promise<SerializedKeypair> {
  await ready();
  const kp = core.generateKeypair();
  try {
    return { publicKey: kp.publicKey, privateKey: kp.privateKey };
  } finally {
    kp.free();
  }
}

export type SealedEnvelope = Envelope & { epk: string };

/** Anonymous seal: encrypt to a recipient public key with a fresh ephemeral key (ECIES). */
export async function sealToPublicKey(
  recipientPublicB64: string,
  plaintext: Bytes,
): Promise<string> {
  await ready();
  return core.sealToPublicKey(recipientPublicB64, plaintext, DOMAIN);
}

/** Open a sealed envelope with the recipient's private key. */
export async function openSealed(
  recipientPrivateB64: string,
  blob: string,
): Promise<Bytes> {
  await ready();
  return bytes(core.openSealed(recipientPrivateB64, blob, DOMAIN));
}
