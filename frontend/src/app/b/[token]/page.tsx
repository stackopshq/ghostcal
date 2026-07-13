"use client";

import { use, useEffect, useState } from "react";
import { type PublicBusy, byDay, fetchPublicBusy } from "@/lib/busy";

/**
 * Someone's availability, for a visitor with no GhostCal account.
 *
 * The sibling of `/c/[token]`, and deliberately much duller. That page holds ciphertext and needs a
 * key out of the URL fragment to make sense of it. This one needs nothing: it shows *when* its owner
 * is occupied, and there is no *what* to show — the server never sent one, and has no field to send
 * it in.
 *
 * The times are rendered in the visitor's own timezone, with the owner's stated alongside, because
 * "busy at 14:00" is a question, not an answer, until you know whose clock it is.
 */
export default function PublicBusyPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [busy, setBusy] = useState<PublicBusy | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "gone">("loading");

  useEffect(() => {
    let active = true;
    fetchPublicBusy(token)
      .then((data) => {
        if (!active) return;
        setBusy(data);
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

  if (state === "gone" || !busy) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="glass max-w-md rounded-2xl p-8 text-center">
          <h1 className="text-lg font-semibold text-foreground">
            This availability is no longer shared
          </h1>
          <p className="mt-2 text-sm text-muted">
            The link was revoked, or it never existed.
          </p>
        </div>
      </main>
    );
  }

  const here = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const days = byDay(busy.busy);

  return (
    <main className="mx-auto min-h-screen max-w-2xl p-6 sm:p-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-foreground">
          When {busy.owner_name} is busy
        </h1>
        <p className="mt-2 text-sm text-muted">
          The next two weeks. Times are shown in your timezone
          {here ? ` (${here})` : ""}
          {here && here !== busy.owner_timezone
            ? ` — ${busy.owner_name} is in ${busy.owner_timezone}`
            : ""}
          .
        </p>
        <p className="mt-1 text-sm text-muted">
          Everything else is free. What fills these hours is not shared, and was
          not sent to your browser.
        </p>
      </header>

      {days.length === 0 ? (
        <p className="glass rounded-2xl p-8 text-center text-sm text-muted">
          Nothing at all. {busy.owner_name} is free for the next two weeks.
        </p>
      ) : (
        <ol className="flex flex-col gap-4">
          {days.map(({ day, blocks }) => (
            <li key={day.toISOString()} className="glass rounded-2xl p-5">
              <h2 className="text-sm font-semibold text-foreground">
                {day.toLocaleDateString(undefined, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                })}
              </h2>
              <ul className="mt-3 flex flex-col gap-2">
                {blocks.map((block) => (
                  <li
                    key={block.start_at}
                    className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                  >
                    <span className="font-medium text-foreground">
                      {new Date(block.start_at).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                      {" – "}
                      {new Date(block.end_at).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                    <span className="text-muted">Busy</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
