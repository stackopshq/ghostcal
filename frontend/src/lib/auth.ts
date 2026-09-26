// Client-side auth: token storage + bearer requests with refresh-on-401.
//
// Tokens live in localStorage. Note (matches the backend decision): the refresh token is held
// client-side because the dev setup is cross-origin http; production should move it to an
// httpOnly cookie behind a same-origin proxy.

import { ApiError, resolveBaseUrl } from "@/lib/api";
import {
  clearUnlockedKeys,
  generateKeyMaterial,
  generateUserKeypair,
  generateRecoveryPhrase,
  listUnlockedKeys,
  rewrapForPassword,
  getUserKeys,
  openOrgKeyForMe,
  storeUnlockedKey,
  storeUserKeys,
  unlockUserPrivateKey,
  unlockWithPassword,
  type ZkKeyMaterial,
} from "@/lib/zk";

const ACCESS_KEY = "gc_access";
const REFRESH_KEY = "gc_refresh";
const ORG_KEY = "gc_org";

export function getActiveOrg(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ORG_KEY);
}

export function setActiveOrg(orgId: string | null): void {
  if (orgId) localStorage.setItem(ORG_KEY, orgId);
  else localStorage.removeItem(ORG_KEY);
}

export type User = {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
  // False for an SSO-only account: it has no password, so deletion is confirmed by the email alone.
  has_password: boolean;
};

type Tokens = { access_token: string; refresh_token: string };

function base(): string {
  return resolveBaseUrl();
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

function setTokens(tokens: Tokens): void {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(ORG_KEY);
}

export function isAuthenticated(): boolean {
  return getAccessToken() !== null;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail || res.statusText);
  }
  // 204 responses have no body.
  return (res.status === 204 ? undefined : await res.json()) as T;
}

// Sign-up generates the org keypair in the browser. The private key is wrapped under the password
// and under a one-time recovery phrase (shown to the user); the server only ever receives the
// public key and the wrapped blobs. Returns the recovery phrase so the page can display it once.
export async function register(
  email: string,
  name: string,
  password: string,
): Promise<{ user_id: string; recovery_phrase: string }> {
  const recoveryPhrase = await generateRecoveryPhrase();
  const zk_keys: ZkKeyMaterial = await generateKeyMaterial(
    password,
    recoveryPhrase,
  );
  const { user_id } = await post<{ user_id: string }>("/v1/auth/register", {
    email,
    name,
    password,
    zk_keys,
  });
  return { user_id, recovery_phrase: recoveryPhrase };
}

export type ZkKeysOut = {
  organization_id: string;
  /** The org's CURRENT public key, whatever generation this row is. */
  public_key: string;
  generation: number;
  /** Generation >= 1: the org key sealed to the user's own public key (ADR-0007). */
  sealed_org_key: string | null;
  /** Generation 0: wrapped under a key derived from the user's password. */
  wrapped_private_key: string | null;
  wrap_salt: string | null;
};

export function getZkKeys(): Promise<ZkKeysOut[]> {
  return authedFetch<ZkKeysOut[]>("/v1/auth/zk-keys");
}

// Unwrap every org private key with the given secret (login password, or an SSO user's encryption
// passphrase — same wrap) and stash them (keyed by org) in the per-tab session store, so the
// dashboard can decrypt the active org's content. Returns how many of the user's org keys unlocked,
// so a caller (the unlock screen) can tell a wrong passphrase from an empty vault.
export async function unlockZkKeys(
  secret: string,
): Promise<{ total: number; unlocked: number }> {
  // The user's own private key has to exist first: from generation 1 on, an org key reaches a member
  // sealed to it, and without it those generations simply cannot be opened.
  await ensureUserKeypair(secret);
  const userKeys = getUserKeys();

  const rows = await getZkKeys();
  const byOrg = new Map<string, ZkKeysOut[]>();
  for (const row of rows) {
    byOrg.set(row.organization_id, [
      ...(byOrg.get(row.organization_id) ?? []),
      row,
    ]);
  }

  let unlocked = 0;
  for (const [organizationId, generations] of byOrg) {
    // Newest generation first — that is the one everything new is sealed under, and the one the
    // fallback chain starts from.
    const ordered = [...generations].sort(
      (a, b) => b.generation - a.generation,
    );
    const privateKeys: string[] = [];

    for (const row of ordered) {
      try {
        if (row.sealed_org_key) {
          if (!userKeys) continue; // no user key in this tab: this generation stays shut
          privateKeys.push(
            await openOrgKeyForMe(row.sealed_org_key, userKeys.privateKey),
          );
        } else if (row.wrapped_private_key && row.wrap_salt) {
          privateKeys.push(
            await unlockWithPassword(
              secret,
              row.wrapped_private_key,
              row.wrap_salt,
            ),
          );
        }
      } catch {
        /* a generation this secret or key cannot open (e.g. a granted key); skip it */
      }
    }

    if (privateKeys.length > 0) {
      storeUnlockedKey(organizationId, {
        publicKey: ordered[0].public_key,
        privateKey: privateKeys[0],
        previousPrivateKeys: privateKeys.slice(1),
      });
      unlocked += 1;
    }
  }
  return { total: byOrg.size, unlocked };
}

