// Zero-knowledge crypto for GhostCal (libsodium).
//
// The org has an X25519 keypair. Invitees seal their private details (name, answers, notes) to the
// org PUBLIC key with an anonymous sealed box — they need no key of their own. Only the holder of
// the org PRIVATE key (a host, in their browser) can open them; the server only ever stores
// ciphertext. The private key is wrapped (secretbox) under a key derived from the host's password
// via Argon2id, and a second time under a one-time recovery phrase. See docs/adr/0002.

// The "sumo" build is required: the standard libsodium-wrappers omits crypto_pwhash (Argon2id).
import _sodium from "libsodium-wrappers-sumo";

let ready: Promise<typeof _sodium> | null = null;

async function sodium(): Promise<typeof _sodium> {
  if (!ready) {
    ready = _sodium.ready.then(() => _sodium);
  }
  return ready;
}

const B64 = 1; // sodium.base64_variants.ORIGINAL (avoids loading sodium just for the enum)

export type WrappedKey = { wrapped_private_key: string; salt: string };

export type ZkKeyMaterial = {
  public_key: string;
  wrapped_private_key: string;
  wrap_salt: string;
  recovery_wrapped_private_key: string;
  recovery_salt: string;
};

/** The cleartext the invitee seals — everything the server must never read. */
export type InviteePrivate = {
  name: string;
  answers: Record<string, string>;
  notes: string;
};

async function deriveKey(s: typeof _sodium, passphrase: string, salt: Uint8Array): Promise<Uint8Array> {
  return s.crypto_pwhash(
    s.crypto_secretbox_KEYBYTES,
    passphrase,
    salt,
    s.crypto_pwhash_OPSLIMIT_INTERACTIVE,
    s.crypto_pwhash_MEMLIMIT_INTERACTIVE,
    s.crypto_pwhash_ALG_ARGON2ID13,
  );
}

async function wrap(s: typeof _sodium, privateKey: Uint8Array, passphrase: string): Promise<WrappedKey> {
  const salt = s.randombytes_buf(s.crypto_pwhash_SALTBYTES);
  const key = await deriveKey(s, passphrase, salt);
  const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
  const cipher = s.crypto_secretbox_easy(privateKey, nonce, key);
  // Store nonce || ciphertext so unwrap is self-contained.
  const blob = new Uint8Array(nonce.length + cipher.length);
  blob.set(nonce);
  blob.set(cipher, nonce.length);
  return { wrapped_private_key: s.to_base64(blob, B64), salt: s.to_base64(salt, B64) };
}

async function unwrap(
  s: typeof _sodium,
  wrappedB64: string,
  saltB64: string,
  passphrase: string,
): Promise<Uint8Array> {
  const key = await deriveKey(s, passphrase, s.from_base64(saltB64, B64));
  const blob = s.from_base64(wrappedB64, B64);
  const nonce = blob.slice(0, s.crypto_secretbox_NONCEBYTES);
  const cipher = blob.slice(s.crypto_secretbox_NONCEBYTES);
  return s.crypto_secretbox_open_easy(cipher, nonce, key); // throws if the passphrase is wrong
}

/** A high-entropy recovery phrase shown once at sign-up (24 random bytes, grouped for legibility). */
export async function generateRecoveryPhrase(): Promise<string> {
  const s = await sodium();
  const raw = s.to_base64(s.randombytes_buf(24), B64);
  return (raw.match(/.{1,4}/g) ?? [raw]).join("-");
}

/** Generate a fresh org keypair and wrap the private key under the password and the recovery phrase. */
export async function generateKeyMaterial(password: string, recoveryPhrase: string): Promise<ZkKeyMaterial> {
  const s = await sodium();
  const kp = s.crypto_box_keypair();
  const byPassword = await wrap(s, kp.privateKey, password);
  const byRecovery = await wrap(s, kp.privateKey, recoveryPhrase);
  return {
    public_key: s.to_base64(kp.publicKey, B64),
    wrapped_private_key: byPassword.wrapped_private_key,
    wrap_salt: byPassword.salt,
    recovery_wrapped_private_key: byRecovery.wrapped_private_key,
    recovery_salt: byRecovery.salt,
  };
}

/** Unwrap the private key with the password (login) — returns it base64, or throws on a bad password. */
export async function unlockWithPassword(
  password: string,
  wrappedB64: string,
  saltB64: string,
): Promise<string> {
  const s = await sodium();
  return s.to_base64(await unwrap(s, wrappedB64, saltB64, password), B64);
}

/** Unwrap with the recovery phrase (password reset) — returns the private key base64. */
export async function unlockWithRecovery(
  recoveryPhrase: string,
  wrappedB64: string,
  saltB64: string,
): Promise<string> {
  const s = await sodium();
  return s.to_base64(await unwrap(s, wrappedB64, saltB64, recoveryPhrase.trim()), B64);
}

/** Re-wrap a known private key under a new password (after a password change/reset). */
export async function rewrapForPassword(privateKeyB64: string, newPassword: string): Promise<WrappedKey> {
  const s = await sodium();
  return wrap(s, s.from_base64(privateKeyB64, B64), newPassword);
}

// --- Unlocked-key session store ----------------------------------------------------------------
// The unwrapped org keypair lives in sessionStorage: per-tab, cleared on tab close, never written
// to disk. It is recovered for the tab's lifetime so the dashboard can decrypt without re-prompting.

const SK_KEY = "gc_zk_sk";
const PK_KEY = "gc_zk_pk";

export type UnlockedKeys = { publicKey: string; privateKey: string };

export function storeUnlockedKeys(keys: UnlockedKeys): void {
  sessionStorage.setItem(PK_KEY, keys.publicKey);
  sessionStorage.setItem(SK_KEY, keys.privateKey);
}

export function getUnlockedKeys(): UnlockedKeys | null {
  if (typeof window === "undefined") return null;
  const publicKey = sessionStorage.getItem(PK_KEY);
  const privateKey = sessionStorage.getItem(SK_KEY);
  return publicKey && privateKey ? { publicKey, privateKey } : null;
}

export function clearUnlockedKeys(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(PK_KEY);
  sessionStorage.removeItem(SK_KEY);
}

/** Seal the invitee's private details to the org public key (booking page). Returns base64. */
export async function sealInviteePrivate(data: InviteePrivate, orgPublicKeyB64: string): Promise<string> {
  const s = await sodium();
  const message = s.from_string(JSON.stringify(data));
  return s.to_base64(s.crypto_box_seal(message, s.from_base64(orgPublicKeyB64, B64)), B64);
}

/** Open a sealed invitee blob with the org keypair (host dashboard). */
export async function openInviteePrivate(
  blobB64: string,
  orgPublicKeyB64: string,
  orgPrivateKeyB64: string,
): Promise<InviteePrivate> {
  const s = await sodium();
  const opened = s.crypto_box_seal_open(
    s.from_base64(blobB64, B64),
    s.from_base64(orgPublicKeyB64, B64),
    s.from_base64(orgPrivateKeyB64, B64),
  );
  return JSON.parse(s.to_string(opened)) as InviteePrivate;
}
