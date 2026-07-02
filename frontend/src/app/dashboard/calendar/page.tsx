"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getActiveOrg } from "@/lib/auth";
import {
  type AgendaItem,
  type CalendarRec,
  createCalendar,
  createEvent,
  deleteEvent,
  type EventDetail,
  type EventInput,
  getAgenda,
  getEvent,
  listCalendars,
  listShares,
  type Share,
  shareCalendar,
  unshareCalendar,
  updateEvent,
} from "@/lib/agenda";
import CalendarTimeGrid, { type GridItem } from "@/components/CalendarTimeGrid";
import EventAttendees from "@/components/EventAttendees";
import { useI18n, useT } from "@/lib/i18n";
import { parseQuickAdd, type QuickAddResult } from "@/lib/quickAdd";
import { listMembers, type Member } from "@/lib/team";
import { getUnlockedKeys, openContent, sealContent, type EventContent } from "@/lib/zk";

const TZ = typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "UTC";
const REPEATS = [
  { value: "", key: "calendar.repeatNone" },
  { value: "FREQ=DAILY", key: "calendar.repeatDaily" },
  { value: "FREQ=WEEKLY", key: "calendar.repeatWeekly" },
  { value: "FREQ=MONTHLY", key: "calendar.repeatMonthly" },
];

type DecoratedItem = AgendaItem & { label: string };
type Draft = {
  id: string | null;
  calendarId: string;
  title: string;
  description: string;
  location: string;
  date: string;
  start: string;
  end: string;
  allDay: boolean;
  rrule: string;
  reminderMinutes: number | null;
  // Recurrence-exception context: the full master record, the clicked occurrence start, and whether
  // an edit/delete applies to the whole series or just this occurrence.
  master: EventDetail | null;
  occStart: string | null;
  scope: "series" | "occurrence";
};

const REMINDERS = [
  { value: "", key: "calendar.remindNone" },
  { value: "10", key: "calendar.remind10m" },
  { value: "60", key: "calendar.remind1h" },
  { value: "1440", key: "calendar.remind1d" },
];

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function localKey(iso: string): string {
  return ymd(new Date(iso));
}
function hm(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** The 42-cell (6×7) grid starting on the Monday on/before the 1st of the month. */
function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7; // Monday-first
  const start = new Date(year, month, 1 - offset);
  return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}

type CalView = "month" | "week" | "day";

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function startOfWeek(d: Date): Date {
  return addDays(d, -((d.getDay() + 6) % 7)); // Monday-first
}
/** The visible days for the current view (7 for week, 1 for day; month uses monthGrid). */
function viewDays(view: CalView, cursor: Date): Date[] {
  if (view === "day") return [new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate())];
  const start = startOfWeek(cursor);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}
/** The agenda query window [from, to) covering the visible range, with padding for recurrence. */
function viewWindow(view: CalView, cursor: Date): [Date, Date] {
  if (view === "day") {
    const s = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate());
    return [s, addDays(s, 1)];
  }
  if (view === "week") {
    const s = startOfWeek(cursor);
    return [s, addDays(s, 7)];
  }
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  return [addDays(first, -7), new Date(cursor.getFullYear(), cursor.getMonth() + 1, 7)];
}

