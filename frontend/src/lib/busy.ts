// Share when you are free, without showing what you are doing.
//
// The sibling of links.ts, and deliberately much smaller. A calendar link (ADR-0009) shares sealed
// events, so it needs a keypair, a fragment, and a browser that re-seals every event to it.
//
// A free-busy link needs none of that, because there is nothing secret to hand over: busy *times*
// are already cleartext on the server (the booking engine has to reason about them to offer slots at
// all). So there is no key here, and no fragment — the URL is the whole link.
//
// Which is worth saying out loud in the UI, because the two links look alike and are not: whoever
// finds this one learns *when* you are busy, and never once *what* you are doing.

import { authedFetch } from "@/lib/auth";

export type BusyLink = {
  id: string;
  name: string;
  created_at: string;
};

/** A stretch of occupied time. There is no title, and there is no field for one. */
export type BusyBlock = {
  start_at: string;
  end_at: string;
};

export type PublicBusy = {
  owner_name: string;
  owner_timezone: string;
  busy: BusyBlock[];
};

export function listBusyLinks(): Promise<BusyLink[]> {
  return authedFetch<BusyLink[]>("/v1/me/busy-links");
}

/** Mint a link. The token comes back once — only its hash is stored, so it cannot be shown again. */
export async function createBusyLink(name: string): Promise<string> {
  const { token } = await authedFetch<{ id: string; token: string }>(
    "/v1/me/busy-links",
    { method: "POST", body: JSON.stringify({ name }) },
  );
  return `${window.location.origin}/b/${token}`;
}

export function revokeBusyLink(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/busy-links/${id}`, { method: "DELETE" });
}

export function fetchPublicBusy(token: string): Promise<PublicBusy> {
  return fetch(`/api/v1/public/busy/${encodeURIComponent(token)}`).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json() as Promise<PublicBusy>;
  });
}

/** Group busy blocks by local day, for a visitor reading them in their own timezone. */
export function byDay(busy: BusyBlock[]): { day: Date; blocks: BusyBlock[] }[] {
  const days = new Map<string, BusyBlock[]>();
  for (const block of busy) {
    const start = new Date(block.start_at);
    const key = `${start.getFullYear()}-${start.getMonth()}-${start.getDate()}`;
    days.set(key, [...(days.get(key) ?? []), block]);
  }
  return [...days.values()].map((blocks) => ({
    day: new Date(blocks[0].start_at),
    blocks,
  }));
}
