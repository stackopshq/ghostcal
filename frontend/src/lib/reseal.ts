// Re-sealing the backlog after a rotation (ADR-0007) — where revocation becomes total.
//
// Rotating the org key stops the leak going forward. The records sealed BEFORE the rotation are
// still readable with the key a departed member may have kept. This pass walks them: each is opened
// with the key that sealed it and re-sealed to the current one, in the browser, which is the only
// place both keys exist. When the backlog reaches zero, the old key opens nothing at all.
//
// It runs in a tab, over a history that may be large, so it is built to be stopped: progress is
// committed batch by batch, and picking it up again just means asking what is left.

import { authedFetch, getActiveOrg } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { getUnlockedKeys, reseal } from "@/lib/zk";

export type SealedKind = "booking" | "event" | "task";

export type SealedRecord = { kind: SealedKind; id: string; sealed: string };

export type Backlog = {
  /** The org's current key generation. */
  generation: number;
  /** Records still sealed under a retired key. Zero means the rotation is actually finished. */
  remaining: number;
};

const BATCH = 50;

export function getBacklog(): Promise<Backlog> {
  return authedFetch<Backlog>("/v1/me/organization/reseal");
}

function fetchPending(limit: number): Promise<SealedRecord[]> {
  return authedFetch<SealedRecord[]>(
    `/v1/me/organization/reseal/pending?limit=${limit}`,
  );
}

function postBatch(
  generation: number,
  records: SealedRecord[],
): Promise<{ applied: number; remaining: number }> {
  return authedFetch("/v1/me/organization/reseal", {
    method: "POST",
    body: JSON.stringify({ generation, records }),
  });
}

export class KeyLocked extends Error {
  constructor() {
    super("the organization key is not unlocked in this tab");
  }
}

/** The org rotated again mid-pass: the blobs in hand are sealed to a key that is no longer current. */
export class RotatedUnderneath extends Error {
  constructor() {
    super("the organization key rotated again");
  }
}

/**
 * Walk the backlog, re-sealing each record to the current key.
 *
 * Reports progress after every batch so a long pass shows movement, and returns how many records it
 * moved. Stopping it (closing the tab) costs progress, never correctness: every batch that landed
 * stays landed, and the next run simply asks what is left.
 */
export async function resealBacklog(
  onProgress?: (done: number, total: number) => void,
): Promise<number> {
  const organizationId = getActiveOrg();
  const keys = getUnlockedKeys(organizationId);
  if (!keys) throw new KeyLocked();

  const start = await getBacklog();
  let done = 0;
  onProgress?.(0, start.remaining);

  for (;;) {
    const pending = await fetchPending(BATCH);
    if (pending.length === 0) break;

    const resealed: SealedRecord[] = [];
    for (const record of pending) {
      try {
        resealed.push({ ...record, sealed: await reseal(record.sealed, keys) });
      } catch {
        // A blob none of our keys open. Skipping it keeps the pass moving; it stays in the backlog
        // and stays readable by whoever does hold that key — dropping or blanking it would destroy
        // data to tidy a counter.
      }
    }
    if (resealed.length === 0) break; // nothing in this batch could be opened; no point looping

    try {
      const result = await postBatch(start.generation, resealed);
      done += result.applied;
      onProgress?.(done, start.remaining);
      if (result.remaining === 0) break;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409)
        throw new RotatedUnderneath();
      throw err;
    }
  }

  return done;
}
