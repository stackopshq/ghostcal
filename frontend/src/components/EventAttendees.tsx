"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type Attendee,
  addAttendee,
  listAttendees,
  removeAttendee,
  sendInvitation,
} from "@/lib/agenda";
import { getMe } from "@/lib/auth";
import { ghostMailUrl, openInGhostMail } from "@/lib/ghostmail";
import { useT } from "@/lib/i18n";

const STATUS_KEY: Record<string, string> = {
  needs_action: "att.pending",
  accepted: "att.accepted",
  declined: "att.declined",
  tentative: "att.tentative",
};

// Guests on a personal event. Inviting sends an ICS email built from the cleartext title/location
// this browser holds (decrypted) — the server relays it and never stores it.
export default function EventAttendees({
  eventId,
  title,
  location,
  startISO,
  endISO,
  allDay,
}: {
  eventId: string;
  title: string;
  location: string;
  startISO: string;
  endISO: string;
  allDay: boolean;
}) {
  const t = useT();
  const [attendees, setAttendees] = useState<Attendee[]>([]);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  // Null until the deployment answers, and the button stays hidden meanwhile.
  // That is the honest default: most deployments run GhostCal on its own, and a
  // button that opens a dead tab is worse than no button at all.
  const [mailApp, setMailApp] = useState<string | null>(null);

  useEffect(() => {
    void ghostMailUrl().then(setMailApp);
  }, []);

  const load = useCallback(async () => {
    try {
      setAttendees(await listAttendees(eventId));
    } catch {
      /* ignore */
    }
  }, [eventId]);

  useEffect(() => {
    // Fetch-on-mount: attendees come from the network, so state is set asynchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const added = await addAttendee(eventId, email.trim(), null);
      const me = await getMe();
      await sendInvitation(eventId, {
        email: added.email,
        token: added.token,
        title: title || t("calendar.untitled"),
        location,
        organizer_name: me.name,
        start_at: startISO,
        end_at: endISO,
        all_day: allDay,
      });
      setEmail("");
      setNote(t("att.invited"));
      await load();
    } catch {
      setNote(t("att.error"));
    } finally {
      setBusy(false);
    }
  }

  async function drop(id: string) {
    await removeAttendee(eventId, id).catch(() => undefined);
    await load();
  }

  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">{t("att.title")}</p>
        {attendees.length > 0 && mailApp && (
          <button
            type="button"
            onClick={() => {
              void openInGhostMail({
                to: attendees.map((a) => a.email),
                subject: title || t("calendar.untitled"),
              });
            }}
            className="flex items-center gap-1 text-xs text-accent hover:underline"
          >
            <span aria-hidden>✉️</span> {t("att.emailGuests")}
          </button>
        )}
      </div>
      {attendees.map((a) => (
        <div key={a.id} className="group flex items-center justify-between text-sm">
          <span className="truncate text-foreground">{a.email}</span>
          <span className="flex items-center gap-2">
            <span
              className={`text-xs ${
                a.status === "accepted"
                  ? "text-accent"
                  : a.status === "declined"
                    ? "text-red-400"
                    : "text-muted"
              }`}
            >
              {t(STATUS_KEY[a.status] ?? "att.pending")}
            </span>
            <button
              type="button"
              aria-label={t("calendar.delete")}
              onClick={() => drop(a.id)}
              className="text-muted opacity-0 transition group-hover:opacity-100 hover:text-red-400"
            >
              ✕
            </button>
          </span>
        </div>
      ))}
      <form onSubmit={invite} className="flex gap-2">
        <input
          type="email"
          placeholder={t("att.addPlaceholder")}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="flex-1 rounded-lg border border-border-strong bg-surface-2 px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent"
        />
        <button
          type="submit"
          disabled={busy || !email.trim()}
          className="rounded-lg border border-border-strong px-3 py-1.5 text-sm text-foreground hover:bg-surface disabled:opacity-50"
        >
          {busy ? t("att.inviting") : t("att.invite")}
        </button>
      </form>
      {note && <p className="text-xs text-accent">{note}</p>}
      <p className="text-[11px] text-muted">{t("att.zkNote")}</p>
    </div>
  );
}
