"use client";

import { useEffect, useState } from "react";
import { type Analytics, getAnalytics } from "@/lib/analytics";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="glass rounded-2xl p-5">
      <p className="text-3xl font-semibold text-foreground">{value}</p>
      <p className="mt-1 text-sm text-muted">{label}</p>
    </div>
  );
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getAnalytics()
      .then((d) => active && setData(d))
      .catch(() => active && setData(null))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  if (loading) return <Center>Loading…</Center>;
  if (!data) return <Center>Could not load analytics.</Center>;

  const maxDay = Math.max(1, ...data.daily.map((d) => d.count));
  const maxEvent = Math.max(1, ...data.by_event_type.map((e) => e.count));

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-8 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Analytics</h1>
        <p className="mt-1 text-sm text-muted">Booking activity across your organization.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Total bookings" value={data.total_bookings} />
        <Stat label="Upcoming" value={data.upcoming_bookings} />
        <Stat label="Booked (30d)" value={data.bookings_last_30_days} />
        <Stat label="Cancelled (30d)" value={data.cancellations_last_30_days} />
      </div>

      <section className="glass flex flex-col gap-3 rounded-2xl p-6">
        <h2 className="text-sm font-medium text-foreground">Activity (2 weeks)</h2>
        {data.daily.length === 0 ? (
          <p className="text-sm text-muted">No bookings in this window.</p>
        ) : (
          <div className="flex h-32 items-end gap-1.5">
            {data.daily.map((d) => (
              <div key={d.day} className="flex flex-1 flex-col items-center gap-1" title={d.day}>
                <div
                  className="w-full rounded-t bg-accent/70"
                  style={{ height: `${(d.count / maxDay) * 100}%` }}
                />
                <span className="text-[10px] text-muted/70">{d.day.slice(5)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="glass flex flex-col gap-3 rounded-2xl p-6">
        <h2 className="text-sm font-medium text-foreground">Top event types</h2>
        {data.by_event_type.length === 0 ? (
          <p className="text-sm text-muted">No bookings yet.</p>
        ) : (
          data.by_event_type.map((e) => (
            <div key={e.title} className="flex items-center gap-3 text-sm">
              <span className="w-40 shrink-0 truncate text-foreground">{e.title}</span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${(e.count / maxEvent) * 100}%` }}
                />
              </div>
              <span className="w-8 text-right text-muted">{e.count}</span>
            </div>
          ))
        )}
      </section>
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
