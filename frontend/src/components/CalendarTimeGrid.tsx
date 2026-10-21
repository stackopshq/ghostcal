"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { AgendaTask } from "@/components/CalendarAgendaList";
import type { AgendaItem } from "@/lib/agenda";
import { layoutLanes } from "@/lib/eventLayout";

// Fantastical-style time grid for the week and day views: hour rows down the left, one column per
// day, timed events positioned by start time and sized by duration; all-day items in a top strip.

export type GridItem = AgendaItem & { label: string; color?: string };

const HOUR_PX = 44;
const HOURS = Array.from({ length: 24 }, (_, h) => h);
// Shortest drawn duration: a 5-minute event still gets a readable box.
const MIN_DURATION_MS = 30 * 60_000;

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function hm(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function eventClasses(it: GridItem): string {
  if (it.color) return "text-foreground"; // colored inline via eventStyle()
  if (it.source !== "event") return "bg-surface-2 text-muted";
  if (it.read_only) return "border border-dashed border-accent/40 text-accent/70";
  return "bg-accent/20 text-foreground";
}

// A calendar colour applied inline (Tailwind can't take dynamic colours): a tint and a bar on the
// left in the calendar's colour, the title in the ink colour — Fantastical's block, and the mobile
// app's. Non-editable items — shared read-only calendars and external (CalDAV) events — keep a
// dashed border to signal it.
function eventStyle(it: GridItem): CSSProperties | undefined {
  if (!it.color) return undefined;
  const outlined = it.read_only || it.source === "external";
  return outlined
    ? { color: it.color, border: `1px dashed ${it.color}80` }
    : { backgroundColor: `${it.color}2b`, borderLeft: `3px solid ${it.color}` };
}

/** The current time, refreshed every minute: the "now" line moves. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export default function CalendarTimeGrid({
  days,
  items,
  locale,
  onNewAt,
  onEventClick,
  onDayClick,
  labels,
  weatherByDay,
  tasks = [],
  onTaskTick,
}: {
  days: Date[];
  items: GridItem[];
  /** Tasks shown in the top strip on the day they are due; today also gathers the overdue ones. */
  tasks?: AgendaTask[];
  onTaskTick?: (task: AgendaTask) => void;
  locale: string;
  onNewAt: (date: Date, hour: number) => void;
  onEventClick: (it: GridItem) => void;
  /** Zoom into one day. Optional: in day view there is nowhere to zoom to, and
   *  the caller says so by not passing it rather than by us guessing from
   *  `days.length === 1`. */
  onDayClick?: (day: Date) => void;
  labels: {
    allDay: string;
    sharedReadOnly: string;
    subscriptionReadOnly: string;
    openDay: string;
  };
  weatherByDay?: Map<string, { glyph: string; tmax: number; tmin: number }>;
}) {
  const now = useNow();
  const todayKey = ymd(now);
  const todayIndex = days.findIndex((d) => ymd(d) === todayKey);
  const nowMinutes = now.getHours() * 60 + now.getMinutes();

  // Open on the current hour today, on the working morning otherwise — not on midnight, which put
  // the first event of the day below the fold.
  const scroller = useRef<HTMLDivElement>(null);
  const firstDay = days[0] ? ymd(days[0]) : "";
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const hour = todayIndex >= 0 ? Math.max(0, new Date().getHours() - 1) : 7.5;
    el.scrollTop = hour * HOUR_PX;
    // Once per period shown, not on every minute tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstDay, days.length]);

  function tasksForDay(day: Date): AgendaTask[] {
    const start = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
    const end = start + 86_400_000;
    const isToday = ymd(day) === todayKey;
    return tasks.filter((x) => {
      const due = new Date(x.due_at).getTime();
      const todayStart = new Date(new Date().setHours(0, 0, 0, 0)).getTime();
      // An overdue task shows on today only: on its own past day as well, it read as two tasks.
      return (due >= start && due < end && due >= todayStart) || (isToday && due < start);
    });
  }

  function timedForDay(day: Date): GridItem[] {
    const key = ymd(day);
    return items.filter((it) => !it.all_day && ymd(new Date(it.start)) === key);
  }
  // Timed events with their box: overlapping events share the column width side by side.
  // Lanes are computed on the drawn box, not the real end, so a short event whose minimum-height
  // box covers its neighbour is split too.
  function positionedForDay(day: Date) {
    const dayStart = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
    const timed = timedForDay(day);
    const spans = timed.map((it) => {
      const start = new Date(it.start).getTime();
      const end = new Date(it.end).getTime();
      return { start, end: start + Math.max(MIN_DURATION_MS, end - start) };
    });
    const lanes = layoutLanes(spans);
    return timed.map((it, i) => {
      const { start, end } = spans[i];
      const width = 100 / lanes[i].lanes;
      return {
        it,
        top: Math.max(0, ((start - dayStart) / 3_600_000) * HOUR_PX),
        height: ((end - start) / 3_600_000) * HOUR_PX,
        left: `calc(${lanes[i].lane * width}% + 2px)`,
        width: `calc(${width}% - 4px)`,
      };
    });
  }
  function allDayForDay(day: Date): GridItem[] {
    const dayStart = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
    const dayEnd = dayStart + 86_400_000;
    return items.filter(
      (it) =>
        it.all_day &&
        new Date(it.start).getTime() < dayEnd &&
        new Date(it.end).getTime() > dayStart,
    );
  }

  const cols = `4rem repeat(${days.length}, minmax(0, 1fr))`;
  const hasAllDay = days.some(
    (d) => allDayForDay(d).length > 0 || tasksForDay(d).length > 0,
  );
  const todayTint = (day: Date) => (days.length > 1 && ymd(day) === todayKey ? "bg-accent/5" : "");

  return (
    <div className="glass overflow-hidden rounded-lg">
      {/* Day headers */}
      <div className="grid border-b border-border" style={{ gridTemplateColumns: cols }}>
        <div />
        {days.map((day) => {
          const isToday = ymd(day) === todayKey;
          const wx = weatherByDay?.get(ymd(day));
          return (
            <div key={ymd(day)} className={`border-l border-border py-2 text-center ${todayTint(day)}`}>
              <div className={`text-2xs font-medium uppercase ${isToday ? "text-accent" : "text-muted"}`}>
                {day.toLocaleDateString(locale, { weekday: "short" })}
              </div>
              {onDayClick ? (
                <button
                  type="button"
                  onClick={() => onDayClick(day)}
                  title={labels.openDay}
                  aria-label={`${labels.openDay}, ${day.toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long" })}`}
                  className={`inline-flex h-7 min-w-7 items-center justify-center rounded-pill px-1.5 text-base tabular-nums ${
                    isToday
                      ? "bg-accent font-bold text-accent-ink"
                      : "text-foreground hover:bg-surface-2 hover:text-accent"
                  }`}
                >
                  {day.getDate()}
                </button>
              ) : (
                <div
                  className={`mx-auto inline-flex h-7 min-w-7 items-center justify-center rounded-pill px-1.5 text-base tabular-nums ${
                    isToday ? "bg-accent font-bold text-accent-ink" : "text-foreground"
                  }`}
                >
                  {day.getDate()}
                </div>
              )}
              {wx && (
                <div
                  className="mt-0.5 text-2xs text-muted"
                  title={`${Math.round(wx.tmin)}° / ${Math.round(wx.tmax)}°`}
                >
                  <span aria-hidden>{wx.glyph}</span> {Math.round(wx.tmax)}°
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* All-day strip */}
      {hasAllDay && (
        <div
          className="grid border-b border-border bg-surface-2/20"
          style={{ gridTemplateColumns: cols }}
        >
          <div className="py-1 pr-1 text-right text-2xs text-muted">{labels.allDay}</div>
          {days.map((day) => (
            <div key={ymd(day)} className={`flex min-w-0 flex-col gap-0.5 border-l border-border p-1 ${todayTint(day)}`}>
              {tasksForDay(day).map((task) => (
                <button
                  key={`task-${task.id}`}
                  type="button"
                  role="checkbox"
                  aria-checked={false}
                  title={task.title}
                  onClick={() => onTaskTick?.(task)}
                  className="flex min-w-0 items-center gap-1 rounded-pill bg-emerald-500/15 px-1.5 py-0.5 text-left text-2xs font-medium text-emerald-500 hover:bg-emerald-500/25"
                >
                  <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-sm border border-current" />
                  <span className="truncate">{task.title}</span>
                </button>
              ))}
              {allDayForDay(day).map((it, i) => (
                <button
                  key={i}
                  type="button"
                  title={
                    it.source === "subscription"
                      ? labels.subscriptionReadOnly
                      : it.read_only
                        ? labels.sharedReadOnly
                        : undefined
                  }
                  onClick={() => onEventClick(it)}
                  style={eventStyle(it)}
                  className={`truncate rounded-pill px-1.5 py-0.5 text-left text-2xs ${eventClasses(it)}`}
                >
                  {it.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Scrollable hour grid */}
      <div ref={scroller} className="max-h-[64vh] overflow-y-auto">
        <div className="relative grid" style={{ gridTemplateColumns: cols }}>
          {/* Hour gutter */}
          <div className="relative">
            {HOURS.map((h) => (
              <div
                key={h}
                style={{ height: HOUR_PX }}
                className="pr-1 text-right text-2xs text-muted"
              >
                {/* The hour the red time sits on is left out: two labels on one line read as
                    neither. */}
                <span className="relative -top-1.5">
                  {h > 0 && (todayIndex < 0 || Math.abs(nowMinutes - h * 60) > 15)
                    ? `${String(h).padStart(2, "0")}:00`
                    : ""}
                </span>
              </div>
            ))}
          </div>

          {/* Day columns */}
          {days.map((day) => (
            <div
              key={ymd(day)}
              className={`relative border-l border-border ${todayTint(day)}`}
              style={{ height: 24 * HOUR_PX }}
            >
              {HOURS.map((h) => (
                <button
                  key={h}
                  type="button"
                  aria-label={`${ymd(day)} ${h}:00`}
                  onClick={() => onNewAt(day, h)}
                  style={{ height: HOUR_PX }}
                  className="block w-full border-b border-border/40 transition hover:bg-surface-2/30"
                />
              ))}
              {positionedForDay(day).map(({ it, top, height, left, width }, i) => (
                <button
                  key={i}
                  type="button"
                  // A narrow lane truncates the label; the tooltip gives it back.
                  title={
                    it.source === "subscription"
                      ? labels.subscriptionReadOnly
                      : it.read_only
                        ? labels.sharedReadOnly
                        : `${it.label} · ${hm(it.start)}`
                  }
                  onClick={() => onEventClick(it)}
                  style={{ top, height, left, width, ...eventStyle(it) }}
                  className={`absolute overflow-hidden rounded-sm px-1.5 py-0.5 text-left text-2xs leading-tight ${eventClasses(it)}`}
                >
                  <span className="font-semibold">{it.label}</span>
                  <span className="block text-2xs opacity-70">{hm(it.start)}</span>
                </button>
              ))}
            </div>
          ))}

          {/* The "now" line: the time in red in the gutter, a line across every day and a dot
              where it crosses today — Fantastical's reading of the hour. */}
          {todayIndex >= 0 && (
            <div
              aria-hidden
              className="pointer-events-none absolute inset-x-0"
              style={{ top: (nowMinutes / 60) * HOUR_PX - 7, height: 14 }}
            >
              <span className="absolute left-0 flex h-full w-16 items-center justify-end pr-1 text-2xs font-bold tabular-nums text-rose-500">
                {now.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}
              </span>
              <span className="absolute right-0 left-16 top-1/2 h-0.5 -translate-y-1/2 bg-rose-500" />
              <span
                className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-rose-500"
                style={{ left: `calc(4rem + (100% - 4rem) * ${todayIndex / days.length})` }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
