"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getActiveOrg } from "@/lib/auth";
import {
  type AgendaItem,
  type CalendarRec,
  createEvent,
  deleteEvent,
  type EventDetail,
  type EventInput,
  getAgenda,
  getEvent,
  listCalendars,
  updateEvent,
} from "@/lib/agenda";
import { useT } from "@/lib/i18n";
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

export default function CalendarPage() {
  const t = useT();
  const [cursor, setCursor] = useState(() => new Date());
  const [items, setItems] = useState<DecoratedItem[]>([]);
  const [calendars, setCalendars] = useState<CalendarRec[]>([]);
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState<Draft | null>(null);

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
    const from = new Date(year, month, 1 - 7).toISOString();
    const to = new Date(year, month + 1, 7).toISOString();
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
  }, [year, month, t]);

  useEffect(() => {
    // Data-loading effect: load() toggles the loading flag and fills state from the API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  function openNew(date: Date) {
    if (locked) return;
    setDraft({
      id: null,
      title: "",
      description: "",
      location: "",
      date: ymd(date),
      start: "09:00",
      end: "10:00",
      allDay: false,
      rrule: "",
      reminderMinutes: null,
      master: null,
      occStart: null,
      scope: "series",
    });
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
      calendar_id: calendars[0]?.id ?? "",
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

  const monthLabel = cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-5 p-6 sm:p-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold capitalize text-foreground">{monthLabel}</h1>
          <p className="mt-1 text-sm text-muted">{t("calendar.sub")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCursor(new Date(year, month - 1, 1))}
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
            onClick={() => setCursor(new Date(year, month + 1, 1))}
            className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-muted hover:text-accent"
          >
            ›
          </button>
        </div>
      </div>

      {locked && (
        <p className="glass flex items-center gap-2 rounded-xl border-l-[3px] border-l-accent p-3 text-sm text-accent/90">
          <span aria-hidden>🔒</span> {t("calendar.locked")}
        </p>
      )}
      {loading && <p className="text-sm text-muted">{t("common.loading")}</p>}

      {!locked && (
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
              const dayItems = items.filter((it) => localKey(it.start) === key);
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
                  {dayItems.slice(0, 3).map((it, i) => (
                    <span
                      key={i}
                      onClick={(e) => {
                        if (it.source === "event" && it.event_id) {
                          e.stopPropagation();
                          void openEdit(it.event_id, it.start);
                        }
                      }}
                      className={[
                        "truncate rounded px-1.5 py-0.5 text-[11px]",
                        it.source === "event"
                          ? "bg-accent/20 text-accent"
                          : "bg-surface-2 text-muted",
                      ].join(" ")}
                    >
                      {!it.all_day && `${hm(it.start)} `}
                      {it.label}
                    </span>
                  ))}
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
          onSave={save}
          onDelete={remove}
          onClose={() => setDraft(null)}
        />
      )}
    </main>
  );
}

function EventModal({
  draft,
  setDraft,
  onSave,
  onDelete,
  onClose,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
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
