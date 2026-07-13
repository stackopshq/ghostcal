"use client";

import { use, useEffect, useState } from "react";
import {
  type PublicCalendar,
  type PublicEvent,
  fetchPublicCalendar,
} from "@/lib/links";
import { keyFromFragment, openContent } from "@/lib/zk";

/**
 * A shared calendar, for someone with no GhostCal account (ADR-0009).
 *
 * The server handed this page ciphertext. The key that opens it is in the URL fragment — the part
 * after `#`, which browsers **do not send**. So the server has never seen it, cannot see it, and is
 * holding a calendar it cannot read while serving it to someone who can.
 *
 * If the fragment is missing, the page has a calendar and no way to open it. It says so, rather than
 * rendering a wall of "(encrypted)" and letting the visitor think the app is broken.
 */
export default function PublicCalendarPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [calendar, setCalendar] = useState<PublicCalendar | null>(null);
  const [titles, setTitles] = useState<Map<number, string>>(new Map());
  const [state, setState] = useState<"loading" | "ready" | "nokey" | "gone">(
    "loading",
  );

  useEffect(() => {
    let active = true;

    // The key lives in the fragment, and only ever in the fragment. It is base64url — standard
    // base64 would have its `+` decoded as a space right here, and the link would simply "not work".
    const raw = new URLSearchParams(window.location.hash.slice(1)).get("k");
    const key = raw ? keyFromFragment(raw) : null;
    if (!key) {
      // Client-only: the fragment does not exist during SSR, so this cannot be read any earlier.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState("nokey");
      return;
    }

    fetchPublicCalendar(token)
      .then(async (data) => {
        if (!active) return;
        const opened = new Map<number, string>();
        await Promise.all(
          data.events.map(async (event: PublicEvent, i: number) => {
            try {
              opened.set(
                i,
                (await openContent(event.content_sealed, key)).title,
              );
            } catch {
              // A key that does not fit this calendar. Leaving the entry out is honest.
            }
          }),
        );
        if (!active) return;
        setCalendar(data);
        setTitles(opened);
        setState("ready");
      })
      .catch(() => active && setState("gone"));

    return () => {
      active = false;
    };
  }, [token]);

  if (state === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted">Loading…</p>
      </main>
    );
  }

  if (state === "nokey") {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="glass max-w-md rounded-2xl p-8 text-center">
          <h1 className="text-lg font-semibold text-foreground">
            This link is missing its key
          </h1>
          <p className="mt-2 text-sm text-muted">
            The part of the link after <code className="text-accent">#</code> is
            what decrypts the calendar, and it never reaches our servers. Copy
            the whole link, including that part.
          </p>
        </div>
      </main>
    );
  }

  if (state === "gone" || !calendar) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="glass max-w-md rounded-2xl p-8 text-center">
          <h1 className="text-lg font-semibold text-foreground">
            This calendar is no longer shared
          </h1>
          <p className="mt-2 text-sm text-muted">
            The link was revoked, or it never existed.
          </p>
        </div>
      </main>
    );
  }

  const sorted = calendar.events
    .map((event, i) => ({ event, title: titles.get(i) }))
    .filter((x) => x.title !== undefined)
    .sort((a, b) => a.event.start_at.localeCompare(b.event.start_at));

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">
          {calendar.calendar_name}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Shared with you by {calendar.owner_name} · decrypted in your browser,
          never on the server.
        </p>
      </div>

      {sorted.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center text-sm text-muted">
          Nothing on this calendar yet.
        </div>
      ) : (
        <ul className="glass flex flex-col divide-y divide-border rounded-2xl">
          {sorted.map(({ event, title }) => (
            <li
              key={event.start_at + (title ?? "")}
              className="flex items-center gap-4 p-4 sm:gap-6 sm:p-5"
            >
              <div className="w-24 shrink-0 sm:w-32">
                <p className="text-sm font-medium text-foreground">
                  {new Date(event.start_at).toLocaleDateString(undefined, {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                  })}
                </p>
                <p className="text-xs tabular-nums text-muted">
                  {event.all_day
                    ? "All day"
                    : new Date(event.start_at).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                </p>
              </div>
              <span className="flex-1 truncate text-sm text-foreground">
                {title}
              </span>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
