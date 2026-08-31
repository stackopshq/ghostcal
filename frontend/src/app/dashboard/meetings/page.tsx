"use client";

import { useEffect, useMemo, useState } from "react";
import { useT } from "@/lib/i18n";
import {
  cancelMeeting,
  listMeetings,
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
