"use client";

import Image from "next/image";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  cancelManagedBooking,
  getAvailability,
  getManagedBooking,
  rescheduleManagedBooking,
  type ManageBooking,
  type Slot,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

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
function longWhen(iso: string, tz: string): string {
  return `${new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    weekday: "long",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso))} (${tz})`;
}

type Mode = "view" | "rescheduling" | "cancelled" | "rescheduled";

const card = "glass w-full max-w-lg rounded-2xl p-8 shadow-2xl";
const dangerBtn =
  "rounded-lg border border-border-strong px-4 py-2.5 text-sm text-muted transition hover:border-red-400 hover:text-red-400";
const accentBtn =
  "rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.45)] transition hover:brightness-110 disabled:opacity-60";

export default function ManagePage() {
  const t = useT();
  const token = String(useParams().token);
  const [booking, setBooking] = useState<ManageBooking | null>(null);
  const [loading, setLoading] = useState(true);
  const [invalid, setInvalid] = useState(false);
  const [mode, setMode] = useState<Mode>("view");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reschedule picker state.
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [newStart, setNewStart] = useState<string | null>(null);

  const tz = booking?.invitee_timezone ?? "UTC";

  useEffect(() => {
    getManagedBooking(token)
      .then(setBooking)
      .catch(() => setInvalid(true))
      .finally(() => setLoading(false));
  }, [token]);

  async function startReschedule() {
    if (!booking) return;
    setMode("rescheduling");
    setError(null);
    const from = dayKey(new Date().toISOString(), tz);
    const to = dayKey(new Date(Date.now() + 14 * 86400_000).toISOString(), tz);
    try {
      const res = await getAvailability(booking.organization_slug, booking.event_slug, from, to);
      setSlots(res.slots);
    } catch {
      setError(t("manage.errLoadTimes"));
    }
  }

  const byDay = useMemo(() => {
    const map = new Map<string, Slot[]>();
    for (const s of slots) (map.get(dayKey(s.start, tz)) ?? map.set(dayKey(s.start, tz), []).get(dayKey(s.start, tz))!).push(s);
    return map;
  }, [slots, tz]);
  const days = useMemo(() => [...byDay.keys()].sort(), [byDay]);
  const activeDay = selectedDay ?? days[0] ?? null;

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      await cancelManagedBooking(token);
      setMode("cancelled");
    } catch {
      setError(t("manage.errCancel"));
    } finally {
      setBusy(false);
    }
  }

  async function confirmReschedule() {
    if (!newStart) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await rescheduleManagedBooking(token, newStart);
      setBooking((b) => (b ? { ...b, start_at: updated.start_at, end_at: updated.end_at } : b));
      setMode("rescheduled");
    } catch {
      setError(t("manage.errReschedule"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
      {loading ? (
        <p className="text-sm text-muted">{t("common.loading")}</p>
      ) : invalid || !booking ? (
        <div className={card}>
          <h1 className="text-xl font-semibold text-foreground">{t("manage.linkInvalid")}</h1>
          <p className="mt-2 text-sm text-muted">{t("manage.linkInvalidSub")}</p>
        </div>
      ) : (
        <div className={card}>
          {/* Le logo, comme dans `AuthCard`. Les deux autres ronds du frontend restent :
              ils précèdent le nom d'une organisation cliente ou d'un hôte, pas le nôtre.
              Y poser le fantôme laisserait croire que cette organisation *est* GhostCal. */}
          <div className="mb-6 flex items-center gap-2 text-sm font-medium tracking-wide text-muted">
            <Image src="/logo.svg" alt="" width={20} height={20} className="h-5 w-5" />
            GhostCal
          </div>

          <h1 className="text-xl font-semibold text-foreground">{booking.event_title}</h1>
          <p className="mt-1 text-sm text-muted">{t("booking.with", { host: booking.host_name })}</p>
          <p className="mt-3 text-sm text-foreground">{longWhen(booking.start_at, tz)}</p>
          <p className="text-sm text-muted">{LOCATION_LABELS[booking.location_type] ?? booking.location_type}</p>

          {booking.status !== "confirmed" && mode === "view" && (
            <p className="mt-6 text-sm text-muted">{t("manage.notActive")}</p>
          )}

          {mode === "cancelled" && (
            <p className="mt-6 text-sm text-accent">{t("manage.cancelled")}</p>
          )}
          {mode === "rescheduled" && (
            <p className="mt-6 text-sm text-accent">
              {t("manage.rescheduledTo", { when: longWhen(booking.start_at, tz) })}
            </p>
          )}

          {booking.status === "confirmed" && mode === "view" && (
            <div className="mt-8 flex gap-3">
              <button type="button" onClick={startReschedule} className={accentBtn}>
                {t("manage.reschedule")}
              </button>
              <button type="button" onClick={cancel} disabled={busy} className={dangerBtn}>
                {t("manage.cancelMeeting")}
              </button>
            </div>
          )}

          {mode === "rescheduling" && (
            <div className="mt-8">
              <p className="mb-3 text-sm font-medium text-foreground">{t("manage.pickNew")}</p>
              {days.length === 0 ? (
                <p className="text-sm text-muted">{t("booking.noTimes")}</p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-[1fr_minmax(0,9rem)]">
                  <div className="flex flex-wrap gap-2 self-start">
                    {days.map((d) => {
                      const active = d === activeDay;
                      return (
                        <button
                          key={d}
                          type="button"
                          onClick={() => {
                            setSelectedDay(d);
                            setNewStart(null);
                          }}
                          className={[
                            "rounded-lg border px-3 py-2 text-sm font-medium transition",
                            active
                              ? "border-accent text-accent"
                              : "border-border-strong text-foreground hover:border-accent",
                          ].join(" ")}
                        >
                          {dayLabel(byDay.get(d)![0].start, tz)}
                        </button>
                      );
                    })}
                  </div>
                  <div className="flex max-h-64 flex-col gap-2 overflow-y-auto pr-1">
                    {(activeDay ? byDay.get(activeDay)! : []).map((s) => (
                      <button
                        key={s.start}
                        type="button"
                        onClick={() => setNewStart(s.start)}
                        className={[
                          "rounded-lg border px-4 py-2 text-sm font-medium transition",
                          newStart === s.start
                            ? "border-accent bg-accent text-accent-ink"
                            : "border-border-strong text-foreground hover:border-accent hover:text-accent",
                        ].join(" ")}
                      >
                        {timeLabel(s.start, tz)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="mt-5 flex items-center gap-3">
                <button
                  type="button"
                  onClick={confirmReschedule}
                  disabled={!newStart || busy}
                  className={accentBtn}
                >
                  {busy ? t("booking.confirming") : t("manage.confirmNew")}
                </button>
                <button
                  type="button"
                  onClick={() => setMode("view")}
                  className="text-sm text-muted hover:text-foreground"
                >
                  {t("manage.back")}
                </button>
              </div>
            </div>
          )}

          {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
        </div>
      )}
    </main>
  );
}
