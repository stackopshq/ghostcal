"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getPublicPoll, votePoll, type PublicPoll } from "@/lib/api";
import { useT } from "@/lib/i18n";

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

export default function PublicPollPage() {
  const t = useT();
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);
  const [poll, setPoll] = useState<PublicPoll | null>(null);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getPublicPoll(slug)
      .then((p) => active && setPoll(p))
      .catch(() => active && setPoll(null))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [slug]);

  function toggle(id: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (picked.size === 0) {
      setError(t("poll.pickOne"));
      return;
    }
    try {
      await votePoll(slug, {
        voter_name: name,
        voter_email: email,
        option_ids: [...picked],
      });
      setDone(true);
    } catch {
      setError(t("poll.errVote"));
    }
  }

  if (loading) return <Center>{t("common.loading")}</Center>;
  if (!poll) return <Center>{t("poll.notExist")}</Center>;

  const finalized = poll.options.find((o) => o.id === poll.finalized_option_id);

  return (
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      <div className="glass w-full max-w-lg rounded-lg p-8 shadow-2xl">
        <p className="text-sm text-muted">{t("poll.asking", { owner: poll.owner_name })}</p>
        <h1 className="mt-1 text-2xl font-semibold text-foreground">{poll.title}</h1>
        <p className="mt-1 text-sm text-muted">
          {t("poll.minTimes", { n: poll.duration_min, tz })}
        </p>

        {finalized ? (
          <div className="mt-6 rounded border border-accent p-4">
            <p className="text-sm text-muted">{t("poll.confirmedTime")}</p>
            <p className="text-lg font-medium text-foreground">{fmt(finalized.start_at, tz)}</p>
          </div>
        ) : done ? (
          <p className="mt-6 text-sm text-accent">{t("poll.thanks")}</p>
        ) : poll.status !== "open" ? (
          <p className="mt-6 text-sm text-muted">{t("poll.closed")}</p>
        ) : (
          <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
            {poll.options.map((o) => (
              <label
                key={o.id}
                className="flex items-center gap-3 rounded-lg border border-border-strong px-4 py-2.5 text-sm text-foreground"
              >
                <input type="checkbox" checked={picked.has(o.id)} onChange={() => toggle(o.id)} />
                <span className="flex-1">{fmt(o.start_at, tz)}</span>
                <span className="text-muted">{o.votes}</span>
              </label>
            ))}
            <input
              required
              placeholder={t("booking.yourName")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
            />
            <input
              required
              type="email"
              placeholder={t("booking.yourEmail")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              className="rounded-pill bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110"
            >
              {t("poll.submit")}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <p className="text-sm text-muted">{children}</p>
    </main>
  );
}
