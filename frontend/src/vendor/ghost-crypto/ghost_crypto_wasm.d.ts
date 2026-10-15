/* tslint:disable */
/* eslint-disable */

/**
 * An X25519 keypair: raw public key and PKCS#8 private key, both base64.
 */
export class Keypair {
    private constructor();
    free(): void;
    [Symbol.dispose](): void;
    readonly privateKey: string;
    readonly publicKey: string;
}

/**
 * Opens an envelope, current or legacy (version-less AES-GCM) format.
 */
export function decryptSymmetric(key: Uint8Array, blob: string): Uint8Array;

/**
 * Argon2id (64 MiB, 3 passes, 1 lane) from a passphrase and a 16-byte salt.
 */
export function deriveKey(passphrase: string, salt: Uint8Array): Uint8Array;

/**
 * Encrypts under a raw 256-bit key. Returns the versioned JSON envelope.
 */
export function encryptSymmetric(key: Uint8Array, plaintext: Uint8Array): string;

export function generateKeypair(): Keypair;

/**
 * Opens a seal, current or legacy format, with the recipient's PKCS#8 private key.
 */
export function openSealed(private_key: string, blob: string, domain: string): Uint8Array;

/**
 * Anonymous seal to a public key (ECIES: X25519 → HKDF(domain) → XChaCha20-Poly1305).
 */
export function sealToPublicKey(public_key: string, plaintext: Uint8Array, domain: string): string;

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
    readonly memory: WebAssembly.Memory;
    readonly __wbg_keypair_free: (a: number, b: number) => void;
    readonly decryptSymmetric: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly deriveKey: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly encryptSymmetric: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly generateKeypair: () => number;
    readonly keypair_privateKey: (a: number) => [number, number];
    readonly keypair_publicKey: (a: number) => [number, number];
    readonly openSealed: (a: number, b: number, c: number, d: number, e: number, f: number) => [number, number, number, number];
    readonly sealToPublicKey: (a: number, b: number, c: number, d: number, e: number, f: number) => [number, number, number, number];
    readonly __wbindgen_exn_store: (a: number) => void;
    readonly __externref_table_alloc: () => number;
    readonly __wbindgen_externrefs: WebAssembly.Table;
    readonly __wbindgen_malloc: (a: number, b: number) => number;
    readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
    readonly __externref_table_dealloc: (a: number) => void;
    readonly __wbindgen_free: (a: number, b: number, c: number) => void;
    readonly __wbindgen_start: () => void;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;

/**
 * Instantiates the given `module`, which can either be bytes or
 * a precompiled `WebAssembly.Module`.
 *
 * @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
 *
 * @returns {InitOutput}
 */
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
 * If `module_or_path` is {RequestInfo} or {URL}, makes a request and
 * for everything else, calls `WebAssembly.instantiate` directly.
 *
 * @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
 *
 * @returns {Promise<InitOutput>}
 */
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
