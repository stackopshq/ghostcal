"use client";

import { useEffect, useMemo, useState } from "react";
import { cancelMeeting, listMeetings, type Meeting, type MeetingScope } from "@/lib/meetings";

function fmtDay(iso: string, tz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(iso));
}

function fmtTime(iso: string, tz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

const TABS: { key: MeetingScope; label: string }[] = [
  { key: "upcoming", label: "Upcoming" },
  { key: "past", label: "Past" },
];

export default function MeetingsPage() {
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);
  const [scope, setScope] = useState<MeetingScope>("upcoming");
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    listMeetings(scope)
      .then((m) => active && setMeetings(m))
      .catch(() => active && setMeetings([]))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [scope, refresh]);

  function switchTo(next: MeetingScope) {
    if (next === scope) return;
    setLoading(true);
    setScope(next);
  }

  async function cancel(id: string) {
    if (!confirm("Cancel this meeting? The invitee's slot will be freed.")) return;
    await cancelMeeting(id);
    setRefresh((r) => r + 1);
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Meetings</h1>
        <p className="mt-1 text-sm text-muted">
          Your booked meetings. Times shown in {tz}.
        </p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => switchTo(tab.key)}
            className={[
              "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition",
              scope === tab.key
                ? "border-accent text-accent"
                : "border-transparent text-muted hover:text-foreground",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-muted">Loading…</p>}
      {!loading && meetings.length === 0 && (
        <p className="text-sm text-muted">
          No {scope} meetings{scope === "upcoming" ? " — share an event type link to get booked." : "."}
        </p>
      )}

      <div className="flex flex-col gap-3">
        {meetings.map((m) => (
          <div
            key={m.id}
            className="glass flex flex-col gap-2 rounded-2xl border-l-[3px] border-l-accent p-5 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="font-medium text-foreground">{m.event_title}</p>
              <p className="text-sm text-muted">
                {m.invitee_name} · {m.invitee_email}
              </p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-sm sm:text-right">
                <p className="text-foreground">{fmtDay(m.start_at, tz)}</p>
                <p className="text-muted">
                  {fmtTime(m.start_at, tz)} – {fmtTime(m.end_at, tz)}
                </p>
              </div>
              {scope === "upcoming" && (
                <button
                  type="button"
                  onClick={() => cancel(m.id)}
                  className="rounded-lg border border-border-strong px-3 py-2 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