// --- The user's own keypair (ADR-0007) ---------------------------------------------------------
//
// Distinct from the ORG keypair: an org key can be sealed TO this one, which is what lets an admin
// rotate an org keypair without any member lifting a finger. It can only be created while the
// password is in the browser, so login is the moment — hence its home here rather than in
// lib/keypair.ts, which keeps the rotation-facing half.

export type UserKeypair = {
  public_key: string;
  wrapped_private_key: string;
  wrap_salt: string;
};

export function getKeypair(): Promise<UserKeypair | null> {
  return authedFetch<UserKeypair | null>("/v1/me/keypair");
}

export function putKeypair(keypair: UserKeypair): Promise<void> {
  return authedFetch<void>("/v1/me/keypair", {
    method: "PUT",
    body: JSON.stringify(keypair),
  });
}

// Make sure the account has a keypair, and stash it unlocked for this tab. Best-effort by design:
// failing here must never keep someone out of their account.
//
// It is best-effort about GENERATING one, not about opening one that exists. Those two failures
// look identical from here and are not: a keypair that will not open is an account that has
// silently lost every org key sealed to it, and no later login repairs that — the envelope on file
// stays wrapped under whatever secret made it. Until 2026-08-31 this comment claimed "their next
// login fixes it", which was false, and it was the only place the behaviour was written down.
//
// The cause was a password change that re-wrapped the org keys and not this one; that is fixed in
// `rewrapAllForNewPassword`. The catch below now distinguishes the two cases rather than treating
// an unopenable keypair as routine.
export async function ensureUserKeypair(secret: string): Promise<void> {
  try {
    let keypair = await getKeypair();

    if (keypair === null) {
      const generated = await generateUserKeypair(secret);
      keypair = {
        public_key: generated.public_key,
        wrapped_private_key: generated.wrapped_private_key,
        wrap_salt: generated.wrap_salt,
      };
      try {
        await putKeypair(keypair);
      } catch {
        // 409: another tab published one first. Theirs won — take it, or we would sit on a private
        // key that nothing will ever be sealed to.
        keypair = await getKeypair();
        if (keypair === null) return;
      }
    }

    storeUserKeys({
      publicKey: keypair.public_key,
      privateKey: await unlockUserPrivateKey(
        secret,
        keypair.wrapped_private_key,
        keypair.wrap_salt,
      ),
    });
  } catch (err) {
    // Something IS broken when a stored keypair will not open, and saying so is the only way it
    // ever gets noticed: the interface degrades quietly and the user reads it as an empty account.
    // Not thrown — a login must not fail on this — but not silent either.
    console.warn(
      "ghostcal: the stored keypair did not open with this secret. Org key generations sealed " +
        "to it will stay locked in this browser.",
      err,
    );
  }
}

// Best-effort unlock used by password login — a failure here never blocks login.
async function unlockZk(password: string): Promise<void> {
  try {
    await unlockZkKeys(password);
  } catch {
    /* leave locked; the dashboard will offer to unlock */
  }
}

/** Whether the user already has zero-knowledge keys (i.e. has set an encryption passphrase). */
export async function hasZkKeys(): Promise<boolean> {
  return (await getZkKeys()).length > 0;
}

export function verifyEmail(token: string): Promise<void> {
  return post("/v1/auth/verify-email", { token });
}