export default function CalendarPage() {
  const { locale, t } = useI18n();
  const [cursor, setCursor] = useState(() => new Date());
  const [items, setItems] = useState<DecoratedItem[]>([]);
  const [calendars, setCalendars] = useState<CalendarRec[]>([]);
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [quickText, setQuickText] = useState("");
  const [quickBusy, setQuickBusy] = useState(false);
  const [view, setView] = useState<CalView>("month");

  // Restore the last-used view once on mount (client-only; avoids an SSR/hydration mismatch).
  useEffect(() => {
    const saved = localStorage.getItem("gc_cal_view");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved === "week" || saved === "day" || saved === "month") setView(saved);
  }, []);
  function pickView(v: CalView) {
    setView(v);
    localStorage.setItem("gc_cal_view", v);
  }

  const ownCalendar = useMemo(() => calendars.find((c) => !c.is_shared), [calendars]);
  const ownCalendars = useMemo(() => calendars.filter((c) => !c.is_shared), [calendars]);
  const colorOf = useMemo(() => new Map(calendars.map((c) => [c.id, c.color])), [calendars]);
  const defaultCalendarId = useMemo(
    () => (ownCalendars.find((c) => c.is_default) ?? ownCalendars[0])?.id ?? "",
    [ownCalendars],
  );
  // Calendars toggled off in the overlay (hidden from the views), persisted per device.
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [newCalOpen, setNewCalOpen] = useState(false);
  const quickRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("gc_cal_hidden") ?? "[]") as string[];
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved.length) setHidden(new Set(saved));
    } catch {
      /* ignore */
    }
  }, []);
  function toggleCalendar(id: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      localStorage.setItem("gc_cal_hidden", JSON.stringify([...next]));
      return next;
    });
  }

  // Live natural-language parse of the quick-add box (pure — no effect, no network).
  const quickParsed = useMemo(
    () => (quickText.trim() ? parseQuickAdd(quickText, locale) : null),
    [quickText, locale],
  );

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const grid = useMemo(() => monthGrid(year, month), [year, month]);

  const load = useCallback(async () => {
    setLoading(true);
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys) {
      setLocked(true);
      setLoading(false);
      return;
    }
    setLocked(false);
    const [fromDate, toDate] = viewWindow(view, cursor);
    const from = fromDate.toISOString();
    const to = toDate.toISOString();
    try {
      const [cals, agenda] = await Promise.all([listCalendars(), getAgenda(from, to)]);
      setCalendars(cals);
      const cache = new Map<string, string>();
      const decorated: DecoratedItem[] = [];
      for (const it of agenda) {
        let label = it.title ?? t("calendar.busy");
        if (it.source === "event" && it.content) {
          let title = cache.get(it.content);
          if (title === undefined) {
            try {
              title = (await openContent(it.content, keys.privateKey)).title || t("calendar.untitled");
            } catch {
              title = t("calendar.locked");
            }
            cache.set(it.content, title);
          }
          label = title;
        }
        decorated.push({ ...it, label });
      }
      setItems(decorated);
    } finally {
      setLoading(false);
    }
  }, [view, cursor, t]);

  useEffect(() => {
    // Data-loading effect: load() toggles the loading flag and fills state from the API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  // Focus the quick-add when arriving via the command palette's "New event" (#new).
  useEffect(() => {
    if (window.location.hash === "#new") {
      requestAnimationFrame(() => quickRef.current?.focus());
      history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  // Keyboard shortcuts (ignored while typing): m/w/d switch views, t today, ←/→ step, n quick-add.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "m") pickView("month");
      else if (k === "w") pickView("week");
      else if (k === "d") pickView("day");
      else if (k === "t") setCursor(new Date());
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === "ArrowRight") step(1);
      else if (k === "n") {
        e.preventDefault();
        quickRef.current?.focus();
      } else return;
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, cursor]);

  function openNew(date: Date, hour = 9) {
    if (locked) return;
    const h = String(hour).padStart(2, "0");
    const hEnd = String((hour + 1) % 24).padStart(2, "0");
    setDraft({
      id: null,
      calendarId: defaultCalendarId,
      title: "",
      description: "",
      location: "",
      date: ymd(date),
      start: `${h}:00`,
      end: `${hEnd}:00`,
      allDay: false,
      rrule: "",
      reminderMinutes: null,
      master: null,
      occStart: null,
      scope: "series",
    });
  }

  // A time-grid event/slot click: edit an event, or create at the clicked day+hour.
  function onGridEvent(it: GridItem) {
    if (it.source === "event" && it.event_id && !it.read_only) void openEdit(it.event_id, it.start);
  }

  async function openEdit(eventId: string, occStartIso: string) {
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys) return;
    const ev = await getEvent(eventId);
    let content: EventContent = { title: "", description: "", location: "" };
    if (ev.content) {
      try {
        content = await openContent(ev.content, keys.privateKey);
      } catch {
        /* leave blank if we cannot open it */
      }
    }
    // Show the clicked occurrence's date/time (recurring) so an "occurrence" edit shifts the right one.
    const occ = new Date(occStartIso);
    const masterStart = new Date(ev.start_at);
    const masterEnd = new Date(ev.end_at);
    const durationMs = masterEnd.getTime() - masterStart.getTime();
    const occEnd = new Date(occ.getTime() + durationMs);
    const t24 = (d: Date) => d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
    setDraft({
      id: ev.id,
      calendarId: ev.calendar_id,
      title: content.title,
      description: content.description,
      location: content.location,
      date: ymd(occ),
      start: t24(occ),
      end: t24(occEnd),
      allDay: ev.all_day,
      rrule: ev.rrule ?? "",
      reminderMinutes: ev.reminder_minutes,
      master: ev,
      occStart: occStartIso,
      scope: ev.rrule ? "occurrence" : "series",
    });
  }

  // The master event with the clicked occurrence excluded (used to detach/cancel one occurrence).
  function masterWithExdate(master: EventDetail, occStart: string): EventInput {
    return {
      calendar_id: master.calendar_id,
      start_at: master.start_at,
      end_at: master.end_at,
      timezone: master.timezone,
      all_day: master.all_day,
      rrule: master.rrule,
      content: master.content,
      reminder_minutes: master.reminder_minutes,
      exdates: [...master.exdates, occStart],
    };
  }

  function draftFromQuick(p: QuickAddResult): Draft {
    return {
      id: null,
      calendarId: defaultCalendarId,
      title: p.title,
      description: "",
      location: p.location,
      date: p.date,
      start: p.start,
      end: p.end,
      allDay: p.allDay,
      rrule: p.rrule,
      reminderMinutes: null,
      master: null,
      occStart: null,
      scope: "series",
    };
  }

  // Enter in the quick-add box: seal and create the parsed event directly (the Fantastical move).
  async function quickCreate() {
    if (!quickParsed) return;
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys?.publicKey) return;
    setQuickBusy(true);
    try {
      const startAt = quickParsed.allDay
        ? new Date(`${quickParsed.date}T00:00:00`)
        : new Date(`${quickParsed.date}T${quickParsed.start}:00`);
      const endAt = quickParsed.allDay
        ? new Date(`${quickParsed.date}T00:00:00`)
        : new Date(`${quickParsed.date}T${quickParsed.end}:00`);
      if (quickParsed.allDay) endAt.setDate(endAt.getDate() + 1);
      const content = await sealContent(
        {
          title: quickParsed.title || t("calendar.untitled"),
          description: "",
          location: quickParsed.location,
        },
        keys.publicKey,
      );
      await createEvent({
        calendar_id: defaultCalendarId,
        start_at: startAt.toISOString(),
        end_at: endAt.toISOString(),
        timezone: TZ,
        all_day: quickParsed.allDay,
        rrule: quickParsed.rrule || null,
        content,
        reminder_minutes: null,
      });
      setQuickText("");
      await load();
    } finally {
      setQuickBusy(false);
    }
  }

  async function save() {
    if (!draft) return;
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys?.publicKey) return;
    const startAt = draft.allDay
      ? new Date(`${draft.date}T00:00:00`)
      : new Date(`${draft.date}T${draft.start}:00`);
    const endAt = draft.allDay
      ? new Date(`${draft.date}T00:00:00`)
      : new Date(`${draft.date}T${draft.end}:00`);
    if (draft.allDay) endAt.setDate(endAt.getDate() + 1);
    const content = await sealContent(
      { title: draft.title, description: draft.description, location: draft.location },
      keys.publicKey,
    );
    const detached: EventInput = {
      calendar_id: draft.calendarId || defaultCalendarId,
      start_at: startAt.toISOString(),
      end_at: endAt.toISOString(),
      timezone: TZ,
      all_day: draft.allDay,
      rrule: null,
      content,
      reminder_minutes: draft.reminderMinutes,
    };

    const editingOneOccurrence = draft.id && draft.master?.rrule && draft.scope === "occurrence";
    if (!draft.id) {
      await createEvent({ ...detached, rrule: draft.rrule || null });
    } else if (editingOneOccurrence && draft.master && draft.occStart) {
      // Exclude this occurrence from the series, then add the edited standalone event.
      await updateEvent(draft.id, masterWithExdate(draft.master, draft.occStart));
      await createEvent(detached);
    } else {
      // Whole series (or a non-recurring event): update the master in place.
      await updateEvent(draft.id, {
        ...detached,
        rrule: draft.rrule || null,
        exdates: draft.master?.exdates ?? [],
      });
    }
    setDraft(null);
    await load();
  }

  async function remove() {
    if (!draft?.id) return;
    if (draft.master?.rrule && draft.scope === "occurrence" && draft.occStart) {
      // Delete just this occurrence: exclude it from the series.
      await updateEvent(draft.id, masterWithExdate(draft.master, draft.occStart));
    } else {
      await deleteEvent(draft.id);
    }
    setDraft(null);
    await load();
  }

  const days = useMemo(() => viewDays(view, cursor), [view, cursor]);
  const headerLabel =
    view === "month"
      ? cursor.toLocaleDateString(locale, { month: "long", year: "numeric" })
      : view === "day"
        ? cursor.toLocaleDateString(locale, { weekday: "long", month: "long", day: "numeric" })
        : `${days[0].toLocaleDateString(locale, { month: "short", day: "numeric" })} – ${days[6].toLocaleDateString(locale, { month: "short", day: "numeric" })}`;

  function step(dir: -1 | 1) {
    if (view === "month") setCursor(new Date(year, month + dir, 1));
    else if (view === "week") setCursor(addDays(cursor, 7 * dir));
    else setCursor(addDays(cursor, dir));
  }

  // Hide toggled-off calendars; colour each event by its calendar (own calendars + shared).
  const visibleItems = useMemo(
    () => items.filter((it) => !it.calendar_id || !hidden.has(it.calendar_id)),
    [items, hidden],
  );
  const gridItems: GridItem[] = visibleItems.map((it) => ({
    ...it,
    color: it.calendar_id ? colorOf.get(it.calendar_id) : undefined,
  }));

  const quickPreview = quickParsed
    ? {
        date: new Date(
          `${quickParsed.date}T${quickParsed.allDay ? "00:00" : quickParsed.start}:00`,
        ).toLocaleDateString(locale, { weekday: "short", month: "short", day: "numeric" }),
        time: quickParsed.allDay ? t("calendar.allDay") : `${quickParsed.start}–${quickParsed.end}`,
      }
    : null;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-5 p-6 sm:p-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold capitalize text-foreground">{headerLabel}</h1>
          <p className="mt-1 text-sm text-muted">{t("calendar.sub")}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* View switcher */}
          <div className="flex overflow-hidden rounded-lg border border-border-strong">
            {(["month", "week", "day"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => pickView(v)}
                className={`px-3 py-1.5 text-sm transition ${
                  view === v
                    ? "bg-accent text-accent-ink"
                    : "text-muted hover:text-accent"
                }`}
              >
                {t(`calendar.view${v[0].toUpperCase()}${v.slice(1)}`)}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => step(-1)}
            className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-muted hover:text-accent"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => setCursor(new Date())}
            className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-muted hover:text-accent"
          >
            {t("calendar.today")}
          </button>
          <button
            type="button"
            onClick={() => step(1)}
            className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-muted hover:text-accent"
          >
            ›
          </button>
          {ownCalendar && (
            <button
              type="button"
              onClick={() => setShareOpen(true)}
              className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-muted hover:text-accent"
            >
              {t("calendar.share")}
            </button>
          )}
        </div>
      </div>

      {!locked && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void quickCreate();
          }}
          className="flex flex-col gap-2"
        >
          <div className="flex items-center gap-2">
            <span aria-hidden className="text-lg text-accent">
              ⌁
            </span>
            <input
              ref={quickRef}
              value={quickText}
              onChange={(e) => setQuickText(e.target.value)}
              placeholder={t("calendar.quickAdd")}
              className="flex-1 rounded-lg border border-border bg-surface-2/40 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
            <button
              type="submit"
              disabled={!quickParsed || quickBusy}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-40"
            >
              {quickBusy ? t("common.saving") : t("calendar.quickAddCreate")}
            </button>
          </div>
          {quickParsed && quickPreview ? (
            <button
              type="button"
              onClick={() => {
                setDraft(draftFromQuick(quickParsed));
                setQuickText("");
              }}
              className="flex flex-wrap items-center gap-x-2 gap-y-1 self-start rounded-lg border border-border bg-surface-2/40 px-3 py-1.5 text-left text-xs"
            >
              <span className="font-medium text-foreground">
                {quickParsed.title || t("calendar.untitled")}
              </span>
              <span className="text-accent">{quickPreview.date}</span>
              <span className="text-muted">{quickPreview.time}</span>
              {quickParsed.location && <span className="text-muted">· {quickParsed.location}</span>}
              {quickParsed.rrule && <span className="text-muted">· ↻</span>}
              <span className="text-muted/70">— {t("calendar.quickAddRefine")}</span>
            </button>
          ) : quickText.trim() ? (
            <p className="px-1 text-xs text-muted">{t("calendar.quickAddHint")}</p>
          ) : null}
        </form>
      )}

      {locked && (
        <p className="glass flex items-center gap-2 rounded-xl border-l-[3px] border-l-accent p-3 text-sm text-accent/90">
          <span aria-hidden>🔒</span> {t("calendar.locked")}
        </p>
      )}
      {loading && <p className="text-sm text-muted">{t("common.loading")}</p>}

      {/* Calendar overlays: toggle each calendar's visibility; colours flow into every view. */}
      {!locked && calendars.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {calendars.map((c) => {
            const off = hidden.has(c.id);
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => toggleCalendar(c.id)}
                className={`flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs transition ${
                  off ? "opacity-40" : "hover:bg-surface-2/40"
                }`}
                title={c.is_shared ? (c.owner_name ?? undefined) : undefined}
              >
                <span
                  aria-hidden
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: off ? "transparent" : c.color, boxShadow: `inset 0 0 0 1.5px ${c.color}` }}
                />
                <span className="text-foreground">{c.name}</span>
                {c.is_shared && <span className="text-muted">·</span>}
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setNewCalOpen(true)}
            className="rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted hover:text-accent"
          >
            + {t("calendar.newCalendar")}
          </button>
        </div>
      )}

      {!locked && view !== "month" && (
        <CalendarTimeGrid
          days={days}
          items={gridItems}
          locale={locale}
          onNewAt={(date, hour) => openNew(date, hour)}
          onEventClick={onGridEvent}
          labels={{ allDay: t("calendar.allDay"), sharedReadOnly: t("calendar.sharedReadOnly") }}
        />
      )}

      {!locked && view === "month" && (
        <div className="glass overflow-hidden rounded-2xl">
          <div className="grid grid-cols-7 border-b border-border text-center text-xs text-muted">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
              <div key={d} className="py-2">
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {grid.map((day) => {
              const key = ymd(day);
              const inMonth = day.getMonth() === month;
              const dayItems = visibleItems.filter((it) => localKey(it.start) === key);
              const isToday = key === ymd(new Date());
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => openNew(day)}
                  className={[
                    "flex min-h-24 flex-col gap-1 border-b border-r border-border p-1.5 text-left transition hover:bg-surface-2/40",
                    inMonth ? "" : "opacity-40",
                  ].join(" ")}
                >
                  <span
                    className={[
                      "text-xs",
                      isToday ? "font-semibold text-accent" : "text-muted",
                    ].join(" ")}
                  >
                    {day.getDate()}
                  </span>
                  {dayItems.slice(0, 3).map((it, i) => {
                    const c = it.calendar_id ? colorOf.get(it.calendar_id) : undefined;
                    const colored = it.source === "event" && c;
                    return (
                      <span
                        key={i}
                        title={it.read_only ? t("calendar.sharedReadOnly") : undefined}
                        onClick={(e) => {
                          if (it.source === "event" && it.event_id && !it.read_only) {
                            e.stopPropagation();
                            void openEdit(it.event_id, it.start);
                          } else {
                            e.stopPropagation();
                          }
                        }}
                        style={
                          colored
                            ? it.read_only
                              ? { color: c, border: `1px dashed ${c}80` }
                              : { backgroundColor: `${c}2b`, color: c }
                            : undefined
                        }
                        className={[
                          "truncate rounded px-1.5 py-0.5 text-[11px]",
                          colored
                            ? ""
                            : it.source !== "event"
                              ? "bg-surface-2 text-muted"
                              : it.read_only
                                ? "border border-dashed border-accent/40 text-accent/70"
                                : "bg-accent/20 text-accent",
                        ].join(" ")}
                      >
                        {!it.all_day && `${hm(it.start)} `}
                        {it.label}
                      </span>
                    );
                  })}
                  {dayItems.length > 3 && (
                    <span className="text-[10px] text-muted">+{dayItems.length - 3}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {draft && (
        <EventModal
          draft={draft}
          setDraft={setDraft}
          calendars={ownCalendars}
          onSave={save}
          onDelete={remove}
          onClose={() => setDraft(null)}
        />
      )}

      {shareOpen && ownCalendar && (
        <ShareModal calendarId={ownCalendar.id} onClose={() => setShareOpen(false)} />
      )}

      {newCalOpen && (
        <NewCalendarModal
          onClose={() => setNewCalOpen(false)}
          onCreated={() => {
            setNewCalOpen(false);
            void load();
          }}
        />
      )}
    </main>
  );
}

const CAL_COLORS = ["#00f0ff", "#a3ff00", "#ff2d95", "#ffb020", "#8b5cff", "#ff5c5c", "#00d68f"];

function NewCalendarModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const t = useT();
  const [name, setName] = useState("");
  const [color, setColor] = useState(CAL_COLORS[0]);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await createCalendar(name.trim(), color);
      onCreated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="glass w-full max-w-sm rounded-2xl p-6 shadow-2xl">
        <h2 className="mb-4 text-lg font-semibold text-foreground">{t("calendar.newCalendar")}</h2>
        <input
          autoFocus
          placeholder={t("calendar.calendarName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
        />
        <div className="mt-4 flex flex-wrap gap-2">
          {CAL_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              aria-label={c}
              onClick={() => setColor(c)}
              className={`h-6 w-6 rounded-full transition ${color === c ? "ring-2 ring-offset-2 ring-offset-surface" : ""}`}
              style={{ backgroundColor: c, boxShadow: color === c ? `0 0 0 2px ${c}` : undefined }}
            />
          ))}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border-strong px-4 py-2 text-sm text-muted hover:text-foreground"
          >
            {t("calendar.cancel")}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !name.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
          >
            {t("calendar.save")}
          </button>
        </div>
      </div>
    </div>
  );
}

function ShareModal({ calendarId, onClose }: { calendarId: string; onClose: () => void }) {
  const t = useT();
  const [members, setMembers] = useState<Member[]>([]);
  const [shared, setShared] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([listMembers(), listShares(calendarId)])
      .then(([m, s]) => {
        if (!active) return;
        setMembers(m);
        setShared(new Set(s.map((x: Share) => x.user_id)));
      })
      .catch(() => undefined)
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [calendarId]);

  async function toggle(userId: string, on: boolean) {
    setShared((prev) => {
      const next = new Set(prev);
      if (on) next.add(userId);
      else next.delete(userId);
      return next;
    });
    if (on) await shareCalendar(calendarId, userId);
    else await unshareCalendar(calendarId, userId);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="glass w-full max-w-md rounded-2xl p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-semibold text-foreground">{t("calendar.shareTitle")}</h2>
        <p className="mb-4 text-xs text-muted">{t("calendar.shareSub")}</p>
        {loading ? (
          <p className="text-sm text-muted">{t("common.loading")}</p>
        ) : (
          <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
            {members.map((m) => (
              <label
                key={m.user_id}
                className="flex items-center justify-between rounded-lg px-2 py-2 text-sm hover:bg-surface-2/50"
              >
                <span className="text-foreground">
                  {m.name} <span className="text-muted">· {m.email}</span>
                </span>
                <input
                  type="checkbox"
                  checked={shared.has(m.user_id)}
                  onChange={(e) => void toggle(m.user_id, e.target.checked)}
                />
              </label>
            ))}
          </div>
        )}
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110"
          >
            {t("common.done")}
          </button>
        </div>
      </div>
    </div>
  );
}

function EventModal({
  draft,
  setDraft,
  calendars,
  onSave,
  onDelete,
  onClose,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
  calendars: CalendarRec[];
  onSave: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const t = useT();
  const input =
    "w-full rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent";
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="glass w-full max-w-md rounded-2xl p-6 shadow-2xl">
        <h2 className="mb-4 text-lg font-semibold text-foreground">
          {draft.id ? t("calendar.editEvent") : t("calendar.newEvent")}
        </h2>
        <div className="flex flex-col gap-3">
          <input
            autoFocus
            placeholder={t("calendar.eventTitle")}
            value={draft.title}
            onChange={(e) => set({ title: e.target.value })}
            className={input}
          />
          {calendars.length > 1 && (
            <select
              value={draft.calendarId}
              onChange={(e) => set({ calendarId: e.target.value })}
              className={input}
            >
              {calendars.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
          <input
            placeholder={t("calendar.location")}
            value={draft.location}
            onChange={(e) => set({ location: e.target.value })}
            className={input}
          />
          <textarea
            placeholder={t("calendar.description")}
            value={draft.description}
            onChange={(e) => set({ description: e.target.value })}
            rows={2}
            className={input}
          />
          <input type="date" value={draft.date} onChange={(e) => set({ date: e.target.value })} className={input} />
          {!draft.allDay && (
            <div className="flex gap-3">
              <input type="time" value={draft.start} onChange={(e) => set({ start: e.target.value })} className={input} />
              <input type="time" value={draft.end} onChange={(e) => set({ end: e.target.value })} className={input} />
            </div>
          )}
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={draft.allDay}
              onChange={(e) => set({ allDay: e.target.checked })}
            />
            {t("calendar.allDay")}
          </label>
          {draft.master?.rrule ? (
            <div className="flex gap-4 text-sm text-muted">
              {(["occurrence", "series"] as const).map((s) => (
                <label key={s} className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    checked={draft.scope === s}
                    onChange={() => set({ scope: s })}
                  />
                  {t(s === "occurrence" ? "calendar.thisOccurrence" : "calendar.wholeSeries")}
                </label>
              ))}
            </div>
          ) : (
            <select value={draft.rrule} onChange={(e) => set({ rrule: e.target.value })} className={input}>
              {REPEATS.map((r) => (
                <option key={r.value} value={r.value}>
                  {t(r.key)}
                </option>
              ))}
            </select>
          )}
          <select
            value={draft.reminderMinutes ?? ""}
            onChange={(e) => set({ reminderMinutes: e.target.value ? Number(e.target.value) : null })}
            className={input}
          >
            {REMINDERS.map((r) => (
              <option key={r.value} value={r.value}>
                {t(r.key)}
              </option>
            ))}
          </select>
          {draft.id && (
            <EventAttendees
              eventId={draft.id}
              title={draft.title}
              location={draft.location}
              startISO={
                draft.allDay
                  ? new Date(`${draft.date}T00:00:00`).toISOString()
                  : new Date(`${draft.date}T${draft.start}:00`).toISOString()
              }
              endISO={
                draft.allDay
                  ? new Date(`${draft.date}T23:59:00`).toISOString()
                  : new Date(`${draft.date}T${draft.end}:00`).toISOString()
              }
              allDay={draft.allDay}
            />
          )}
          <p className="flex items-center gap-1.5 text-xs text-accent/80">
            <span aria-hidden>🔒</span> {t("calendar.zkNotice")}
          </p>
        </div>
        <div className="mt-5 flex items-center justify-between">
          {draft.id ? (
            <button type="button" onClick={onDelete} className="text-sm text-red-400 hover:underline">
              {t("calendar.delete")}
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border-strong px-4 py-2 text-sm text-muted hover:text-foreground"
            >
              {t("calendar.cancel")}
            </button>
            <button
              type="button"
              onClick={onSave}
              disabled={!draft.title.trim()}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
            >
              {t("calendar.save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
