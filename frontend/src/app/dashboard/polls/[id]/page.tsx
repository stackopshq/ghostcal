"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { cancelPoll, finalizePoll, getPoll, type Poll } from "@/lib/polls";

function fmt(iso: string, tz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export default function PollDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);
  const [poll, setPoll] = useState<Poll | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    getPoll(id)
      .then((p) => active && setPoll(p))
      .catch(() => active && setPoll(null))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [id]);

  async function finalize(optionId: string) {
    if (!confirm("Lock in this time? Everyone who voted will be notified.")) return;
    setBusy(true);
    try {
      setPoll(await finalizePoll(id, optionId));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Cancel this poll?")) return;
    await cancelPoll(id);
    window.location.href = "/dashboard/polls";
  }

  if (loading) return <Wrap>Loading…</Wrap>;
  if (!poll) return <Wrap>Poll not found.</Wrap>;

  const shareUrl =
    typeof window !== "undefined" ? `${window.location.origin}/poll/${poll.slug}` : "";

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6 sm:p-10">
      <Link href="/dashboard/polls" className="text-sm text-muted hover:text-foreground">
        ← All polls
      </Link>
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{poll.title}</h1>
        <p className="mt-1 text-sm text-muted">
          {poll.duration_min} min · {poll.status}
        </p>
      </div>

      {poll.status === "open" && (
        <p className="rounded-lg border border-border bg-surface-2/50 px-4 py-3 text-sm text-muted">
          Share to collect votes: <span className="text-accent">{shareUrl}</span>
        </p>
      )}

      <section className="flex flex-col gap-2">
        {poll.options.map((o) => {
          const won = poll.finalized_option_id === o.id;
          return (
            <div
              key={o.id}
              className={[
                "flex items-center justify-between rounded-xl border p-4",
                won ? "border-accent" : "border-border",
              ].join(" ")}
            >
              <div>
                <p className="font-medium text-foreground">{fmt(o.start_at, tz)}</p>
                <p className="text-sm text-muted">
                  {o.votes} vote{o.votes === 1 ? "" : "s"}
                  {won && <span className="text-accent"> · chosen</span>}
                </p>
              </div>
              {poll.status === "open" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => finalize(o.id)}
                  className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-foreground transition hover:border-accent hover:text-accent disabled:opacity-60"
                >
                  Pick this time
                </button>
              )}
            </div>
          );
        })}
      </section>

      {poll.voters.length > 0 && (
        <section className="flex flex-col gap-1">
          <h2 className="text-sm font-medium text-foreground">Voters</h2>
          {poll.voters.map((v) => (
            <p key={v.email} className="text-sm text-muted">
              {v.name} ({v.email}) — {v.option_ids.length} time
              {v.option_ids.length === 1 ? "" : "s"}
            </p>
          ))}
        </section>
      )}

      <button
        type="button"
        onClick={remove}
        className="self-start text-sm text-muted transition hover:text-red-400"
      >
        Cancel poll
      </button>
    </main>
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-3xl p-10">
      <p className="text-sm text-muted">{children}</p>
    </main>
  );
}
