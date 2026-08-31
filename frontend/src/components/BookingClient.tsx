"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  createBooking,
  getAvailability,
  type Booking,
  type BookingQuestion,
  type EventType,
  type Slot,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { sealInviteePrivate } from "@/lib/zk";
import {
  LockIcon,
} from "@/components/icons";

const LOCATION_LABELS: Record<string, string> = {
  google_meet: "Google Meet",
  ms_teams: "Microsoft Teams",
  zoom: "Zoom",
  in_person: "In person",
  phone: "Phone",
  custom: "Custom",
};

function dayKey(iso: string, tz: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
}

function dayLabel(iso: string, tz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

function timeLabel(iso: string, tz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

function addDays(days: number): Date {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d;
}

function listTimezones(fallback: string): string[] {
  const fn = (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
  try {
    return fn ? fn("timeZone") : [fallback];
  } catch {
    return [fallback];
  }
}

function parseEmails(raw: string): string[] {
  return raw
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function BookingClient({
  org,
  event,
  eventType,
}: {
  org: string;
  event: string;
  eventType: EventType;
}) {
  const t = useT();
  const detectedTz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);
  const timezones = useMemo(() => listTimezones(detectedTz), [detectedTz]);
  const [tz, setTz] = useState(detectedTz);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [guests, setGuests] = useState("");
  const [notes, setNotes] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<Booking | null>(null);

  useEffect(() => {
    const from = dayKey(new Date().toISOString(), tz);
    const to = dayKey(addDays(14).toISOString(), tz);
    getAvailability(org, event, from, to)
      .then((res) => setSlots(res.slots))
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [org, event, tz]);

  function setAnswer(id: string, value: string) {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  }

  function missingRequired(): boolean {
    return eventType.questions.some((q) => q.required && !(answers[q.id] ?? "").trim());
  }

  const byDay = useMemo(() => {
    const map = new Map<string, Slot[]>();
    for (const slot of slots) {
      const key = dayKey(slot.start, tz);
      (map.get(key) ?? map.set(key, []).get(key)!).push(slot);
    }
    return map;
  }, [slots, tz]);

  const days = useMemo(() => [...byDay.keys()].sort(), [byDay]);
  const activeDay = selectedDay ?? days[0] ?? null;
  const daySlots = activeDay ? (byDay.get(activeDay) ?? []) : [];

  async function confirm() {
    if (!selectedSlot) return;
    setSubmitting(true);
    setBookingError(null);
    try {
      // Zero-knowledge: seal the name, answers and notes to the org public key in the browser. The
      // server receives only ciphertext (and the email it needs to send confirmations).
      const invitee_private = eventType.zk_public_key
        ? await sealInviteePrivate({ name, answers, notes }, eventType.zk_public_key)
        : null;
      const booking = await createBooking(org, event, {
        start_at: selectedSlot.start,
        invitee_email: email,
        invitee_timezone: tz,
        guest_emails: parseEmails(guests),
        invitee_private,
      });
      if (eventType.redirect_url) {
        window.location.href = eventType.redirect_url;
        return;
      }
      setConfirmation(booking);
    } catch (e) {
      setBookingError(
        e instanceof ApiError && e.status === 409 ? t("booking.errTaken") : t("booking.errGeneric"),
      );
    } finally {
      setSubmitting(false);
    }
  }

  const location = LOCATION_LABELS[eventType.location_type] ?? eventType.location_type;

  return (
    <div className="glass grid w-full max-w-5xl overflow-hidden rounded-lg shadow-2xl md:grid-cols-[minmax(0,22rem)_1fr]">
      {/* Host panel */}
      <aside className="flex flex-col gap-6 border-b border-border p-8 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 text-sm font-medium tracking-wide text-muted">
          <span className="text-accent">●</span> {eventType.host_name}
        </div>
        <h1 className="text-2xl font-semibold text-foreground">{eventType.title}</h1>
        <ul className="flex flex-col gap-3 text-sm text-muted">
          <li>{eventType.duration_min} min</li>
          <li>{location}</li>
        </ul>
        <label className="flex flex-col gap-1 text-xs text-muted/70">
          {t("booking.timezone")}
          <select
            value={tz}
            onChange={(e) => {
              setTz(e.target.value);
              setSelectedDay(null);
              setSelectedSlot(null);
            }}
            className="rounded border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
          >
            {timezones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
        </label>
      </aside>

      {/* Right side */}
      <section className="p-8">
        {confirmation ? (
          <Confirmed slot={confirmation} tz={tz} host={eventType.host_name} />
        ) : (
          <>
            <h2 className="mb-6 text-sm font-medium tracking-wide text-foreground">
              {t("booking.selectTime")}
            </h2>

            {loading && <p className="text-sm text-muted">{t("booking.loading")}</p>}
            {loadError && <p className="text-sm text-red-400">{loadError}</p>}
            {!loading && !loadError && days.length === 0 && (
              <p className="text-sm text-muted">{t("booking.noTimes")}</p>
            )}

            {days.length > 0 && (
              <div className="grid gap-8 sm:grid-cols-[1fr_minmax(0,11rem)]">
                {/* Day strip */}
                <div className="flex flex-wrap gap-2 self-start">
                  {days.map((d) => {
                    const iso = byDay.get(d)![0].start;
                    const active = d === activeDay;
                    return (
                      <button
                        key={d}
                        type="button"
                        onClick={() => {
                          setSelectedDay(d);
                          setSelectedSlot(null);
                        }}
                        className={[
                          "rounded-pill border px-3 py-2 text-sm font-medium transition",
                          active
                            ? "border-accent text-accent shadow-[0_0_14px_color-mix(in_srgb,var(--color-accent)_25%,transparent)]"
                            : "border-border-strong text-foreground hover:border-accent hover:text-accent",
                        ].join(" ")}
                      >
                        {dayLabel(iso, tz)}
                      </button>
                    );
                  })}
                </div>

                {/* Slots */}
                <div className="flex max-h-80 flex-col gap-2 overflow-y-auto pr-1">
                  {daySlots.map((slot) => {
                    const active = selectedSlot?.start === slot.start;
                    return (
                      <button
                        key={slot.start}
                        type="button"
                        onClick={() => setSelectedSlot(slot)}
                        className={[
                          "rounded-pill border px-4 py-2.5 text-sm font-medium transition",
                          active
                            ? "border-accent bg-accent text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)]"
                            : "border-border-strong text-foreground hover:border-accent hover:text-accent hover:shadow-[0_0_14px_color-mix(in_srgb,var(--color-accent)_25%,transparent)]",
                        ].join(" ")}
                      >
                        {timeLabel(slot.start, tz)}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {selectedSlot && (
              <form
                className="mt-8 flex flex-col gap-3 border-t border-border pt-6"
                onSubmit={(e) => {
                  e.preventDefault();
                  void confirm();
                }}
              >
                <p className="text-sm text-muted">
                  {dayLabel(selectedSlot.start, tz)} at {timeLabel(selectedSlot.start, tz)}
                </p>
                <input
                  required
                  placeholder={t("booking.yourName")}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                />
                <input
                  required
                  type="email"
                  placeholder={t("booking.yourEmail")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                />
                <input
                  placeholder={t("booking.guests")}
                  value={guests}
                  onChange={(e) => setGuests(e.target.value)}
                  className="rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                />
                {eventType.questions.map((q) => (
                  <QuestionField
                    key={q.id}
                    question={q}
                    value={answers[q.id] ?? ""}
                    onChange={(v) => setAnswer(q.id, v)}
                  />
                ))}
                <textarea
                  placeholder={t("booking.notes")}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  className="rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                />
                {eventType.zk_public_key && (
                  <p className="flex items-start gap-1.5 text-xs text-accent/80">
                    <LockIcon />
                    <span>{t("booking.zkNotice")}</span>
                  </p>
                )}
                {bookingError && <p className="text-sm text-red-400">{bookingError}</p>}
                <button
                  type="submit"
                  disabled={submitting || missingRequired()}
                  className="rounded-pill bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110 disabled:opacity-60"
                >
                  {submitting ? t("booking.confirming") : t("booking.confirm")}
                </button>
              </form>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function QuestionField({
  question,
  value,
  onChange,
}: {
  question: BookingQuestion;
  value: string;
  onChange: (value: string) => void;
}) {
  const t = useT();
  const inputClass =
    "rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent";
  const label = (
    <span className="text-xs text-muted/80">
      {question.label}
      {question.required && <span className="text-accent"> *</span>}
    </span>
  );

  if (question.type === "checkbox") {
    return (
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input
          type="checkbox"
          checked={value === "true"}
          onChange={(e) => onChange(e.target.checked ? "true" : "false")}
        />
        {question.label}
      </label>
    );
  }

  return (
    <label className="flex flex-col gap-1">
      {label}
      {question.type === "textarea" ? (
        <textarea
          required={question.required}
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        />
      ) : question.type === "select" ? (
        <select
          required={question.required}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        >
          <option value="">{t("booking.choose")}</option>
          {question.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : (
        <input
          required={question.required}
          type={question.type === "phone" ? "tel" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        />
      )}
    </label>
  );
}

function Confirmed({ slot, tz, host }: { slot: Booking; tz: string; host: string }) {
  const t = useT();
  return (
    <div className="flex flex-col items-start gap-3 py-6">
      <div className="flex h-12 w-12 items-center justify-center rounded-pill bg-accent/15 text-2xl text-accent ring-1 ring-border-strong">
        ✓
      </div>
      <h2 className="text-xl font-semibold text-foreground">{t("booking.booked")}</h2>
      <p className="text-sm text-muted">
        {dayLabel(slot.start_at, tz)} · {timeLabel(slot.start_at, tz)} ·{" "}
        {t("booking.with", { host })}
      </p>
      <p className="text-xs text-muted/70">{t("booking.emailFollow")}</p>
    </div>
  );
}
