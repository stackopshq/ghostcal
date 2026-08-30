"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { createPoll, listPolls, type PollSummary } from "@/lib/polls";

export default function PollsPage() {
  const t = useT();
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
      setError(t("pollsh.errMinTwo"));
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
      setError(t("pollsh.errCreate"));
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t("pollsh.title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("pollsh.sub")}</p>
      </div>

      <form onSubmit={submit} className="glass flex flex-col gap-4 rounded-lg p-6">
        <h2 className="text-sm font-medium text-foreground">{t("pollsh.new")}</h2>
        <input
          required
          placeholder={t("pollsh.titlePh")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="rounded-lg border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
        />
        <label className="flex items-center gap-3 text-sm text-muted">
          {t("pollsh.duration")}
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
          <span className="text-sm text-muted">{t("pollsh.proposedTimes")}</span>
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
            {t("pollsh.addTime")}
          </button>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={creating}
          className="self-start rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110 disabled:opacity-60"
        >
          {creating ? t("pollsh.creating") : t("pollsh.create")}
        </button>
      </form>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-foreground">{t("pollsh.yourPolls")}</h2>
        {loading && <p className="text-sm text-muted">{t("common.loading")}</p>}
        {!loading && polls.length === 0 && <p className="text-sm text-muted">{t("pollsh.none")}</p>}
        {polls.map((p) => (
          <Link
            key={p.id}
            href={`/dashboard/polls/${p.id}`}
            className="glass flex items-center justify-between rounded-md p-4 transition hover:border-accent"
          >
            <div>
              <p className="font-medium text-foreground">{p.title}</p>
              <p className="text-sm text-muted">
                {t("pollsh.summary", {
                  options: p.option_count,
                  votes: p.vote_count,
                  status: p.status,
                })}
              </p>
            </div>
            <span className="text-accent">→</span>
          </Link>
        ))}
      </section>
    </main>
  );
}
