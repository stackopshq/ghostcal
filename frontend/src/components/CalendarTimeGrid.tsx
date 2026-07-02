"use client";

import type { CSSProperties } from "react";
import type { AgendaItem } from "@/lib/agenda";

// Fantastical-style time grid for the week and day views: hour rows down the left, one column per
// day, timed events positioned by start time and sized by duration; all-day items in a top strip.

export type GridItem = AgendaItem & { label: string; color?: string };

const HOUR_PX = 44;
const HOURS = Array.from({ length: 24 }, (_, h) => h);

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function hm(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function eventClasses(it: GridItem): string {
  if (it.source !== "event") return "bg-surface-2 text-muted";
  if (it.color) return ""; // colored inline via eventStyle()
  if (it.read_only) return "border border-dashed border-accent/40 text-accent/70";
  return "bg-accent/20 text-accent";
}

// A calendar colour applied inline (Tailwind can't take dynamic colours). Read-only overlays get a
// dashed border to signal they're shared.
function eventStyle(it: GridItem): CSSProperties | undefined {
  if (it.source !== "event" || !it.color) return undefined;
  return it.read_only
    ? { color: it.color, border: `1px dashed ${it.color}80` }
    : { backgroundColor: `${it.color}2b`, color: it.color };
}

export default function CalendarTimeGrid({
  days,
  items,
  locale,
  onNewAt,
  onEventClick,
  labels,
}: {
  days: Date[];
  items: GridItem[];
  locale: string;
  onNewAt: (date: Date, hour: number) => void;
  onEventClick: (it: GridItem) => void;
  labels: { allDay: string; sharedReadOnly: string };
}) {
  const todayKey = ymd(new Date());

  function timedForDay(day: Date): GridItem[] {
    const key = ymd(day);
    return items.filter((it) => !it.all_day && ymd(new Date(it.start)) === key);
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
  const hasAllDay = days.some((d) => allDayForDay(d).length > 0);

  return (
    <div className="glass overflow-hidden rounded-2xl">
      {/* Day headers */}
      <div className="grid border-b border-border" style={{ gridTemplateColumns: cols }}>
        <div />
        {days.map((day) => {
          const isToday = ymd(day) === todayKey;
          return (
            <div key={ymd(day)} className="border-l border-border py-2 text-center">
              <div className="text-[11px] uppercase text-muted">
                {day.toLocaleDateString(locale, { weekday: "short" })}
              </div>
              <div
                className={`text-sm ${isToday ? "font-semibold text-accent" : "text-foreground"}`}
              >
                {day.getDate()}
              </div>
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
          <div className="py-1 pr-1 text-right text-[10px] text-muted">{labels.allDay}</div>
          {days.map((day) => (
            <div key={ymd(day)} className="flex flex-col gap-0.5 border-l border-border p-1">
              {allDayForDay(day).map((it, i) => (
                <button
                  key={i}
                  type="button"
                  title={it.read_only ? labels.sharedReadOnly : undefined}
                  onClick={() => onEventClick(it)}
                  style={eventStyle(it)}
                  className={`truncate rounded px-1.5 py-0.5 text-left text-[11px] ${eventClasses(it)}`}
                >
                  {it.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Scrollable hour grid */}
      <div className="max-h-[64vh] overflow-y-auto">
        <div className="grid" style={{ gridTemplateColumns: cols }}>
          {/* Hour gutter */}
          <div className="relative">
            {HOURS.map((h) => (
              <div
                key={h}
                style={{ height: HOUR_PX }}
                className="pr-1 text-right text-[10px] text-muted"
              >
                <span className="relative -top-1.5">{h > 0 ? `${String(h).padStart(2, "0")}:00` : ""}</span>
              </div>
            ))}
          </div>

          {/* Day columns */}
          {days.map((day) => (
            <div
              key={ymd(day)}
              className="relative border-l border-border"
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
              {timedForDay(day).map((it, i) => {
                const start = new Date(it.start);
                const end = new Date(it.end);
                const dayStart = new Date(day.getFullYear(), day.getMonth(), day.getDate());
                const top = Math.max(0, ((start.getTime() - dayStart.getTime()) / 3_600_000) * HOUR_PX);
                const durMin = Math.max(30, (end.getTime() - start.getTime()) / 60_000);
                const height = (durMin / 60) * HOUR_PX;
                return (
                  <button
                    key={i}
                    type="button"
                    title={it.read_only ? labels.sharedReadOnly : undefined}
                    onClick={() => onEventClick(it)}
                    style={{ top, height, ...eventStyle(it) }}
                    className={`absolute inset-x-0.5 overflow-hidden rounded px-1.5 py-0.5 text-left text-[11px] leading-tight ${eventClasses(it)}`}
                  >
                    <span className="font-medium">{it.label}</span>
                    <span className="block text-[10px] opacity-70">{hm(it.start)}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
