"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import UnlockBanner from "@/components/UnlockBanner";
import { getActiveOrg } from "@/lib/auth";
import {
  type Connection,
  listConnections,
  syncAllCalendars,
} from "@/lib/calendar";
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
import {
  addSubscription,
  deleteSubscription,
  listSubscriptions,
  refreshSubscription,
  type Subscription,
} from "@/lib/subscriptions";
import {
  geocode,
  getForecast,
  type Place,
  saveLocation,
  savedLocation,
  type WeatherDay,
  type WeatherLocation,
  weatherGlyph,
} from "@/lib/weather";
import CalendarAgendaList from "@/components/CalendarAgendaList";
import CalendarTimeGrid, { type GridItem } from "@/components/CalendarTimeGrid";
import CalendarYearGrid from "@/components/CalendarYearGrid";
import EventAttendees from "@/components/EventAttendees";
import { useI18n, useT } from "@/lib/i18n";
import {
  type CalendarLink,
  createLink,
  listLinks,
  refreshLinks,
  revokeLink,
} from "@/lib/links";
import {
  type BusyLink,
  createBusyLink,
  listBusyLinks,
  revokeBusyLink,
} from "@/lib/busy";
import { openInGhostMail } from "@/lib/ghostmail";
import { parseImportUrl, toDraftFields } from "@/lib/importEvent";
import { drainPushQueue } from "@/lib/push";
import { parseQuickAdd, type QuickAddResult } from "@/lib/quickAdd";
import { listMembers, type Member } from "@/lib/team";
import {
  getUnlockedKeys,
  openContent,
  openWithOrgKeys,
  sealContent,
  type EventContent,
} from "@/lib/zk";

const TZ =
  typeof Intl !== "undefined"
    ? Intl.DateTimeFormat().resolvedOptions().timeZone
    : "UTC";
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
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The 42-cell (6×7) grid starting on the Monday on/before the 1st of the month. */
function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7; // Monday-first
  const start = new Date(year, month, 1 - offset);
  return Array.from(
    { length: 42 },
    (_, i) =>
      new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
}

type CalView = "month" | "week" | "day" | "year" | "list";

const CAL_VIEWS: readonly CalView[] = ["month", "week", "day", "year", "list"];

// How far ahead the list view looks. Long enough to be a real answer to "what is next?", short
// enough that the agenda query stays one page.
const LIST_DAYS = 60;

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
function startOfWeek(d: Date): Date {
  return addDays(d, -((d.getDay() + 6) % 7)); // Monday-first
}
/** The visible days for the current view (7 for week, 1 for day; month uses monthGrid). */
function viewDays(view: CalView, cursor: Date): Date[] {
  if (view === "day")
    return [
      new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate()),
    ];
  const start = startOfWeek(cursor);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}
