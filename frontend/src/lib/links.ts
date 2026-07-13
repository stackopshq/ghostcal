// Share a calendar outside the organization, by secret link (ADR-0009).
//
// The link has its own keypair. Its PUBLIC key goes to the server; its PRIVATE key goes into the URL
// fragment and stays there. Browsers do not send fragments, so the server has never seen it and never
// will — which is why it can hold the sealed copies and still not be able to read them.
//
// Why a keypair and not a shared secret: sealing a NEW event later needs only the public key, which
// the server already has. The owner never has to keep the link's secret anywhere, and a secret you
// do not keep is one you cannot lose.

import { authedFetch, getActiveOrg } from "@/lib/auth";
import {
  generateOrgKeypair,
  getUnlockedKeys,
  keyToFragment,
  openContent,
  openWithOrgKeys,
  sealContent,
} from "@/lib/zk";

export type CalendarLink = {
  id: string;
  name: string;
  public_key: string;
  created_at: string;
  /** Events with no sealed copy for this link yet — what this browser has left to do. */
  pending: number;
};

type PendingSeal = { event_id: string; content_sealed: string | null };

export function listLinks(calendarId: string): Promise<CalendarLink[]> {
  return authedFetch<CalendarLink[]>(`/v1/me/calendars/${calendarId}/links`);
}

export function revokeLink(linkId: string): Promise<void> {
  return authedFetch<void>(`/v1/me/links/${linkId}`, { method: "DELETE" });
}

/**
 * Mint a link and seal the calendar's events to it.
 *
 * Returns the full URL, **including the fragment**. This is the only moment it exists: the token is
 * never retrievable again (the server keeps a hash), and the private key was never sent anywhere. If
 * the owner loses it, they make a new link — which is the correct behaviour, not a limitation.
 */
export async function createLink(
  calendarId: string,
  name: string,
): Promise<string> {
  const pair = await generateOrgKeypair();

  const created = await authedFetch<{ id: string; token: string }>(
    `/v1/me/calendars/${calendarId}/links`,
    {
      method: "POST",
      body: JSON.stringify({ public_key: pair.publicKey, name }),
    },
  );

  // The link exists but shows nothing yet: only this browser can open the events, so only this
  // browser can seal the copies. Do it now, before handing over a link that would look broken.
  await sealPendingFor(created.id, pair.publicKey);

  // base64url: a fragment parsed with URLSearchParams turns a base64 `+` into a space, and the
  // key comes back corrupted. See keyToFragment.
  return `${window.location.origin}/c/${created.token}#k=${keyToFragment(pair.privateKey)}`;
}

/**
 * Seal whatever this link has no copy of yet.
 *
 * Only this browser can: it opens each event with the ORG key it holds, and re-seals the result to
 * the LINK's public key. The server carries two envelopes it cannot open, side by side.
 */
export async function sealPendingFor(
  linkId: string,
  linkPublicKey: string,
): Promise<number> {
  const keys = getUnlockedKeys(getActiveOrg());
  if (!keys) return 0;

  let sealed = 0;
  for (;;) {
    const pending = await authedFetch<PendingSeal[]>(
      `/v1/me/links/${linkId}/pending`,
    );
    if (pending.length === 0) break;

    const copies = [];
    for (const item of pending) {
      if (!item.content_sealed) continue; // an event with no content is nothing to show
      try {
        const content = await openWithOrgKeys(
          keys,
          item.content_sealed,
          openContent,
        );
        copies.push({
          event_id: item.event_id,
          content_sealed: await sealContent(content, linkPublicKey),
        });
      } catch {
        // Sealed under a key this tab does not hold. Leave it pending rather than publish a
        // placeholder — an empty slot is honest, a wrong title is not.
      }
    }
    if (copies.length === 0) break;

    await authedFetch<void>(`/v1/me/links/${linkId}/seal`, {
      method: "POST",
      body: JSON.stringify({ copies }),
    });
    sealed += copies.length;
  }
  return sealed;
}

/** Bring every link on this calendar up to date — a changed event dropped its copies. */
export async function refreshLinks(calendarId: string): Promise<void> {
  for (const link of await listLinks(calendarId)) {
    if (link.pending > 0) await sealPendingFor(link.id, link.public_key);
  }
}

// --- the visitor's side ------------------------------------------------------------------------

export type PublicEvent = {
  start_at: string;
  end_at: string;
  all_day: boolean;
  timezone: string;
  rrule: string | null;
  exdates: string[];
  content_sealed: string;
};

export type PublicCalendar = {
  calendar_name: string;
  owner_name: string;
  events: PublicEvent[];
};

/** No auth: a visitor has no account. What comes back is ciphertext. */
export function fetchPublicCalendar(token: string): Promise<PublicCalendar> {
  return fetch(`/api/v1/public/calendar/${encodeURIComponent(token)}`).then(
    (r) => {
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json() as Promise<PublicCalendar>;
    },
  );
}
