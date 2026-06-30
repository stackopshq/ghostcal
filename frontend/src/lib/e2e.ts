// Vendored end-to-end crypto core for the ghost suite — WebCrypto only, plus hash-wasm Argon2id
// for the password-derived mode. No heavyweight crypto dependency.
//
// Primitives:
//   - AES-256-GCM (12-byte nonce) for all symmetric encryption.
//   - X25519 ECDH → HKDF-SHA256 → AES-256-GCM for anonymous "seal to a public key" (ECIES),
//     so an invitee with no key can encrypt to an organization's public key.
//   - Argon2id (hash-wasm) to derive a 256-bit key from a password or recovery phrase.
//
// Encodings: raw keys travel base64url; ciphertext envelopes are base64 JSON
// ({ nonce, encrypted_target } for symmetric, plus { epk } for the ECDH seal).

import { argon2id } from "hash-wasm";

// WebCrypto wants ArrayBuffer-backed views (not SharedArrayBuffer) under TS strict DOM lib.
type Bytes = Uint8Array<ArrayBuffer>;

const NONCE_BYTES = 12;
const KEY_BYTES = 32;
const HKDF_INFO = new TextEncoder().encode("ghostcal-zk-v1");

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

function randomBytes(n: number): Bytes {
  return crypto.getRandomValues(new Uint8Array(n));
}

export function randomKey(): Bytes {
  return randomBytes(KEY_BYTES);
}

// --- AES-256-GCM ----------------------------------------------------------------------------

export type Envelope = { nonce: string; encrypted_target: string };

async function aesEncrypt(keyBytes: Bytes, plaintext: Bytes): Promise<Envelope> {
  const key = await crypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["encrypt"]);
  const nonce = randomBytes(NONCE_BYTES);
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, plaintext),
  );
  return { nonce: toB64(nonce), encrypted_target: toB64(ct) };
}

async function aesDecrypt(keyBytes: Bytes, env: Envelope): Promise<Bytes> {
  const key = await crypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["decrypt"]);
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: fromB64(env.nonce) },
    key,
    fromB64(env.encrypted_target),
  );
  return new Uint8Array(pt);
}

/** Encrypt bytes under a raw 256-bit key. Returns a base64 JSON envelope. */
export async function encryptSymmetric(keyBytes: Bytes, plaintext: Bytes): Promise<string> {
  return JSON.stringify(await aesEncrypt(keyBytes, plaintext));
}

export async function decryptSymmetric(keyBytes: Bytes, blob: string): Promise<Bytes> {
  return aesDecrypt(keyBytes, JSON.parse(blob) as Envelope);
}

// --- Argon2id (password / recovery-phrase derived key) --------------------------------------

export const ARGON2_SALT_BYTES = 16;

export async function deriveKey(passphrase: string, salt: Bytes): Promise<Bytes> {
  const hash = await argon2id({
    password: passphrase,
    salt,
    parallelism: 1,
    iterations: 3,
    memorySize: 65536, // 64 MiB
    hashLength: KEY_BYTES,
    outputType: "binary",
  });
  return new Uint8Array(hash);
}

// --- X25519 keypair + ECDH "seal to public key" (ECIES) -------------------------------------

export type SerializedKeypair = { publicKey: string; privateKey: string };

/** Generate an X25519 keypair. Public key is raw (32 bytes); private key is PKCS#8 — both base64. */
export async function generateKeypair(): Promise<SerializedKeypair> {
  const kp = (await crypto.subtle.generateKey({ name: "X25519" }, true, [
    "deriveBits",
  ])) as CryptoKeyPair;
  const pub = new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey));
  const priv = new Uint8Array(await crypto.subtle.exportKey("pkcs8", kp.privateKey));
  return { publicKey: toB64(pub), privateKey: toB64(priv) };
}

async function importPublic(rawB64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", fromB64(rawB64), { name: "X25519" }, false, []);
}

async function importPrivate(pkcs8B64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("pkcs8", fromB64(pkcs8B64), { name: "X25519" }, false, [
    "deriveBits",
  ]);
}

async function ecdhAesKey(privateKey: CryptoKey, publicKey: CryptoKey): Promise<Bytes> {
  const shared = await crypto.subtle.deriveBits({ name: "X25519", public: publicKey }, privateKey, 256);
  const hkdfKey = await crypto.subtle.importKey("raw", shared, "HKDF", false, ["deriveBits"]);
  const derived = await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: HKDF_INFO },
    hkdfKey,
    256,
  );
  return new Uint8Array(derived);
}

export type SealedEnvelope = Envelope & { epk: string };

/** Anonymous seal: encrypt to a recipient public key with a fresh ephemeral key (ECIES). */
export async function sealToPublicKey(
  recipientPublicB64: string,
  plaintext: Bytes,
): Promise<string> {
  const ephemeral = (await crypto.subtle.generateKey({ name: "X25519" }, true, [
    "deriveBits",
  ])) as CryptoKeyPair;
  const recipient = await importPublic(recipientPublicB64);
  const aesKey = await ecdhAesKey(ephemeral.privateKey, recipient);
  const env = await aesEncrypt(aesKey, plaintext);
  const epk = new Uint8Array(await crypto.subtle.exportKey("raw", ephemeral.publicKey));
  const sealed: SealedEnvelope = { ...env, epk: toB64(epk) };
  return JSON.stringify(sealed);
}

/** Open a sealed envelope with the recipient's private key. */
export async function openSealed(
  recipientPrivateB64: string,
  blob: string,
): Promise<Bytes> {
  const sealed = JSON.parse(blob) as SealedEnvelope;
  const recipientPriv = await importPrivate(recipientPrivateB64);
  const epk = await importPublic(sealed.epk);
  const aesKey = await ecdhAesKey(recipientPriv, epk);
  return aesDecrypt(aesKey, sealed);
}
