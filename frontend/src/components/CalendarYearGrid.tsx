"use client";

import { useMemo } from "react";
import type { GridItem } from "@/components/CalendarTimeGrid";

/**
 * Twelve months at a glance.
 *
 * A year has no room for titles — and here that is a feature rather than a constraint. The server
 * cannot read the titles anyway; what a year view is *for* is shape: which weeks are packed, which
 * are empty, where the holiday is. So each day is a dot whose weight tracks how much is on it, and
 * clicking one drops into that day.
 */
export default function CalendarYearGrid({
  year,
  items,
  locale,
  onPickDay,
  todayLabel,
}: {
  year: number;
  items: GridItem[];
  locale: string;
  onPickDay: (day: Date) => void;
  todayLabel: string;
}) {
  // How many items land on each day. Keyed by local date, not UTC: an event at 00:30 Paris time
  // belongs to that day for the person looking at it, whatever the epoch says.
  const countByDay = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      const d = new Date(item.start);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return counts;
  }, [items]);

  const today = new Date();
  const isToday = (d: Date) =>
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate();

  const monthNames = useMemo(
    () =>
      Array.from({ length: 12 }, (_, m) =>
        new Date(year, m, 1).toLocaleDateString(locale, { month: "long" }),
      ),
    [year, locale],
  );

  // Monday-first initials, taken from a known Monday so they follow the locale rather than English.
  const weekdayInitials = useMemo(() => {
    const monday = new Date(2024, 0, 1);
    return Array.from({ length: 7 }, (_, i) =>
      new Date(2024, 0, 1 + i)
        .toLocaleDateString(locale, { weekday: "narrow" })
        .slice(0, 1),
    ).map((s, i) => ({ key: `${monday.getTime()}-${i}`, label: s }));
  }, [locale]);

  return (
    <div className="glass grid gap-6 rounded-lg p-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {monthNames.map((name, month) => {
        const first = new Date(year, month, 1);
        const offset = (first.getDay() + 6) % 7; // Monday-first
        const daysInMonth = new Date(year, month + 1, 0).getDate();

        return (
          <div key={name}>
            <h3 className="mb-2 text-sm font-medium capitalize text-foreground">
              {name}
            </h3>
            <div className="grid grid-cols-7 gap-y-1 text-center text-[10px] text-muted">
              {weekdayInitials.map((d) => (
                <span key={d.key}>{d.label}</span>
              ))}
              {Array.from({ length: offset }, (_, i) => (
                <span key={`pad-${i}`} />
              ))}
              {Array.from({ length: daysInMonth }, (_, i) => {
                const day = new Date(year, month, i + 1);
                const count = countByDay.get(`${year}-${month}-${i + 1}`) ?? 0;
                return (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onPickDay(day)}
                    aria-label={`${day.toLocaleDateString(locale)}${isToday(day) ? ` (${todayLabel})` : ""}`}
                    className={`relative mx-auto flex h-6 w-6 items-center justify-center rounded-pill text-[11px] transition hover:bg-surface-2 ${
                      isToday(day)
                        ? "bg-accent font-semibold text-black"
                        : count > 0
                          ? "text-foreground"
                          : "text-muted"
                    }`}
                  >
                    {i + 1}
                    {count > 0 && !isToday(day) && (
                      <span
                        aria-hidden
                        className="absolute bottom-0 h-1 w-1 rounded-pill bg-accent"
                        // Weight, not count: three dots in a 6px cell is noise. Opacity carries the
                        // "busy day" signal legibly, and the day view carries the detail.
                        style={{ opacity: Math.min(1, 0.35 + count * 0.2) }}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
