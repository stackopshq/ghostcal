// Fantastical-style natural-language quick-add. Runs entirely in the browser (GhostCal is
// zero-knowledge: the parsed title/location are sealed client-side before anything reaches the
// server). Dates/times are parsed by chrono-node in the user's locale; duration, recurrence and
// location are matched with small multilingual patterns (EN/FR).

import * as chrono from "chrono-node";
import type { Locale } from "@/lib/i18n";

export type QuickAddResult = {
  title: string;
  location: string;
  date: string; // YYYY-MM-DD (local)
  start: string; // HH:MM (local, 24h)
  end: string; // HH:MM (local, 24h)
  allDay: boolean;
  rrule: string; // "" or "FREQ=..."
};

const DEFAULT_DURATION_MIN = 60;

function chronoFor(locale: Locale) {
  if (locale === "fr") return chrono.fr;
  return chrono.en;
}

// --- recurrence (returns an RRULE and the matched phrase to strip from the title) ---
const RECUR: { rrule: string; re: RegExp }[] = [
  { rrule: "FREQ=WEEKLY;BYDAY=MO", re: /\b(every monday|mondays|chaque lundi|tous les lundis)\b/i },
  { rrule: "FREQ=WEEKLY;BYDAY=TU", re: /\b(every tuesday|tuesdays|chaque mardi|tous les mardis)\b/i },
  { rrule: "FREQ=WEEKLY;BYDAY=WE", re: /\b(every wednesday|wednesdays|chaque mercredi|tous les mercredis)\b/i },
  { rrule: "FREQ=WEEKLY;BYDAY=TH", re: /\b(every thursday|thursdays|chaque jeudi|tous les jeudis)\b/i },
  { rrule: "FREQ=WEEKLY;BYDAY=FR", re: /\b(every friday|fridays|chaque vendredi|tous les vendredis)\b/i },
  { rrule: "FREQ=WEEKLY;BYDAY=SA", re: /\b(every saturday|saturdays|chaque samedi|tous les samedis)\b/i },
  { rrule: "FREQ=WEEKLY;BYDAY=SU", re: /\b(every sunday|sundays|chaque dimanche|tous les dimanches)\b/i },
  { rrule: "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", re: /\b(every weekday|weekdays|en semaine|chaque jour ouvr\w*)\b/i },
  { rrule: "FREQ=DAILY", re: /\b(every day|everyday|daily|chaque jour|tous les jours)\b/i },
  { rrule: "FREQ=WEEKLY", re: /\b(every week|weekly|chaque semaine|toutes les semaines)\b/i },
  { rrule: "FREQ=MONTHLY", re: /\b(every month|monthly|chaque mois|tous les mois)\b/i },
];

function extractRecurrence(text: string): { rrule: string; text: string } {
  for (const { rrule, re } of RECUR) {
    if (re.test(text)) return { rrule, text: text.replace(re, " ") };
  }
  return { rrule: "", text };
}

// --- duration: "for 90 min", "pendant 2 heures", "for 1h30" ---
const DURATION_RE =
  /\b(?:for|pendant)\s+(\d+)\s*(h|hr|hrs|hour|hours|heure|heures|m|min|mins|minute|minutes|d|day|days|jour|jours)?\b/i;

function extractDuration(text: string): { minutes: number | null; text: string } {
  const m = text.match(DURATION_RE);
  if (!m) return { minutes: null, text };
  const n = Number(m[1]);
  const unit = (m[2] ?? "h").toLowerCase();
  let minutes = n;
  if (/^(h|hr|hrs|hour|hours|heure|heures)$/.test(unit)) minutes = n * 60;
  else if (/^(d|day|days|jour|jours)$/.test(unit)) minutes = n * 60 * 24;
  return { minutes, text: text.replace(DURATION_RE, " ") };
}

// --- location: trailing "at/@/à/en <place>" (chrono already consumed "at <time>") ---
// "en" stays: it is French too ("en salle 3"), not only Spanish.
const LOCATION_RE = /(?:\s@\s?|\s(?:at|à|au|aux|chez|en)\s)([^@]+?)\s*$/i;

function extractLocation(text: string): { location: string; text: string } {
  const m = text.match(LOCATION_RE);
  if (!m) return { location: "", text };
  return { location: m[1].trim(), text: text.replace(LOCATION_RE, " ") };
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}
function ymd(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}
function hm(d: Date): string {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function cleanTitle(text: string): string {
  return text
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s,–-]+|[\s,–-]+$/g, "")
    .replace(/\b(with|avec|con|at|on|for|le|la|les|el|los|the)\s*$/i, "")
    .trim();
}

/** Parse a natural-language string into a draft event, or null if no date/time could be found. */
export function parseQuickAdd(
  input: string,
  locale: Locale,
  ref: Date = new Date(),
): QuickAddResult | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  const recur = extractRecurrence(trimmed);
  const dur = extractDuration(recur.text);
  const results = chronoFor(locale).parse(dur.text, ref, { forwardDate: true });
  if (results.length === 0) return null;
  const r = results[0];

  const startDate = r.start.date();
  const hasTime = r.start.isCertain("hour");
  const allDay = !hasTime;

  let endDate: Date;
  if (r.end) endDate = r.end.date();
  else if (dur.minutes !== null) endDate = new Date(startDate.getTime() + dur.minutes * 60_000);
  else endDate = new Date(startDate.getTime() + DEFAULT_DURATION_MIN * 60_000);

  // Remove the matched date text, then pull out a trailing location; the rest is the title.
  const withoutDate = dur.text.replace(r.text, " ");
  const loc = extractLocation(withoutDate);

  return {
    title: cleanTitle(loc.text),
    location: loc.location,
    date: ymd(startDate),
    start: hm(startDate),
    end: hm(endDate),
    allDay,
    rrule: recur.rrule,
  };
}
