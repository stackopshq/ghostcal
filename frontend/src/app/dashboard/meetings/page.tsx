"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import {
  KMEET_ROOM_PREFIX,
  cancelMeeting,
  generateMeetingRoom,
  listMeetings,
  shareMeetingLink,
  type Meeting,
  type MeetingScope,
} from "@/lib/meetings";
import { getActiveOrg } from "@/lib/auth";
import {
  getUnlockedKeys,
  openInviteePrivate,
  openWithOrgKeys,
  type InviteePrivate,
} from "@/lib/zk";
import {
  LockIcon,
  UnlockIcon,
} from "@/components/icons";

function fmtDay(iso: string, tz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(iso));
}

function fmtTime(iso: string, tz: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

const TABS: { key: MeetingScope; labelKey: string }[] = [
  { key: "upcoming", labelKey: "meetings.upcoming" },
  { key: "past", labelKey: "meetings.past" },
];

export default function MeetingsPage() {
  const t = useT();
  const tz = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone,
    [],
  );
  const [scope, setScope] = useState<MeetingScope>("upcoming");
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [decrypted, setDecrypted] = useState<Record<string, InviteePrivate>>(
    {},
  );
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    listMeetings(scope)
      .then(async (m) => {
        if (!active) return;
        setMeetings(m);
        // Decrypt the sealed invitee blobs in-browser with the org private key (per-tab session).
        const keys = getUnlockedKeys(getActiveOrg());
        const sealed = m.filter((x) => x.invitee_private);
        if (sealed.length > 0 && !keys) {
          setLocked(true);
          return;
        }
        setLocked(false);
        if (!keys) return;
        const out: Record<string, InviteePrivate> = {};
        for (const x of sealed) {
          try {
            out[x.id] = await openWithOrgKeys(
              keys,
              x.invitee_private!,
              (blob, sk) => openInviteePrivate(blob, keys.publicKey, sk),
            );
          } catch {
            /* skip blobs we cannot open */
          }
        }
        if (active) setDecrypted(out);
      })
      .catch(() => active && setMeetings([]))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [scope, refresh]);

  function switchTo(next: MeetingScope) {
    if (next === scope) return;
    setLoading(true);
    setScope(next);
  }

  async function cancel(id: string) {
    if (!confirm(t("meetings.confirmCancel"))) return;
    await cancelMeeting(id);
    setRefresh((r) => r + 1);
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">
          {t("meetings.title")}
        </h1>
        <p className="mt-1 text-sm text-muted">{t("meetings.sub", { tz })}</p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => switchTo(tab.key)}
            className={[
              "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition",
              scope === tab.key
                ? "border-accent text-accent"
                : "border-transparent text-muted hover:text-foreground",
            ].join(" ")}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {locked && (
        <p className="glass flex items-center gap-2 rounded border-l-[3px] border-l-accent p-3 text-sm text-accent/90">
          <LockIcon /> {t("meetings.locked")}
        </p>
      )}

      {loading && <p className="text-sm text-muted">{t("common.loading")}</p>}
      {!loading && meetings.length === 0 && (
        <p className="text-sm text-muted">
          {scope === "upcoming"
            ? t("meetings.noneUpcoming")
            : t("meetings.nonePast")}
        </p>
      )}

      <div className="flex flex-col gap-3">
        {meetings.map((m) => (
          <div
            key={m.id}
            className="glass flex flex-col gap-2 rounded-lg border-l-[3px] border-l-accent p-5 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="font-medium text-foreground">{m.event_title}</p>
              <p className="text-sm text-muted">
                {(decrypted[m.id]?.name || m.invitee_name) ?? t("meetings.noName")} ·{" "}
                {m.invitee_email}
              </p>
              {decrypted[m.id] && (
                <MeetingDetails
                  details={decrypted[m.id]}
                  label={t("meetings.privateDetails")}
                />
              )}
              {m.meeting_url && (
                <a
                  href={m.meeting_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 block max-w-xs truncate text-sm text-accent hover:underline"
                >
                  {m.meeting_url}
                </a>
              )}
              {scope === "upcoming" && (
                <MeetingLinkForm
                  meeting={m}
                  onShared={(updated) =>
                    setMeetings((all) =>
                      all.map((x) => (x.id === updated.id ? { ...x, meeting_url: updated.meeting_url } : x)),
                    )
                  }
                />
              )}
            </div>
            <div className="flex items-center gap-4">
              <div className="text-sm sm:text-right">
                <p className="text-foreground">{fmtDay(m.start_at, tz)}</p>
                <p className="text-muted">
                  {fmtTime(m.start_at, tz)} – {fmtTime(m.end_at, tz)}
                </p>
              </div>
              {scope === "upcoming" && (
                <button
                  type="button"
                  onClick={() => cancel(m.id)}
                  className="rounded-pill border border-border-strong px-3 py-2 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
                >
                  {t("meetings.cancel")}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}

function MeetingLinkForm({
  meeting,
  onShared,
}: {
  meeting: Meeting;
  onShared: (updated: Meeting) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState(meeting.meeting_url ?? "");
  const hasKmeetRoom = meeting.meeting_url?.startsWith(KMEET_ROOM_PREFIX) ?? false;
  const [source, setSource] = useState<"paste" | "kmeet">(hasKmeetRoom ? "kmeet" : "paste");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(
    null,
  );

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (source === "kmeet") {
      await send(() =>
        // Resending keeps the room the invitee already has; only a meeting without one gets a new room.
        hasKmeetRoom && meeting.meeting_url
          ? shareMeetingLink(meeting.id, meeting.meeting_url)
          : generateMeetingRoom(meeting.id, "kmeet"),
      );
      return;
    }
    if (!url.trim().startsWith("https://")) {
      setStatus({ ok: false, text: t("meetings.linkInvalid") });
      return;
    }
    await send(() => shareMeetingLink(meeting.id, url.trim()), url.trim());
  }

  async function send(call: () => Promise<Meeting>, pasted?: string) {
    setBusy(true);
    setStatus(null);
    try {
      const updated = await call();
      onShared(updated);
      setUrl(updated.meeting_url ?? "");
      setStatus({ ok: true, text: t("meetings.linkSent") });
    } catch (err) {
      const code = err instanceof ApiError ? err.status : 0;
      // 502: the link is saved but the email failed. A generated room's URL is only known from
      // the next reload of the list, so only a pasted link can be shown right away.
      if (code === 502 && pasted) onShared({ ...meeting, meeting_url: pasted });
      setStatus({
        ok: false,
        text:
          code === 422
            ? t("meetings.linkInvalid")
            : code === 502
              ? t("meetings.linkMailFailed")
              : t("meetings.linkError"),
      });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="mt-2">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-pill border border-border-strong px-3 py-1.5 text-sm text-foreground transition hover:border-accent hover:text-accent"
        >
          {meeting.meeting_url ? t("meetings.changeLink") : t("meetings.sendLink")}
        </button>
        {status?.ok && <p className="mt-1 text-xs text-accent">{status.text}</p>}
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="mt-2 flex flex-col gap-2">
      <label className="text-xs text-muted" htmlFor={`source-${meeting.id}`}>
        {t("meetings.linkSource")}
      </label>
      <select
        id={`source-${meeting.id}`}
        value={source}
        onChange={(e) => setSource(e.target.value as "paste" | "kmeet")}
        className="rounded border border-border bg-surface-2/40 px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent"
      >
        <option value="paste">{t("meetings.linkSourcePaste")}</option>
        <option value="kmeet">{t("meetings.linkSourceKmeet")}</option>
      </select>
      {source === "paste" ? (
        <label className="text-xs text-muted" htmlFor={`link-${meeting.id}`}>
          {t("meetings.linkLabel")}
        </label>
      ) : (
        <p className="text-xs text-muted">
          {hasKmeetRoom ? t("meetings.kmeetResend") : t("meetings.kmeetHint")}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {source === "paste" && (
          <input
            id={`link-${meeting.id}`}
            type="url"
            inputMode="url"
            autoFocus
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t("meetings.linkPlaceholder")}
            className="min-w-0 flex-1 rounded border border-border bg-surface-2/40 px-3 py-1.5 text-sm text-foreground outline-none focus:border-accent"
          />
        )}
        <button
          type="submit"
          disabled={busy}
          className="rounded-pill bg-accent px-3 py-1.5 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-40"
        >
          {t("meetings.linkSend")}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setStatus(null);
          }}
          className="rounded-pill px-3 py-1.5 text-sm text-muted hover:text-foreground"
        >
          {t("meetings.linkCancel")}
        </button>
      </div>
      {status && (
        <p
          role="status"
          className={`text-xs ${status.ok ? "text-accent" : "text-red-400"}`}
        >
          {status.text}
        </p>
      )}
    </form>
  );
}

function MeetingDetails({
  details,
  label,
}: {
  details: InviteePrivate;
  label: string;
}) {
  const entries = Object.entries(details.answers ?? {}).filter(([, v]) => v);
  if (entries.length === 0 && !details.notes) return null;
  return (
    <div className="mt-2 rounded-lg border border-border bg-surface-2/60 p-3 text-xs">
      <p className="mb-1 flex items-center gap-1 text-accent/80">
        <UnlockIcon /> {label}
      </p>
      <dl className="flex flex-col gap-0.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <dt className="text-muted/70">{k}:</dt>
            <dd className="text-foreground">{v}</dd>
          </div>
        ))}
        {details.notes && (
          <p className="mt-1 whitespace-pre-wrap text-foreground">
            {details.notes}
          </p>
        )}
      </dl>
    </div>
  );
}
