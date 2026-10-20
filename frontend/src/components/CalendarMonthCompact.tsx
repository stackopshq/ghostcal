"use client";

import type { AgendaTask } from "@/components/CalendarAgendaList";
import type { GridItem } from "@/components/CalendarTimeGrid";

/**
 * The month on a phone, as in Fantastical and the mobile app: a compact grid of numbers with
 * coloured dots, the selected week as a band and today as a filled disc. The page lists the
 * selected day and the ones after it underneath.
 *
 * Titles do not fit in a seventh of a phone: written in the cells they were three letters and an
 * ellipsis. The dots say which days are busy; the list says with what.
 */
export default function CalendarMonthCompact({
  days,
  month,
  selected,
  items,
  tasks,
  weekdays,
  locale,
  onSelect,
  onOpen,
}: {
  /** Six weeks from the Monday before the first of the month. */
  days: Date[];
  month: number;
  selected: Date;
  items: GridItem[];
  tasks: AgendaTask[];
  /** Narrow weekday names, Monday first. */
  weekdays: string[];
  locale: string;
  onSelect: (day: Date) => void;
  /** Tapping the selected day again opens it, as in Fantastical. */
  onOpen: (day: Date) => void;
}) {
  const key = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  const today = new Date();
  const todayKey = key(today);
  const selectedKey = key(selected);
  const todayIndex = (today.getDay() + 6) % 7;

  function dotsFor(day: Date): string[] {
    const start = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
    const end = start + 86_400_000;
    const colours: string[] = [];
    for (const x of tasks) {
      const due = new Date(x.due_at).getTime();
      const todayStart = new Date(new Date().setHours(0, 0, 0, 0)).getTime();
      // An overdue task shows on today only: on its own past day as well, it read as two tasks.
      if (
        (due >= start && due < end && due >= todayStart) ||
        (key(day) === todayKey && due < start)
      ) {
        colours.push("var(--color-emerald-500, #10b981)");
      }
    }
    for (const it of items) {
      const s = new Date(it.start).getTime();
      const e = new Date(it.end).getTime();
      if (s < end && (e > start || s >= start)) colours.push(it.color ?? "var(--color-accent)");
    }
    return colours.slice(0, 3);
  }

  const weeks = Array.from({ length: days.length / 7 }, (_, w) => days.slice(w * 7, w * 7 + 7));

  return (
    <div className="glass rounded-lg px-1 pb-1">
      <div className="grid grid-cols-7 py-2 text-center text-2xs font-medium uppercase tracking-wide text-muted">
        {weekdays.map((w, i) => (
          <span key={i} className={i === todayIndex ? "text-accent" : ""}>
            {w}
          </span>
        ))}
      </div>
      {weeks.map((week) => {
        const band = week.some((d) => key(d) === selectedKey);
        return (
          <div
            key={key(week[0])}
            className={`grid grid-cols-7 rounded-lg ${band ? "bg-surface-2/70" : ""}`}
          >
            {week.map((day) => {
              const k = key(day);
              const isToday = k === todayKey;
              const isSelected = k === selectedKey;
              const dots = dotsFor(day);
              return (
                <button
                  key={k}
                  type="button"
                  aria-label={day.toLocaleDateString(locale, {
                    weekday: "long",
                    day: "numeric",
                    month: "long",
                  })}
                  aria-pressed={isSelected}
                  onClick={() => (isSelected ? onOpen(day) : onSelect(day))}
                  className={`flex h-12 flex-col items-center justify-center gap-0.5 ${
                    day.getMonth() === month ? "" : "opacity-40"
                  }`}
                >
                  <span
                    className={`inline-flex h-7 w-7 items-center justify-center rounded-pill text-sm tabular-nums ${
                      isToday
                        ? "bg-accent font-bold text-accent-ink"
                        : isSelected
                          ? "bg-foreground font-bold"
                          : "font-medium text-foreground"
                    }`}
                    // The selected day reads as ink inverted: the base colour on the ink disc.
                    style={isSelected && !isToday ? { color: "var(--color-base)" } : undefined}
                  >
                    {day.getDate()}
                  </span>
                  <span aria-hidden className="flex h-1.5 gap-0.5">
                    {dots.map((c, i) => (
                      <span
                        key={i}
                        className="h-1.5 w-1.5 rounded-pill"
                        style={{ backgroundColor: c }}
                      />
                    ))}
                  </span>
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