/** The agenda query window [from, to) covering the visible range, with padding for recurrence. */
function viewWindow(view: CalView, cursor: Date): [Date, Date] {
  if (view === "year") {
    return [
      new Date(cursor.getFullYear(), 0, 1),
      new Date(cursor.getFullYear() + 1, 0, 1),
    ];
  }
  if (view === "list") {
    // From today, not from the cursor: a list of what is coming up starts now, whatever month the
    // user was last looking at.
    const today = new Date();
    const s = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    return [s, addDays(s, LIST_DAYS)];
  }
  if (view === "day") {
    const s = new Date(
      cursor.getFullYear(),
      cursor.getMonth(),
      cursor.getDate(),
    );
    return [s, addDays(s, 1)];
  }
  if (view === "week") {
    const s = startOfWeek(cursor);
    return [s, addDays(s, 7)];
  }
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  return [
    addDays(first, -7),
    new Date(cursor.getFullYear(), cursor.getMonth() + 1, 7),
  ];
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
    if (CAL_VIEWS.includes(saved as CalView)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setView(saved as CalView);
    }
  }, []);
  function pickView(v: CalView) {
    setView(v);
    localStorage.setItem("gc_cal_view", v);
  }

  const ownCalendar = useMemo(
    () => calendars.find((c) => !c.is_shared),
    [calendars],
  );
  const ownCalendars = useMemo(
    () => calendars.filter((c) => !c.is_shared),
    [calendars],
  );
  // Where an event can actually be put: calendars you own, plus any shared with you for editing.
  // Offering a calendar you cannot write to would be an affordance that ends in a 403.
  const writableCalendars = useMemo(
    () => calendars.filter((c) => c.can_edit),
    [calendars],
  );
  const colorOf = useMemo(
    () => new Map(calendars.map((c) => [c.id, c.color])),
    [calendars],
  );
  const defaultCalendarId = useMemo(
    () => (ownCalendars.find((c) => c.is_default) ?? ownCalendars[0])?.id ?? "",
    [ownCalendars],
  );
  // Calendars toggled off in the overlay (hidden from the views), persisted per device.
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [newCalOpen, setNewCalOpen] = useState(false);
  const quickRef = useRef<HTMLInputElement>(null);
  // A member may have several external calendars connected. Each is its own overlay, with its own
  // colour — external events carry their connection id in `calendar_id`, the same convention
  // subscriptions use, so there is no special case left for "external" here.
  const [connections, setConnections] = useState<Connection[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [subOpen, setSubOpen] = useState(false);
  const subColorOf = useMemo(
    () => new Map(subscriptions.map((s) => [s.id, s.color])),
    [subscriptions],
  );
  const connColorOf = useMemo(
    () => new Map(connections.map((c) => [c.id, c.color])),
    [connections],
  );
  const [weatherLoc, setWeatherLoc] = useState<WeatherLocation | null>(null);
  const [weather, setWeather] = useState<WeatherDay[]>([]);
  const [weatherOpen, setWeatherOpen] = useState(false);

  // A day → {glyph, tmax, tmin} lookup the month cells and time-grid headers read from.
  const weatherByDay = useMemo(() => {
    const m = new Map<string, { glyph: string; tmax: number; tmin: number }>();
    for (const w of weather) {
      m.set(w.day, {
        glyph: weatherGlyph(w.weather_code),
        tmax: w.temp_max,
        tmin: w.temp_min,
      });
    }
    return m;
  }, [weather]);

  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("gc_cal_hidden") ?? "[]",
      ) as string[];
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

  async function runSync() {
    setSyncing(true);
    try {
      await syncAllCalendars();
      await load();
    } finally {
      setSyncing(false);
    }
  }

  // Restore the saved weather location once on mount (client-only; never persisted server-side).
  useEffect(() => {
    const loc = savedLocation();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (loc) setWeatherLoc(loc);
  }, []);

  // Fetch the forecast whenever a location is set (clearing is handled in the chooser).
  useEffect(() => {
    if (!weatherLoc) return;
    let cancelled = false;
    getForecast(weatherLoc.latitude, weatherLoc.longitude)
      .then((days) => {
        if (!cancelled) setWeather(days);
      })
      .catch(() => {
        if (!cancelled) setWeather([]);
      });
    return () => {
      cancelled = true;
    };
  }, [weatherLoc]);

  function chooseWeatherLocation(loc: WeatherLocation | null) {
    saveLocation(loc);
    setWeatherLoc(loc);
    if (!loc) setWeather([]);
    setWeatherOpen(false);
  }

  async function removeSubscription(id: string) {
    await deleteSubscription(id);
    await load();
  }

  async function resyncSubscription(id: string) {
    setSyncing(true);
    try {
      await refreshSubscription(id);
      await load();
    } finally {
      setSyncing(false);
    }
  }

  // Live natural-language parse of the quick-add box (pure — no effect, no network).
  const quickParsed = useMemo(
    () => (quickText.trim() ? parseQuickAdd(quickText, locale) : null),
    [quickText, locale],
  );

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const grid = useMemo(() => monthGrid(year, month), [year, month]);

  // A changed event dropped every sealed copy a link held of it — they had become lies, and only
  // this browser can remake them. Its own effect rather than part of `load`: it depends on the
  // calendars that `load` itself sets, so folding it in would loop.
  useEffect(() => {
    if (!ownCalendar || locked) return;
    void refreshLinks(ownCalendar.id).catch(() => undefined);
  }, [ownCalendar, locked]);

  const load = useCallback(async () => {
    setLoading(true);
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys) {
      setLocked(true);
      setLoading(false);
      return;
    }
    setLocked(false);

    // Nothing in the background can read an event, so publishing to CalDAV waits for a browser.
    // This is that browser. Fire-and-forget: a phone's server being down is not a reason to hold up
    // the page, and the queue keeps whatever did not land.
    void drainPushQueue().catch(() => undefined);

    const [fromDate, toDate] = viewWindow(view, cursor);
    const from = fromDate.toISOString();
    const to = toDate.toISOString();
    try {
      const [cals, agenda, conns, subs] = await Promise.all([
        listCalendars(),
        getAgenda(from, to),
        listConnections().catch(() => []),
        listSubscriptions().catch(() => []),
      ]);
      setConnections(conns);
      setCalendars(cals);
      setSubscriptions(subs);
      const cache = new Map<string, string>();
      const decorated: DecoratedItem[] = [];
      for (const it of agenda) {
        let label = it.title ?? t("calendar.busy");
        if (it.source === "event" && it.content) {
          let title = cache.get(it.content);
          if (title === undefined) {
            try {
              title =
                (await openWithOrgKeys(keys, it.content, openContent)).title ||
                t("calendar.untitled");
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
    void load();
  }, [load]);

  // Deep links from the sibling apps. Two doors, because they carry different things:
  //
  //   ?add=<text>   — a sentence spotted in an email. Pre-fills the quick-add box, which is exactly
  //                   what a sentence deserves.
  //   ?import=1&…   — a structured event (an .ics attachment, a meeting invitation). Opens the event
  //                   form, because a sentence cannot carry an end time, a location and a recurrence
  //                   rule, and re-parsing prose would throw away what the sender stated exactly.
  //
  // Neither saves anything. The user reviews, confirms, and the event is sealed in this browser.
  useEffect(() => {
    const imported = parseImportUrl(window.location.search);
    if (imported) {
      const fields = toDraftFields(imported);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDraft({
        id: null,
        calendarId: defaultCalendarId,
        ...fields,
        reminderMinutes: null,
        master: null,
        occStart: null,
        scope: "series",
      });
      history.replaceState(null, "", window.location.pathname);
      return;
    }

    const add = new URLSearchParams(window.location.search).get("add");
    if (add) {
      setQuickText(add);
      requestAnimationFrame(() => quickRef.current?.focus());
      history.replaceState(null, "", window.location.pathname);
    } else if (window.location.hash === "#new") {
      requestAnimationFrame(() => quickRef.current?.focus());
      history.replaceState(null, "", window.location.pathname);
    }
  }, [defaultCalendarId]);

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
      else if (k === "y") pickView("year");
      else if (k === "a") pickView("list");
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
    if (it.source === "event" && it.event_id && !it.read_only)
      void openEdit(it.event_id, it.start);
  }

  async function openEdit(eventId: string, occStartIso: string) {
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys) return;
    const ev = await getEvent(eventId);
    let content: EventContent = { title: "", description: "", location: "" };
    if (ev.content) {
      try {
        content = await openWithOrgKeys(keys, ev.content, openContent);
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
    const t24 = (d: Date) =>
      d.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
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
      {
        title: draft.title,
        description: draft.description,
        location: draft.location,
      },
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

    const editingOneOccurrence =
      draft.id && draft.master?.rrule && draft.scope === "occurrence";
    if (!draft.id) {
      await createEvent({ ...detached, rrule: draft.rrule || null });
    } else if (editingOneOccurrence && draft.master && draft.occStart) {
      // Exclude this occurrence from the series, then add the edited standalone event.
      await updateEvent(
        draft.id,
        masterWithExdate(draft.master, draft.occStart),
      );
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
      await updateEvent(
        draft.id,
        masterWithExdate(draft.master, draft.occStart),
      );
    } else {
      await deleteEvent(draft.id);
    }
    setDraft(null);
    await load();
  }

  const days = useMemo(() => viewDays(view, cursor), [view, cursor]);
  const headerLabel =
    view === "year"
      ? String(cursor.getFullYear())
      : view === "list"
        ? t("calendar.upcoming")
        : view === "month"
          ? cursor.toLocaleDateString(locale, {
              month: "long",
              year: "numeric",
            })
          : view === "day"
            ? cursor.toLocaleDateString(locale, {
                weekday: "long",
                month: "long",
                day: "numeric",
              })
            : `${days[0].toLocaleDateString(locale, { month: "short", day: "numeric" })} – ${days[6].toLocaleDateString(locale, { month: "short", day: "numeric" })}`;

  function step(dir: -1 | 1) {
    if (view === "list") return; // "what is next?" has no previous page
    if (view === "year") setCursor(new Date(cursor.getFullYear() + dir, 0, 1));
    else if (view === "month") setCursor(new Date(year, month + dir, 1));
    else if (view === "week") setCursor(addDays(cursor, 7 * dir));
    else setCursor(addDays(cursor, dir));
  }

  // Every source now identifies itself the same way — `calendar_id` carries the id of whatever it
  // came from (a calendar, a connected account, a subscription) — so hiding and colouring are one
  // rule rather than three.
  const visibleItems = useMemo(
    () => items.filter((it) => !it.calendar_id || !hidden.has(it.calendar_id)),
    [items, hidden],
  );
  const colorFor = (it: DecoratedItem): string | undefined => {
    if (!it.calendar_id) return undefined;
    if (it.source === "external") return connColorOf.get(it.calendar_id);
    if (it.source === "subscription") return subColorOf.get(it.calendar_id);
    return colorOf.get(it.calendar_id);
  };
  const gridItems: GridItem[] = visibleItems.map((it) => ({
    ...it,
    color: colorFor(it),
  }));

  const quickPreview = quickParsed
    ? {
        date: new Date(
          `${quickParsed.date}T${quickParsed.allDay ? "00:00" : quickParsed.start}:00`,
        ).toLocaleDateString(locale, {
          weekday: "short",
          month: "short",
          day: "numeric",
        }),
        time: quickParsed.allDay
          ? t("calendar.allDay")
          : `${quickParsed.start}–${quickParsed.end}`,
      }
    : null;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-5 p-6 sm:p-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold capitalize text-foreground">
            {headerLabel}
          </h1>
          <p className="mt-1 text-sm text-muted">{t("calendar.sub")}</p>
        </div>
        {/* `flex-wrap` ici AUSSI, pas seulement sur le parent. Le parent l'avait
            déjà : il déplaçait donc cette barre sur sa propre ligne — sans la
            rétrécir. Cinq boutons de vue, trois de navigation et « Partager »
            forment un bloc insécable d'environ 640 px, qui élargit le CORPS DE
            PAGE sur un téléphone de 390.

            Le symptôme est reconnaissable et trompeur : le fond de l'en-tête
            s'arrête au milieu de l'écran, là où la fenêtre finissait avant que
            la page ne s'élargisse. On croit à un défaut de l'en-tête ; il est
            ailleurs, plus bas.

            `w-full sm:w-auto` pour qu'elle prenne sa ligne entière en mobile au
            lieu de rester collée à droite. */}
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
          {/* Sélecteur de vue — il DÉFILE au lieu de se replier. Un contrôle
              segmenté qui passe à la ligne casse sa bordure commune et cesse de
              ressembler à un sélecteur ; le faire défiler garde la forme. */}
          <div className="flex max-w-full overflow-x-auto rounded-lg border border-border-strong">
            {CAL_VIEWS.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => pickView(v)}
                className={`shrink-0 whitespace-nowrap px-2.5 py-1.5 text-sm transition sm:px-3 ${
                  view === v
                    ? "bg-accent text-accent-ink"
                    : "text-muted hover:text-accent"
                }`}
              >
                {t(`calendar.view${v[0].toUpperCase()}${v.slice(1)}`)}
              </button>
            ))}
          </div>
          {/* The list view starts from today and runs forwards: paging it has no meaning, and a
              control that does nothing is worse than no control. */}
          {view !== "list" && (
            <>
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
            </>
          )}
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
              {quickParsed.location && (
                <span className="text-muted">· {quickParsed.location}</span>
              )}
              {quickParsed.rrule && <span className="text-muted">· ↻</span>}
              <span className="text-muted/70">
                — {t("calendar.quickAddRefine")}
              </span>
            </button>
          ) : quickText.trim() ? (
            <p className="px-1 text-xs text-muted">
              {t("calendar.quickAddHint")}
            </p>
          ) : null}
        </form>
      )}

      {locked && <UnlockBanner />}
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
                  style={{
                    backgroundColor: off ? "transparent" : c.color,
                    boxShadow: `inset 0 0 0 1.5px ${c.color}`,
                  }}
                />
                <span className="text-foreground">{c.name}</span>
                {/* A bare dot said nothing. Two people's default calendars are both "My calendar",
                    so a shared one has to name its owner to be tellable apart at a glance. */}
                {c.is_shared && (
                  <span className="text-muted">· {c.owner_name}</span>
                )}
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

          {/* Each connected account is its own toggleable overlay. */}
          {connections.length > 0 ? (
            <>
              {connections.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => toggleCalendar(c.id)}
                  className={`flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs transition ${
                    hidden.has(c.id) ? "opacity-40" : "hover:bg-surface-2/40"
                  }`}
                  title={`${c.username}@${c.server_url}`}
                >
                  <span
                    aria-hidden
                    className="h-2.5 w-2.5 rounded-full"
                    style={{
                      backgroundColor: hidden.has(c.id)
                        ? "transparent"
                        : c.color,
                      boxShadow: `inset 0 0 0 1.5px ${c.color}`,
                    }}
                  />
                  <span className="text-foreground">
                    {c.calendar_name || t("calendar.externalCalendar")}
                  </span>
                </button>
              ))}
              <button
                type="button"
                onClick={runSync}
                disabled={syncing}
                className="rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted hover:text-accent disabled:opacity-50"
              >
                {syncing ? t("common.saving") : `↻ ${t("calendar.syncNow")}`}
              </button>
            </>
          ) : (
            <Link
              href="/dashboard/settings"
              className="rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted hover:text-accent"
            >
              + {t("calendar.connectExternal")}
            </Link>
          )}

          {/* Public ICS subscriptions: each a toggleable, read-only overlay (holidays, fixtures…). */}
          {subscriptions.map((s) => {
            const off = hidden.has(s.id);
            const errored = s.status === "error";
            return (
              <span
                key={s.id}
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition ${
                  errored ? "border-danger/50" : "border-border"
                } ${off ? "opacity-40" : ""}`}
                title={
                  errored
                    ? (s.last_error ?? undefined)
                    : (s.last_synced_at ?? undefined)
                }
              >
                <button
                  type="button"
                  onClick={() => toggleCalendar(s.id)}
                  className="flex items-center gap-1.5 hover:text-accent"
                >
                  <span
                    aria-hidden
                    className="h-2.5 w-2.5 rounded-full"
                    style={{
                      backgroundColor: off ? "transparent" : s.color,
                      boxShadow: `inset 0 0 0 1.5px ${s.color}`,
                    }}
                  />
                  <span className="text-foreground">{s.name}</span>
                  {errored && <span aria-hidden>⚠</span>}
                </button>
                <button
                  type="button"
                  onClick={() => void resyncSubscription(s.id)}
                  disabled={syncing}
                  title={t("calendar.syncNow")}
                  className="text-muted hover:text-accent disabled:opacity-50"
                >
                  ↻
                </button>
                <button
                  type="button"
                  onClick={() => void removeSubscription(s.id)}
                  title={t("common.delete")}
                  className="text-muted hover:text-danger"
                >
                  ×
                </button>
              </span>
            );
          })}
          <button
            type="button"
            onClick={() => setSubOpen(true)}
            className="rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted hover:text-accent"
          >
            + {t("calendar.subscribe")}
          </button>

          {/* Weather: pick a location (client-side only) to overlay the daily forecast. */}
          {weatherLoc ? (
            <span className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs">
              <button
                type="button"
                onClick={() => setWeatherOpen(true)}
                className="flex items-center gap-1 text-foreground hover:text-accent"
              >
                <span aria-hidden>📍</span>
                {weatherLoc.name}
              </button>
              <button
                type="button"
                onClick={() => chooseWeatherLocation(null)}
                title={t("common.delete")}
                className="text-muted hover:text-danger"
              >
                ×
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setWeatherOpen(true)}
              className="rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted hover:text-accent"
            >
              + {t("calendar.weather")}
            </button>
          )}
        </div>
      )}

      {subOpen && (
        <SubscribeModal onClose={() => setSubOpen(false)} onDone={load} t={t} />
      )}
      {weatherOpen && (
        <WeatherModal
          current={weatherLoc}
          onClose={() => setWeatherOpen(false)}
          onChoose={chooseWeatherLocation}
          t={t}
        />
      )}

      {!locked && (view === "week" || view === "day") && (
        <CalendarTimeGrid
          days={days}
          items={gridItems}
          locale={locale}
          onNewAt={(date, hour) => openNew(date, hour)}
          onEventClick={onGridEvent}
          labels={{
            allDay: t("calendar.allDay"),
            sharedReadOnly: t("calendar.sharedReadOnly"),
          }}
          weatherByDay={weatherByDay}
        />
      )}

      {!locked && view === "year" && (
        <CalendarYearGrid
          year={cursor.getFullYear()}
          items={gridItems}
          locale={locale}
          todayLabel={t("calendar.today")}
          onPickDay={(day) => {
            setCursor(day);
            pickView("day");
          }}
        />
      )}

      {!locked && view === "list" && (
        <CalendarAgendaList
          items={gridItems}
          locale={locale}
          onEventClick={onGridEvent}
          labels={{
            allDay: t("calendar.allDay"),
            empty: t("calendar.nothingAhead"),
            sharedReadOnly: t("calendar.sharedReadOnly"),
          }}
        />
      )}

      {!locked && view === "month" && (
        <div className="glass overflow-hidden rounded-2xl">
          <div className="grid grid-cols-7 border-b border-border text-center text-xs text-muted">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
              <div key={d} className="py-2">
                <span className="hidden md:inline">{d}</span>
                <span className="md:hidden">{d[0]}</span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {grid.map((day) => {
              const key = ymd(day);
              const inMonth = day.getMonth() === month;
              const dayItems = visibleItems.filter(
                (it) => localKey(it.start) === key,
              );
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
                  <span className="flex flex-wrap items-center justify-between gap-3">
                    <span
                      className={[
                        "text-xs",
                        isToday ? "font-semibold text-accent" : "text-muted",
                      ].join(" ")}
                    >
                      {day.getDate()}
                    </span>
                    {weatherByDay.get(key) && (
                      <span
                        className="text-[10px] text-muted"
                        title={`${Math.round(weatherByDay.get(key)!.tmin)}° / ${Math.round(weatherByDay.get(key)!.tmax)}°`}
                      >
                        <span aria-hidden>{weatherByDay.get(key)!.glyph}</span>{" "}
                        {Math.round(weatherByDay.get(key)!.tmax)}°
                      </span>
                    )}
                  </span>
                  {dayItems.slice(0, 3).map((it, i) => {
                    const c = colorFor(it);
                    const outlined = it.read_only || it.source === "external";
                    return (
                      <span
                        key={i}
                        title={
                          it.read_only
                            ? t("calendar.sharedReadOnly")
                            : undefined
                        }
                        onClick={(e) => {
                          if (
                            it.source === "event" &&
                            it.event_id &&
                            !it.read_only
                          ) {
                            e.stopPropagation();
                            void openEdit(it.event_id, it.start);
                          } else {
                            e.stopPropagation();
                          }
                        }}
                        style={
                          c
                            ? outlined
                              ? { color: c, border: `1px dashed ${c}80` }
                              : { backgroundColor: `${c}2b`, color: c }
                            : undefined
                        }
                        className={[
                          "truncate rounded px-1.5 py-0.5 text-[11px]",
                          c
                            ? ""
                            : it.source !== "event"
                              ? "bg-surface-2 text-muted"
                              : "bg-accent/20 text-accent",
                        ].join(" ")}
                      >
                        {!it.all_day && `${hm(it.start)} `}
                        {it.label}
                      </span>
                    );
                  })}
                  {dayItems.length > 3 && (
                    <span className="text-[10px] text-muted">
                      +{dayItems.length - 3}
                    </span>
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
          calendars={writableCalendars}
          onSave={save}
          onDelete={remove}
          onClose={() => setDraft(null)}
        />
      )}

      {shareOpen && ownCalendar && (
        <ShareModal
          calendarId={ownCalendar.id}
          onClose={() => setShareOpen(false)}
        />
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

const CAL_COLORS = [
  "#00f0ff",
  "#a3ff00",
  "#ff2d95",
  "#ffb020",
  "#8b5cff",
  "#ff5c5c",
  "#00d68f",
];

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
        <h2 className="mb-4 text-lg font-semibold text-foreground">
          {t("calendar.newCalendar")}
        </h2>
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
              style={{
                backgroundColor: c,
                boxShadow: color === c ? `0 0 0 2px ${c}` : undefined,
              }}
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

function SubscribeModal({
  onClose,
  onDone,
  t,
}: {
  onClose: () => void;
  onDone: () => Promise<void> | void;
  t: (key: string) => string;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [color, setColor] = useState(CAL_COLORS[4]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!name.trim() || !url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addSubscription({ name: name.trim(), url: url.trim(), color });
      await onDone();
      onClose();
    } catch {
      // The feed is validated server-side; a bad/unreachable URL comes back as an error.
      setError(t("calendar.subscribeError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="glass w-full max-w-sm rounded-2xl p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-semibold text-foreground">
          {t("calendar.subscribe")}
        </h2>
        <p className="mb-4 text-xs text-muted">{t("calendar.subscribeHint")}</p>
        <input
          autoFocus
          placeholder={t("calendar.calendarName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
        />
        <input
          type="url"
          inputMode="url"
          placeholder="https://example.com/calendar.ics"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="mt-3 w-full rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
        />
        <div className="mt-4 flex flex-wrap gap-2">
          {CAL_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              aria-label={c}
              onClick={() => setColor(c)}
              className={`h-6 w-6 rounded-full transition ${color === c ? "ring-2 ring-offset-2 ring-offset-surface" : ""}`}
              style={{
                backgroundColor: c,
                boxShadow: color === c ? `0 0 0 2px ${c}` : undefined,
              }}
            />
          ))}
        </div>
        {error && <p className="mt-3 text-xs text-danger">{error}</p>}
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
            disabled={busy || !name.trim() || !url.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
          >
            {busy ? t("common.saving") : t("calendar.save")}
          </button>
        </div>
      </div>
    </div>
  );
}

function WeatherModal({
  current,
  onClose,
  onChoose,
  t,
}: {
  current: WeatherLocation | null;
  onClose: () => void;
  onChoose: (loc: WeatherLocation | null) => void;
  t: (key: string) => string;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [busy, setBusy] = useState(false);
  const [geoBusy, setGeoBusy] = useState(false);

  async function search() {
    if (query.trim().length < 2) return;
    setBusy(true);
    try {
      setResults(await geocode(query.trim()));
    } catch {
      setResults([]);
    } finally {
      setBusy(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) return;
    setGeoBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoBusy(false);
        onChoose({
          name: t("calendar.weatherMyLocation"),
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
        });
      },
      () => setGeoBusy(false),
      { timeout: 8000 },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="glass w-full max-w-sm rounded-2xl p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-semibold text-foreground">
          {t("calendar.weather")}
        </h2>
        <p className="mb-4 text-xs text-muted">{t("calendar.weatherHint")}</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
          className="flex gap-2"
        >
          <input
            autoFocus
            placeholder={t("calendar.weatherSearch")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={busy || query.trim().length < 2}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
          >
            {busy ? "…" : t("calendar.weatherSearchGo")}
          </button>
        </form>

        {results.length > 0 && (
          <ul className="mt-3 max-h-52 overflow-y-auto">
            {results.map((p, i) => (
              <li key={`${p.latitude},${p.longitude},${i}`}>
                <button
                  type="button"
                  onClick={() =>
                    onChoose({
                      name: p.name,
                      latitude: p.latitude,
                      longitude: p.longitude,
                    })
                  }
                  className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface-2/40"
                >
                  <span className="text-foreground">{p.name}</span>
                  {p.country && (
                    <span className="text-xs text-muted">{p.country}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-5 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={useMyLocation}
            disabled={geoBusy}
            className="rounded-lg border border-border-strong px-3 py-2 text-xs text-muted hover:text-accent disabled:opacity-60"
          >
            {geoBusy ? "…" : `📍 ${t("calendar.weatherMyLocation")}`}
          </button>
          <div className="flex gap-2">
            {current && (
              <button
                type="button"
                onClick={() => onChoose(null)}
                className="rounded-lg border border-border-strong px-3 py-2 text-xs text-muted hover:text-danger"
              >
                {t("calendar.weatherTurnOff")}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border-strong px-3 py-2 text-xs text-muted hover:text-foreground"
            >
              {t("calendar.cancel")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** What a colleague may do with a shared calendar. */
type Access = "none" | "read" | "edit";

function ShareModal({
  calendarId,
  onClose,
}: {
  calendarId: string;
  onClose: () => void;
}) {
  const t = useT();
  // Sharing outside the organization is a different animal: the recipient has no account and no org
  // key. A link carries its own key, in the URL fragment, which never reaches the server (ADR-0009).
  const [links, setLinks] = useState<CalendarLink[]>([]);
  const [linkName, setLinkName] = useState("");
  const [minting, setMinting] = useState(false);
  // Shown exactly once. The token is not retrievable (the server keeps a hash) and the key was never
  // sent anywhere — so if it is lost, the answer is a new link, not a recovery.
  const [freshLink, setFreshLink] = useState<string | null>(null);
  // A free-busy link is a different promise, and the UI must not let the two blur: it shows WHEN
  // this person is busy and never WHAT they are doing, so it carries no key and has no fragment.
  const [busyLinks, setBusyLinks] = useState<BusyLink[]>([]);
  const [busyName, setBusyName] = useState("");
  const [freshBusyLink, setFreshBusyLink] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  // Three states per colleague, not two: not shared, read-only, read-write.
  const [access, setAccess] = useState<Map<string, Access>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([listMembers(), listShares(calendarId), listBusyLinks()])
      .then(([m, s, b]) => {
        if (!active) return;
        setMembers(m);
        setBusyLinks(b);
        setAccess(
          new Map(
            s.map(
              (x: Share) => [x.user_id, x.can_edit ? "edit" : "read"] as const,
            ),
          ),
        );
      })
      .catch(() => undefined)
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [calendarId]);

  async function setAccessFor(userId: string, next: Access) {
    setAccess((prev) => {
      const map = new Map(prev);
      if (next === "none") map.delete(userId);
      else map.set(userId, next);
      return map;
    });
    // Re-sharing is how a grant is changed: the server upserts, so a downgrade to read-only takes
    // effect rather than quietly doing nothing.
    if (next === "none") await unshareCalendar(calendarId, userId);
    else await shareCalendar(calendarId, userId, next === "edit");
  }

  async function mintLink() {
    setMinting(true);
    try {
      setFreshLink(await createLink(calendarId, linkName.trim()));
      setLinkName("");
      setLinks(await listLinks(calendarId));
    } finally {
      setMinting(false);
    }
  }

  async function dropLink(id: string) {
    await revokeLink(id);
    setLinks(await listLinks(calendarId));
  }

  // No keypair to generate, and nothing to seal afterwards: this link shows only what the server
  // already knows. Minting it is one POST, and that is the whole story.
  async function mintBusyLink() {
    setFreshBusyLink(await createBusyLink(busyName.trim()));
    setBusyName("");
    setBusyLinks(await listBusyLinks());
  }

  async function dropBusyLink(id: string) {
    await revokeBusyLink(id);
    setBusyLinks(await listBusyLinks());
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="glass max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-semibold text-foreground">
          {t("calendar.shareTitle")}
        </h2>
        <p className="mb-4 text-xs text-muted">{t("calendar.shareSub")}</p>
        {loading ? (
          <p className="text-sm text-muted">{t("common.loading")}</p>
        ) : (
          <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
            {members.map((m) => (
              <div
                key={m.user_id}
                className="flex items-center justify-between gap-3 rounded-lg px-2 py-2 text-sm"
              >
                <span className="min-w-0 flex-1 truncate text-foreground">
                  {m.name} <span className="text-muted">· {m.email}</span>
                </span>
                <select
                  value={access.get(m.user_id) ?? "none"}
                  onChange={(e) =>
                    void setAccessFor(m.user_id, e.target.value as Access)
                  }
                  className="rounded-lg border border-border bg-surface-2 px-2 py-1 text-xs text-foreground"
                >
                  <option value="none">{t("calendar.shareNone")}</option>
                  <option value="read">{t("calendar.shareRead")}</option>
                  <option value="edit">{t("calendar.shareEdit")}</option>
                </select>
              </div>
            ))}
          </div>
        )}
        <section className="mt-6 border-t border-border pt-5">
          <h3 className="text-sm font-medium text-foreground">
            {t("calendar.linkTitle")}
          </h3>
          <p className="mt-1 text-xs text-muted">{t("calendar.linkSub")}</p>

          {freshLink && (
            <div className="mt-3 rounded-lg border border-accent/40 bg-accent/5 p-3">
              <p className="text-xs text-accent">{t("calendar.linkOnce")}</p>
              <code className="mt-2 block break-all text-xs text-foreground">
                {freshLink}
              </code>
              <button
                type="button"
                onClick={() => void navigator.clipboard.writeText(freshLink)}
                className="mt-2 rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent"
              >
                {t("calendar.linkCopy")}
              </button>
            </div>
          )}

          {links.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1">
              {links.map((link) => (
                <li
                  key={link.id}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate text-foreground">
                    {link.name || t("calendar.linkUnnamed")}
                    {link.pending > 0 && (
                      <span className="ml-2 text-xs text-muted">
                        {t("calendar.linkPending").replace(
                          "{n}",
                          String(link.pending),
                        )}
                      </span>
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => void dropLink(link.id)}
                    className="shrink-0 text-xs text-muted transition hover:text-red-400"
                  >
                    {t("calendar.linkRevoke")}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-3 flex gap-2">
            <input
              value={linkName}
              onChange={(e) => setLinkName(e.target.value)}
              placeholder={t("calendar.linkNamePh")}
              className="flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-foreground placeholder:text-muted"
            />
            <button
              type="button"
              onClick={() => void mintLink()}
              disabled={minting}
              className="shrink-0 rounded-lg border border-border-strong px-3 py-2 text-sm text-muted transition hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {minting ? t("common.saving") : t("calendar.linkCreate")}
            </button>
          </div>
        </section>

        {/* Availability. Not a calendar link with the titles left off — a different thing, sharing
            strictly what the server already knows, and it should be presented as such. */}
        <section className="mt-6 border-t border-border pt-5">
          <h3 className="text-sm font-medium text-foreground">
            {t("calendar.busyTitle")}
          </h3>
          <p className="mt-1 text-xs text-muted">{t("calendar.busySub")}</p>

          {freshBusyLink && (
            <div className="mt-3 rounded-lg border border-accent/40 bg-accent/5 p-3">
              <p className="text-xs text-accent">{t("calendar.linkOnce")}</p>
              <code className="mt-2 block break-all text-xs text-foreground">
                {freshBusyLink}
              </code>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() =>
                    void navigator.clipboard.writeText(freshBusyLink)
                  }
                  className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent"
                >
                  {t("calendar.linkCopy")}
                </button>
                {/* Only here, and only now: the token is shown exactly once, so this is the one
                    moment at which a link exists to send. Offering it beside a saved link would be
                    offering something we cannot produce. */}
                <button
                  type="button"
                  onClick={() =>
                    openInGhostMail({
                      to: [],
                      subject: t("calendar.busyEmailSubject"),
                      body: t("calendar.busyEmailBody").replace(
                        "{url}",
                        freshBusyLink,
                      ),
                    })
                  }
                  className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition hover:text-accent"
                >
                  ✉ {t("calendar.busyEmail")}
                </button>
              </div>
            </div>
          )}

          {busyLinks.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1">
              {busyLinks.map((link) => (
                <li
                  key={link.id}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate text-foreground">
                    {link.name || t("calendar.linkUnnamed")}
                  </span>
                  <button
                    type="button"
                    onClick={() => void dropBusyLink(link.id)}
                    className="shrink-0 text-xs text-muted transition hover:text-red-400"
                  >
                    {t("calendar.linkRevoke")}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-3 flex gap-2">
            <input
              value={busyName}
              onChange={(e) => setBusyName(e.target.value)}
              placeholder={t("calendar.busyNamePh")}
              className="flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-foreground placeholder:text-muted"
            />
            <button
              type="button"
              onClick={() => void mintBusyLink()}
              className="shrink-0 rounded-lg border border-border-strong px-3 py-2 text-sm text-muted transition hover:border-accent hover:text-accent"
            >
              {t("calendar.linkCreate")}
            </button>
          </div>
        </section>

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
                  {/* Two people's default calendars are both called "My calendar". Once a shared one
                      can be written to, the picker has to say whose it is. */}
                  {c.is_shared ? `${c.name} · ${c.owner_name}` : c.name}
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
          <input
            type="date"
            value={draft.date}
            onChange={(e) => set({ date: e.target.value })}
            className={input}
          />
          {!draft.allDay && (
            <div className="flex gap-3">
              <input
                type="time"
                value={draft.start}
                onChange={(e) => set({ start: e.target.value })}
                className={input}
              />
              <input
                type="time"
                value={draft.end}
                onChange={(e) => set({ end: e.target.value })}
                className={input}
              />
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
                  {t(
                    s === "occurrence"
                      ? "calendar.thisOccurrence"
                      : "calendar.wholeSeries",
                  )}
                </label>
              ))}
            </div>
          ) : (
            <select
              value={draft.rrule}
              onChange={(e) => set({ rrule: e.target.value })}
              className={input}
            >
              {REPEATS.map((r) => (
                <option key={r.value} value={r.value}>
                  {t(r.key)}
                </option>
              ))}
            </select>
          )}
          <select
            value={draft.reminderMinutes ?? ""}
            onChange={(e) =>
              set({
                reminderMinutes: e.target.value ? Number(e.target.value) : null,
              })
            }
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
            <button
              type="button"
              onClick={onDelete}
              className="text-sm text-red-400 hover:underline"
            >
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
