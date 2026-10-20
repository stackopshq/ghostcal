"use client";

import type { GridItem } from "@/components/CalendarTimeGrid";
import { LockIcon } from "@/components/icons";

/** A task as the calendar shows it: decrypted title, cleartext due date. */
export type AgendaTask = { id: string; title: string; due_at: string };

/**
 * What is coming up, as a list.
 *
 * The month/week/day grids answer "when is this?". This one answers "what is next?" — which is the
 * question people actually open a calendar to ask, and the one a grid is worst at when the day is
 * mostly empty.
 *
 * Laid out like the mobile app and Fantastical: one section per day, named "Today", "Tomorrow" or
 * the weekday, the day's tasks first with a box to tick, then the events with their time on the
 * left and a bar in their calendar's colour. Today also gathers the overdue tasks, so a late one
 * stays in sight instead of sinking into the past.
 *
 * Titles here are already decrypted: the page unseals them in the browser before handing them over,
 * exactly as the grid views get them. Nothing new is exposed by listing them.
 */
export default function CalendarAgendaList({
  items,
  tasks = [],
  locale,
  onEventClick,
  onTaskTick,
  labels,
}: {
  items: GridItem[];
  tasks?: AgendaTask[];
  locale: string;
  onEventClick: (item: GridItem) => void;
  onTaskTick?: (task: AgendaTask) => void;
  labels: {
    allDay: string;
    empty: string;
    sharedReadOnly: string;
    subscriptionReadOnly: string;
    today: string;
    tomorrow: string;
  };
}) {
  const today = startOfDay(new Date());
  // Not memoised: a few hundred rows at most, and the React compiler already caches what it can.
  const days = (() => {
    const byDay = new Map<
      number,
      { date: Date; items: GridItem[]; tasks: AgendaTask[] }
    >();
    const bucket = (d: Date) => {
      const date = startOfDay(d);
      const key = date.getTime();
      let b = byDay.get(key);
      if (!b) {
        b = { date, items: [], tasks: [] };
        byDay.set(key, b);
      }
      return b;
    };
    for (const item of [...items].sort((a, b) =>
      a.start.localeCompare(b.start),
    )) {
      bucket(new Date(item.start)).items.push(item);
    }
    for (const task of [...tasks].sort((a, b) =>
      a.due_at.localeCompare(b.due_at),
    )) {
      const due = new Date(task.due_at);
      // Overdue: under today, not on a day the list never shows.
      bucket(due < today ? today : due).tasks.push(task);
    }
    return [...byDay.values()].sort(
      (a, b) => a.date.getTime() - b.date.getTime(),
    );
  })();

  if (days.length === 0) {
    return (
      <div className="glass rounded-lg p-10 text-center text-sm text-muted">
        {labels.empty}
      </div>
    );
  }

  const dayName = (d: Date) => {
    const gap = Math.round((d.getTime() - today.getTime()) / 86_400_000);
    if (gap === 0) return labels.today;
    if (gap === 1) return labels.tomorrow;
    return d.toLocaleDateString(locale, { weekday: "long" });
  };
  const time = (iso: string) =>
    new Date(iso).toLocaleTimeString(locale, {
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <div className="glass flex flex-col divide-y divide-border-strong rounded-lg">
      {days.map(({ date, items: dayItems, tasks: dayTasks }) => {
        const isToday = date.getTime() === today.getTime();
        return (
          <section key={date.getTime()} className="px-4 py-4 sm:px-6">
            <h2
              className={`mb-2 text-sm tracking-wide ${isToday ? "text-accent" : "text-foreground"}`}
            >
              <span className="font-extrabold uppercase">{dayName(date)}</span>
              <span
                className={`ml-2 font-medium tabular-nums ${isToday ? "" : "text-muted"}`}
              >
                {date.toLocaleDateString(locale)}
              </span>
            </h2>

            <ul className="flex flex-col">
              {dayTasks.map((task) => {
                const due = new Date(task.due_at);
                const late = startOfDay(due).getTime() < date.getTime();
                return (
                  <li key={`task-${task.id}`}>
                    <button
                      type="button"
                      onClick={() => onTaskTick?.(task)}
                      className="flex w-full items-start gap-3 rounded-pill px-2 py-1.5 text-left transition hover:bg-surface-2/60"
                    >
                      <span
                        aria-hidden
                        className="mt-0.5 h-5 w-5 shrink-0 rounded-sm border-2 border-emerald-500"
                      />
                      <span className="min-w-0 flex-1">
                        {late && (
                          <span className="block text-sm font-semibold text-rose-500">
                            {due.toLocaleDateString(locale, {
                              day: "numeric",
                              month: "short",
                            })}
                          </span>
                        )}
                        <span className="block truncate text-base text-foreground">
                          {task.title}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}

              {dayItems.map((item) => (
                <li key={`${item.source}-${item.event_id ?? item.start}`}>
                  <button
                    type="button"
                    onClick={() => onEventClick(item)}
                    className="flex w-full items-stretch gap-3 rounded-pill px-2 py-1.5 text-left transition hover:bg-surface-2/60"
                  >
                    {/* `min-w-0` n'est pas cosmétique : un enfant flex refuse par
                        défaut de descendre sous la largeur de son contenu, donc
                        `truncate` ne s'applique JAMAIS sans lui. */}
                    <span className="w-14 shrink-0 tabular-nums">
                      {item.all_day ? (
                        <span className="text-xs text-muted">{labels.allDay}</span>
                      ) : (
                        <>
                          <span className="block text-sm font-semibold text-foreground">
                            {time(item.start)}
                          </span>
                          {item.end && (
                            <span className="block text-xs text-muted">
                              {time(item.end)}
                            </span>
                          )}
                        </>
                      )}
                    </span>
                    <span
                      aria-hidden
                      className="w-1 shrink-0 rounded-pill"
                      style={{ backgroundColor: item.color ?? "var(--accent)" }}
                    />
                    <span className="min-w-0 flex-1 self-center truncate text-base font-medium text-foreground">
                      {item.label}
                    </span>
                    {item.read_only && (
                      <span
                        title={
                          item.source === "subscription"
                            ? labels.subscriptionReadOnly
                            : labels.sharedReadOnly
                        }
                        className="shrink-0 self-center text-xs text-muted"
                      >
                        <LockIcon />
                        <span className="sr-only">
                          {item.source === "subscription"
                            ? labels.subscriptionReadOnly
                            : labels.sharedReadOnly}
                        </span>
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
