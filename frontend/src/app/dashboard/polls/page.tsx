"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createPoll, listPolls, type PollSummary } from "@/lib/polls";

export default function PollsPage() {
  const [polls, setPolls] = useState<PollSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);

  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState(30);
  const [options, setOptions] = useState<string[]>(["", ""]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let active = true;
    listPolls()
      .then((p) => active && setPolls(p))
      .catch(() => active && setPolls([]))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [refresh]);

  function setOption(i: number, value: string) {
    setOptions((prev) => prev.map((o, idx) => (idx === i ? value : o)));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const starts = options
      .filter(Boolean)
      .map((local) => new Date(local).toISOString());
    if (starts.length < 2) {
      setError("Add at least two time options.");
      return;
    }
    setCreating(true);
    try {
      await createPoll({
        title,
        duration_min: duration,
        location_type: "google_meet",
        option_starts: starts,
      });
      setTitle("");
      setOptions(["", ""]);
      setRefresh((r) => r + 1);
    } catch {
      setError("Could not create the poll.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Meeting polls</h1>
        <p className="mt-1 text-sm text-muted">
          Propose several times, let invitees vote, then lock one in.
        </p>
      </div>

      <form onSubmit={submit} className="glass flex flex-col gap-4 rounded-2xl p-6">
        <h2 className="text-sm font-medium text-foreground">New poll</h2>
        <input
          required
          placeholder="Poll title (e.g. Team retro)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="rounded-lg border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
        />
        <label className="flex items-center gap-3 text-sm text-muted">
          Duration
          <select
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
            className="rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
          >
            {[15, 30, 45, 60].map((d) => (
              <option key={d} value={d}>
                {d} min
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-col gap-2">
          <span className="text-sm text-muted">Proposed times</span>
          {options.map((value, i) => (
            <div key={i} className="flex gap-2">
              <input
                type="datetime-local"
                value={value}
                onChange={(e) => setOption(i, e.target.value)}
                className="flex-1 rounded-lg border border-border-strong bg-surface-2 px-4 py-2 text-sm text-foreground outline-none focus:border-accent"
              />
              {options.length > 2 && (
                <button
                  type="button"
                  onClick={() => setOptions((prev) => prev.filter((_, idx) => idx !== i))}
                  className="rounded-lg border border-border-strong px-3 text-sm text-muted hover:text-red-400"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            onClick={() => setOptions((prev) => [...prev, ""])}
            className="self-start text-sm text-accent hover:brightness-110"
          >
            + Add a time
          </button>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={creating}
          className="self-start rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110 disabled:opacity-60"
        >
          {creating ? "Creating…" : "Create poll"}
        </button>
      </form>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-foreground">Your polls</h2>
        {loading && <p className="text-sm text-muted">Loading…</p>}
        {!loading && polls.length === 0 && <p className="text-sm text-muted">No polls yet.</p>}
        {polls.map((p) => (
          <Link
            key={p.id}
            href={`/dashboard/polls/${p.id}`}
            className="glass flex items-center justify-between rounded-xl p-4 transition hover:border-accent"
          >
            <div>
              <p className="font-medium text-foreground">{p.title}</p>
              <p className="text-sm text-muted">
                {p.option_count} options · {p.vote_count} votes · {p.status}
              </p>
            </div>
            <span className="text-accent">→</span>
          </Link>
        ))}
      </section>
    </main>
  );
}
