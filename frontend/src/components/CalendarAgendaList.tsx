"use client";

import { useMemo } from "react";
import type { GridItem } from "@/components/CalendarTimeGrid";

/**
 * What is coming up, as a list.
 *
 * The month/week/day grids answer "when is this?". This one answers "what is next?" — which is the
 * question people actually open a calendar to ask, and the one a grid is worst at when the day is
 * mostly empty.
 *
 * Titles here are already decrypted: the page unseals them in the browser before handing them over,
 * exactly as the grid views get them. Nothing new is exposed by listing them.
 */
export default function CalendarAgendaList({
  items,
  locale,
  onEventClick,
  labels,
}: {
  items: GridItem[];
  locale: string;
  onEventClick: (item: GridItem) => void;
  labels: { allDay: string; empty: string; sharedReadOnly: string };
}) {
  const days = useMemo(() => {
    const byDay = new Map<string, { date: Date; items: GridItem[] }>();
    for (const item of [...items].sort((a, b) =>
      a.start.localeCompare(b.start),
    )) {
      const d = new Date(item.start);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const bucket = byDay.get(key);
      if (bucket) bucket.items.push(item);
      else
        byDay.set(key, {
          date: new Date(d.getFullYear(), d.getMonth(), d.getDate()),
          items: [item],
        });
    }
    return [...byDay.values()];
  }, [items]);

  if (days.length === 0) {
    return (
      <div className="glass rounded-2xl p-10 text-center text-sm text-muted">
        {labels.empty}
      </div>
    );
  }

  const today = new Date();
  const isToday = (d: Date) =>
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate();

  return (
    <div className="glass flex flex-col divide-y divide-border rounded-2xl">
      {days.map(({ date, items: dayItems }) => (
        <div
          key={date.toISOString()}
          className="flex gap-4 p-4 sm:gap-6 sm:p-5"
        >
          <div className="w-20 shrink-0 sm:w-28">
            <p
              className={`text-sm font-medium ${isToday(date) ? "text-accent" : "text-foreground"}`}
            >
              {date.toLocaleDateString(locale, {
                weekday: "short",
                day: "numeric",
              })}
            </p>
            <p className="text-xs text-muted">
              {date.toLocaleDateString(locale, { month: "short" })}
            </p>
          </div>

          <ul className="flex flex-1 flex-col gap-2">
            {dayItems.map((item) => (
              <li key={`${item.source}-${item.event_id ?? item.start}`}>
                <button
                  type="button"
                  onClick={() => onEventClick(item)}
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left transition hover:bg-surface-2/60"
                >
                  <span
                    aria-hidden
                    className="h-8 w-1 shrink-0 rounded-full"
                    style={{ backgroundColor: item.color ?? "var(--accent)" }}
                  />
                  <span className="w-24 shrink-0 text-xs tabular-nums text-muted">
                    {item.all_day
                      ? labels.allDay
                      : new Date(item.start).toLocaleTimeString(locale, {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                  </span>
                  <span className="flex-1 truncate text-sm text-foreground">
                    {item.label}
                  </span>
                  {item.read_only && (
                    <span className="shrink-0 text-xs text-muted">
                      {labels.sharedReadOnly}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