/**
 * @param totpCode  le code du second facteur, ou un code de récupération.
 *
 * Il est facultatif parce que le premier appel se fait sans : c'est le serveur qui réclame,
 * par un 401 portant `mfa_required`. Cet argument n'existait pas, et la conséquence était
 * qu'un compte à second facteur activé ne pouvait plus se connecter au web du tout.
 */
export async function login(email: string, password: string, totpCode?: string): Promise<void> {
  const corps: Record<string, string> = { email, password };
  const code = totpCode?.trim();
  // Un champ vide n'est pas « pas de code » : le serveur le validerait comme une saisie.
  if (code) corps.totp_code = code;
  const tokens = await post<Tokens>("/v1/auth/login", corps);
  setTokens(tokens);
  await unlockZk(password);
}

// ─── Le second facteur, côté réglages ───
//
// Les cinq routes existaient, testées et déployées, sans un seul appelant côté interface.

export type EtatDuSecondFacteur = {
  enabled: boolean;
  pending: boolean;
  recovery_codes_remaining: number;
};

export function lireLeSecondFacteur(): Promise<EtatDuSecondFacteur> {
  return authedFetch<EtatDuSecondFacteur>("/v1/auth/mfa");
}

/** Démarre l'enrôlement. Le mot de passe est redemandé : voir le commentaire de la route. */
export function demarrerLeSecondFacteur(
  password: string,
): Promise<{ secret: string; otpauth_uri: string }> {
  return authedFetch("/v1/auth/mfa/setup", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

/** Active contre un premier code, et rend les codes de récupération — une seule fois. */
export function activerLeSecondFacteur(code: string): Promise<{ recovery_codes: string[] }> {
  return authedFetch("/v1/auth/mfa/activate", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function desactiverLeSecondFacteur(password: string, code: string): Promise<void> {
  return authedFetch("/v1/auth/mfa/disable", {
    method: "POST",
    body: JSON.stringify({ password, code }),
  });
}

export function refaireLesCodesDeRecuperation(
  password: string,
  code: string,
): Promise<{ recovery_codes: string[] }> {
  return authedFetch("/v1/auth/mfa/recovery-codes", {
    method: "POST",
    body: JSON.stringify({ password, code }),
  });
}

// --- SSO / OIDC ---------------------------------------------------------------------------------

export type AuthConfig = {
  oidc_enabled: boolean;
  /** Sibling GhostMail, or null/absent when this deployment has none. */
  ghostmail_url?: string | null;
  /** Where "Privacy policy" points. Per-deployment: see the server-side comment. */
  privacy_url?: string | null;
};

export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${base()}/v1/auth/config`, { cache: "no-store" });
  if (!res.ok) {
    // The fallback is deliberate — a login page without its SSO button beats a login page that does
    // not render. But it makes an unreachable API indistinguishable from an instance where OIDC is
    // genuinely off, which is precisely how a broken proxy hid on 2026-08-13: the button was simply
    // absent, and nothing anywhere said why. Hence the trace.
    console.error(`auth config unavailable: HTTP ${res.status} — the SSO button will be hidden`);
    return { oidc_enabled: false };
  }
  return (await res.json()) as AuthConfig;
}

/** Send the browser to the backend OIDC start route, which 302s to the identity provider. */
export function beginOidcLogin(): void {
  window.location.assign(`${base()}/v1/auth/oidc/login`);
}

// The OIDC callback lands on /auth/callback with the session tokens in the URL *fragment* (never
// sent to a server). Read them into storage and strip the fragment from the address bar/history.
export function completeOidcSession(): boolean {
  if (typeof window === "undefined") return false;
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return false;
  const params = new URLSearchParams(hash);
  const access = params.get("access_token");
  const refresh = params.get("refresh_token");
  if (!access || !refresh) return false;
  setTokens({ access_token: access, refresh_token: refresh });
  history.replaceState(null, "", window.location.pathname);
  return true;
}

// First-time SSO users have no zero-knowledge keys: they choose an encryption passphrase (separate
// from SSO — the server never sees it), which wraps a fresh org keypair. Returns the one-time
// recovery phrase to show once. The keys are unlocked into this tab immediately.
export async function setupEncryptionPassphrase(
  passphrase: string,
): Promise<string> {
  const recoveryPhrase = await generateRecoveryPhrase();
  const zk_keys: ZkKeyMaterial = await generateKeyMaterial(
    passphrase,
    recoveryPhrase,
  );
  await authedFetch<void>("/v1/auth/zk-keys", {
    method: "POST",
    body: JSON.stringify(zk_keys),
  });
  await unlockZkKeys(passphrase);
  return recoveryPhrase;
}

/**
 * Re-wrap everything this browser holds under a new password. Call after a successful change.
 *
 * "Everything" means the user's own keypair as well as the org keys. Until 2026-08-31 it meant
 * only the org keys, and the omission was permanent rather than inconvenient: the keypair is
 * write-once, so an envelope left sealed under the old password could never be re-sealed. The
 * account kept working, `ensureUserKeypair` swallowed the failure at the next login, and every
 * org key generation sealed to that keypair stayed shut — for good.
 *
 * The keypair goes first, deliberately. If an org key fails to re-wrap it can be re-granted by an
 * admin, which ADR-0003 already provides for; a keypair that fails cannot be recovered by anyone,
 * because nothing but the old password could ever open the envelope on file.
 */
export async function rewrapAllForNewPassword(
  newPassword: string,
): Promise<void> {
  const userKeys = getUserKeys();
  if (userKeys) {
    const wrapped = await rewrapForPassword(userKeys.privateKey, newPassword);
    // Not `PUT /keypair`, which is write-once: this route matches the public key instead of
    // writing it, so the same keypair gets a new envelope and nothing sealed to it is stranded.
    await authedFetch<void>("/v1/me/keypair/rewrap", {
      method: "POST",
      body: JSON.stringify({
        public_key: userKeys.publicKey,
        wrapped_private_key: wrapped.wrapped_private_key,
        wrap_salt: wrapped.salt,
      }),
    });
    // This tab keeps the same unwrapped key — re-wrapping changes the envelope, not the keypair.
  }

  for (const { organizationId, keys } of listUnlockedKeys()) {
    const wrapped = await rewrapForPassword(keys.privateKey, newPassword);
    await authedFetch<void>("/v1/auth/zk-rewrap", {
      method: "POST",
      body: JSON.stringify({
        organization_id: organizationId,
        wrapped_private_key: wrapped.wrapped_private_key,
        wrap_salt: wrapped.salt,
      }),
    });
  }
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  clearTokens();
  clearUnlockedKeys();
  if (refresh) {
    await post("/v1/auth/logout", { refresh_token: refresh }).catch(
      () => undefined,
    );
  }
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const tokens = await post<Tokens>("/v1/auth/refresh", {
      refresh_token: refresh,
    });
    setTokens(tokens);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

/** Exécute la requête authentifiée et rend la réponse BRUTE.
 *
 * Séparé de `authedFetch` parce que tout ce que sert l'API n'est pas du JSON : une image
 * téléversée arrive en octets. Le rafraîchissement du jeton sur 401 vit ici, une seule
 * fois, plutôt que recopié par chaque appelant qui veut autre chose que du JSON.
 */
export async function authedRequest(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const org = getActiveOrg();

  // Un corps `FormData` ne doit PAS porter de `Content-Type` posé à la main.
  //
  // Le navigateur en écrit un qui contient la **frontière** séparant les parties —
  // `multipart/form-data; boundary=----WebKitFormBoundary…` — et il ne le fait que si on
  // ne lui en impose pas un. Forcer `application/json` ici enverrait donc un corps
  // multipart annoncé comme du JSON, sans frontière : le serveur ne saurait pas où
  // commence le fichier, et rendrait une erreur qui ne parlerait pas de ça.
  const multipart = init?.body instanceof FormData;

  const run = async (): Promise<Response> =>
    fetch(`${base()}${path}`, {
      ...init,
      headers: {
        ...(multipart ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
        Authorization: `Bearer ${getAccessToken() ?? ""}`,
        ...(org ? { "X-Organization-Id": org } : {}),
      },
      cache: "no-store",
    });

  let res = await run();
  if (res.status === 401 && (await tryRefresh())) {
    res = await run();
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res;
}

/** Fetch an authenticated endpoint, transparently refreshing once on a 401. */
export async function authedFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await authedRequest(path, init);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export function getMe(): Promise<User> {
  return authedFetch<User>("/v1/auth/me");
}
