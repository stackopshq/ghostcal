// Publishing a calendar to an external CalDAV server — from the browser, because nothing else can.
//
// The server holds your events sealed and cannot read them, so it cannot build the VEVENT that a
// CalDAV server needs. Only this can. So the browser opens each queued event and hands the server
// the cleartext at push time; the server relays it onward and stores none of it.
//
// The honest cost: a push waits for a browser. Nothing runs this in the background, because nothing
// in the background can read an event. The queue is what makes that liveable — a change is
// remembered until some tab, at some later point, is open with the key unlocked.

import { authedFetch, getActiveOrg } from "@/lib/auth";
import { getUnlockedKeys, openWithOrgKeys, openContent } from "@/lib/zk";

export type PushOp = "upsert" | "delete";

export type PendingPush = {
  id: string;
  op: PushOp;
  external_uid: string;
  /** Ciphertext. This is the point: the server hands it over unopened. */
  content_sealed: string | null;
  start_at: string | null;
  end_at: string | null;
  all_day: boolean;
  rrule: string | null;
};

export type PushResult = { pushed: number; failed: number };

export function publishCalendar(
  calendarId: string,
  connectionId: string | null,
): Promise<void> {
  return authedFetch<void>(`/v1/me/calendar/calendars/${calendarId}/publish`, {
    method: "PUT",
    body: JSON.stringify({ connection_id: connectionId }),
  });
}

function pending(): Promise<PendingPush[]> {
  return authedFetch<PendingPush[]>("/v1/me/calendar/push/pending");
}

/**
 * Drain the publication queue: open what is waiting, and hand the cleartext over to be relayed.
 *
 * Returns how many events reached the CalDAV server. Silent by design — this runs on page load, and
 * a calendar that failed to publish because a phone's server is down is not something to interrupt
 * someone with. The queue keeps it; the next visit tries again.
 */
export async function drainPushQueue(): Promise<number> {
  const keys = getUnlockedKeys(getActiveOrg());
  if (!keys) return 0; // locked: nothing here can open an event, so there is nothing to do

  let pushed = 0;
  for (;;) {
    const batch = await pending();
    if (batch.length === 0) break;

    const items = [];
    for (const item of batch) {
      if (item.op === "delete") {
        // Nothing to open: the event is gone, and the UID is all the far end needs to drop it.
        items.push({
          id: item.id,
          op: item.op,
          external_uid: item.external_uid,
        });
        continue;
      }
      try {
        const content = item.content_sealed
          ? await openWithOrgKeys(keys, item.content_sealed, openContent)
          : { title: "", description: "", location: "" };
        items.push({
          id: item.id,
          op: item.op,
          external_uid: item.external_uid,
          summary: content.title,
          description: content.description,
          location: content.location,
          start_at: item.start_at,
          end_at: item.end_at,
          rrule: item.rrule,
        });
      } catch {
        // A blob none of our org keys open — sealed under a key this tab does not hold. Leave it
        // queued: someone else's browser, or this one after a re-login, will get to it. Publishing
        // a placeholder would be worse than publishing nothing.
      }
    }
    if (items.length === 0) break;

    const result = await authedFetch<PushResult>("/v1/me/calendar/push", {
      method: "POST",
      body: JSON.stringify({ items }),
    });
    pushed += result.pushed;

    // Everything failed and nothing was consumed: the far end is down. Stop rather than spin.
    if (result.pushed === 0) break;
  }
  return pushed;
}
