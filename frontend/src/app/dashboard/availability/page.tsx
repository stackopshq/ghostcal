"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import {
  createSchedule,
  listSchedules,
  updateSchedule,
  type Override,
  type Rule,
} from "@/lib/schedules";

type Range = { start: string; end: string };

const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
const COMMON_TZ = [
  "UTC",
  "Europe/Zurich",
  "Europe/Paris",
  "Europe/London",
  "America/New_York",
  "America/Los_Angeles",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const hhmm = (t: string): string => t.slice(0, 5);

function emptyWeek(): Range[][] {
  return Array.from({ length: 7 }, () => []);
}

function defaultWeek(): Range[][] {
  return Array.from({ length: 7 }, (_, wd) =>
    wd < 5 ? [{ start: "09:00", end: "17:00" }] : [],
  );
}

function rulesToWeek(rules: Rule[]): Range[][] {
  const week = emptyWeek();
  for (const r of rules) {
    if (r.weekday >= 0 && r.weekday <= 6) {
      week[r.weekday].push({ start: hhmm(r.start), end: hhmm(r.end) });
    }
  }
  return week;
}

export default function AvailabilityPage() {
  const router = useRouter();
  const browserTz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);

  const [loading, setLoading] = useState(true);
  const [scheduleId, setScheduleId] = useState<string | null>(null);
  const [name, setName] = useState("Working hours");
  const [timezone, setTimezone] = useState("UTC");
  const [week, setWeek] = useState<Range[][]>(emptyWeek);
  const [overrides, setOverrides] = useState<Override[]>([]);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    listSchedules()
      .then((list) => {
        if (list.length > 0) {
          const s = list[0];
          setScheduleId(s.id);
          setName(s.name);
          setTimezone(s.timezone);
          setWeek(rulesToWeek(s.rules));
          setOverrides(s.overrides);
        } else {
          setTimezone(browserTz);
          setWeek(defaultWeek());
        }
      })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router, browserTz]);

  function mutateDay(day: number, fn: (ranges: Range[]) => Range[]) {
    setStatus("idle");
    setWeek((prev) => prev.map((ranges, i) => (i === day ? fn(ranges) : ranges)));
  }

  function toggleDay(day: number) {
    mutateDay(day, (ranges) => (ranges.length > 0 ? [] : [{ start: "09:00", end: "17:00" }]));
  }

  function addRange(day: number) {
    mutateDay(day, (ranges) => [...ranges, { start: "09:00", end: "17:00" }]);
  }

  function removeRange(day: number, index: number) {
    mutateDay(day, (ranges) => ranges.filter((_, i) => i !== index));
  }

  function setRange(day: number, index: number, field: "start" | "end", value: string) {
    mutateDay(day, (ranges) =>
      ranges.map((r, i) => (i === index ? { ...r, [field]: value } : r)),
    );
  }

  async function save() {
    setSaving(true);
    setError(null);
    const rules: Rule[] = week.flatMap((ranges, weekday) =>
      ranges
        .filter((r) => r.start && r.end)
        .map((r) => ({ weekday, start: r.start, end: r.end })),
    );
    const body = { name, timezone, rules, overrides };
    try {
      if (scheduleId) {
        await updateSchedule(scheduleId, body);
      } else {
        const created = await createSchedule(body);
        setScheduleId(created.id);
      }
      setStatus("saved");
    } catch (e) {
      setStatus("error");
      setError(
        e instanceof ApiError && e.status === 422
          ? "Check your hours — each end time must be after its start."
          : "Could not save. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="flex flex-1 items-center justify-center p-8">
        <p className="text-sm text-muted">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6 sm:p-10">
      <header className="flex items-center justify-between">
        <Link href="/dashboard" className="text-sm text-muted hover:text-accent">
          ← Dashboard
        </Link>
        <span className="text-sm font-medium tracking-wide text-muted">
          <span className="text-accent">●</span> Availability
        </span>
      </header>

      <section className="glass flex flex-col gap-6 rounded-2xl p-6 sm:p-8">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm text-muted">
            Schedule name
            <input
              value={name}
              onChange={(e) => {
                setStatus("idle");
                setName(e.target.value);
              }}
              className={inputClass}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-muted">
            Timezone
            <select
              value={timezone}
              onChange={(e) => {
                setStatus("idle");
                setTimezone(e.target.value);
              }}
              className={inputClass}
            >
              {[...new Set([timezone, browserTz, ...COMMON_TZ])].map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-col divide-y divide-border">
          {DAYS.map((label, day) => {
            const ranges = week[day];
            const enabled = ranges.length > 0;
            return (
              <div key={label} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
                <button
                  type="button"
                  onClick={() => toggleDay(day)}
                  className={[
                    "flex w-32 shrink-0 items-center gap-2 text-sm font-medium transition",
                    enabled ? "text-foreground" : "text-muted",
                  ].join(" ")}
                >
                  <span
                    className={[
                      "inline-block h-2.5 w-2.5 rounded-full",
                      enabled ? "bg-accent shadow-[0_0_8px_rgba(0,240,255,0.7)]" : "bg-border-strong",
                    ].join(" ")}
                  />
                  {label}
                </button>

                <div className="flex flex-1 flex-col gap-2">
                  {!enabled && <span className="text-sm text-muted/70">Unavailable</span>}
                  {ranges.map((r, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input
                        type="time"
                        value={r.start}
                        onChange={(e) => setRange(day, i, "start", e.target.value)}
                        className={`${inputClass} py-1.5`}
                      />
                      <span className="text-muted">–</span>
                      <input
                        type="time"
                        value={r.end}
                        onChange={(e) => setRange(day, i, "end", e.target.value)}
                        className={`${inputClass} py-1.5`}
                      />
                      <button
                        type="button"
                        onClick={() => removeRange(day, i)}
                        aria-label="Remove time range"
                        className="px-2 text-muted transition hover:text-red-400"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  {enabled && (
                    <button
                      type="button"
                      onClick={() => addRange(day)}
                      className="self-start text-xs text-accent hover:underline"
                    >
                      + Add a range
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center gap-4">
          <button type="button" onClick={save} disabled={saving} className={primaryButtonClass}>
            {saving ? "Saving…" : "Save availability"}
          </button>
          {status === "saved" && <span className="text-sm text-accent">Saved ✓</span>}
          {status === "error" && error && <span className="text-sm text-red-400">{error}</span>}
        </div>
      </section>
    </main>
  );
}
