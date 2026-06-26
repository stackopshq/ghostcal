"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  createBooking,
  getAvailability,
  type Booking,
  type EventType,
  type Slot,
} from "@/lib/api";

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

export default function BookingClient({
  org,
  event,
  eventType,
}: {
  org: string;
  event: string;
  eventType: EventType;
}) {
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
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
      const booking = await createBooking(org, event, {
        start_at: selectedSlot.start,
        invitee_name: name,
        invitee_email: email,
        invitee_timezone: tz,
      });
      setConfirmation(booking);
    } catch (e) {
      setBookingError(
        e instanceof ApiError && e.status === 409
          ? "That slot was just taken. Pick another time."
          : "Could not confirm the booking. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const location = LOCATION_LABELS[eventType.location_type] ?? eventType.location_type;

  return (
    <div className="glass grid w-full max-w-5xl overflow-hidden rounded-2xl shadow-2xl md:grid-cols-[minmax(0,22rem)_1fr]">
      {/* Host panel */}
      <aside className="flex flex-col gap-6 border-b border-border p-8 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 text-sm font-medium tracking-wide text-muted">
          <span className="text-accent">●</span> {eventType.host_name}
        </div>
        <h1 className="text-2xl font-semibold text-foreground">{eventType.title}</h1>
        <ul className="flex flex-col gap-3 text-sm text-muted">
          <li>{eventType.duration_min} min</li>
          <li>{location}</li>
          <li className="text-xs text-muted/70">Times shown in {tz}</li>
        </ul>
      </aside>

      {/* Right side */}
      <section className="p-8">
        {confirmation ? (
          <Confirmed slot={confirmation} tz={tz} host={eventType.host_name} />
        ) : (
          <>
            <h2 className="mb-6 text-sm font-medium tracking-wide text-foreground">
              Select a time
            </h2>

            {loading && <p className="text-sm text-muted">Loading availability…</p>}
            {loadError && <p className="text-sm text-red-400">{loadError}</p>}
            {!loading && !loadError && days.length === 0 && (
              <p className="text-sm text-muted">No times available in the next two weeks.</p>
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
                          "rounded-lg border px-3 py-2 text-sm font-medium transition",
                          active
                            ? "border-accent text-accent shadow-[0_0_14px_rgba(0,240,255,0.25)]"
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
                          "rounded-lg border px-4 py-2.5 text-sm font-medium transition",
                          active
                            ? "border-accent bg-accent text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)]"
                            : "border-border-strong text-foreground hover:border-accent hover:text-accent hover:shadow-[0_0_14px_rgba(0,240,255,0.25)]",
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
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="rounded-lg border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                />
                <input
                  required
                  type="email"
                  placeholder="Your email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="rounded-lg border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                />
                {bookingError && <p className="text-sm text-red-400">{bookingError}</p>}
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110 disabled:opacity-60"
                >
                  {submitting ? "Confirming…" : "Confirm booking"}
                </button>
              </form>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function Confirmed({ slot, tz, host }: { slot: Booking; tz: string; host: string }) {
  return (
    <div className="flex flex-col items-start gap-3 py-6">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/15 text-2xl text-accent ring-1 ring-border-strong">
        ✓
      </div>
      <h2 className="text-xl font-semibold text-foreground">You&apos;re booked</h2>
      <p className="text-sm text-muted">
        {dayLabel(slot.start_at, tz)} at {timeLabel(slot.start_at, tz)} with {host}.
      </p>
      <p className="text-xs text-muted/70">A confirmation will follow by email.</p>
    </div>
  );
}
