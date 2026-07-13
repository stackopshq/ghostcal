"use client";

import { useEffect, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import {
  type CalendarRec,
  listCalendars as listMyCalendars,
} from "@/lib/agenda";
import {
  type CalendarInfo,
  type Connection,
  connectCalendar,
  disconnectCalendar,
  listCalendars,
  listConnections,
  setMirrorTarget,
  syncConnection,
} from "@/lib/calendar";
import { useT } from "@/lib/i18n";
import { drainPushQueue, publishCalendar } from "@/lib/push";

type T = (key: string, params?: Record<string, string | number>) => string;

function errorText(e: unknown, t: T): string {
  if (e instanceof ApiError && e.status === 401) return t("cal.invalidCreds");
  if (e instanceof ApiError && e.status === 502) return t("cal.unreachable");
  if (e instanceof ApiError && e.status === 409) return t("cal.tooMany");
  return t("common.errGeneric");
}

/**
 * Connected external calendars — several of them: work, personal, family.
 *
 * The list makes the two things that stop being obvious with more than one calendar *visible*: which
 * one bookings are written back to (exactly one is), and what colour each one wears in the calendar.
 */
export default function CalendarSettings() {
  const t = useT();
  const [connections, setConnections] = useState<Connection[]>([]);
  // The user's own GhostCal calendars, each of which may publish to one connected calendar.
  const [myCalendars, setMyCalendars] = useState<CalendarRec[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const [serverUrl, setServerUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [calendars, setCalendars] = useState<CalendarInfo[] | null>(null);
  const [selected, setSelected] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listConnections(), listMyCalendars()])
      .then(([conns, cals]) => {
        setConnections(conns);
        setMyCalendars(cals.filter((c) => !c.is_shared));
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  async function publish(calendarId: string, connectionId: string | null) {
    setBusy(true);
    setError(null);
    try {
      await publishCalendar(calendarId, connectionId);
      setMyCalendars((await listMyCalendars()).filter((c) => !c.is_shared));
      if (connectionId) {
        // Nothing in the background can read an event, so the push happens here, now, in the tab
        // that just asked for it. The queue keeps whatever does not land.
        const pushed = await drainPushQueue();
        setMessage(t("cal.published", { n: pushed }));
      }
    } catch {
      setError(t("common.errGeneric"));
    } finally {
      setBusy(false);
    }
  }

  function resetForm() {
    setAdding(false);
    setCalendars(null);
    setServerUrl("");
    setUsername("");
    setPassword("");
  }

  async function findCalendars() {
    setBusy(true);
    setError(null);
    try {
      const list = await listCalendars({
        server_url: serverUrl,
        username,
        password,
      });
      setCalendars(list);
      setSelected(list[0]?.url ?? "");
    } catch (e) {
      setError(errorText(e, t));
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const chosen = calendars?.find((c) => c.url === selected);
      await connectCalendar({
        server_url: serverUrl,
        username,
        password,
        calendar_url: selected,
        calendar_name: chosen?.name ?? null,
      });
      setConnections(await listConnections());
      resetForm();
      setMessage(t("cal.connected"));
    } catch (e) {
      setError(errorText(e, t));
    } finally {
      setBusy(false);
    }
  }

  async function sync(id: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await syncConnection(id);
      setMessage(t("cal.synced", { n: res.synced }));
      setConnections(await listConnections());
    } catch (e) {
      setError(errorText(e, t));
    } finally {
      setBusy(false);
    }
  }

  async function makeMirror(id: string) {
    setBusy(true);
    setError(null);
    try {
      await setMirrorTarget(id);
      setConnections(await listConnections());
    } catch (e) {
      setError(errorText(e, t));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect(id: string) {
    if (!confirm(t("cal.confirmDisconnect"))) return;
    setBusy(true);
    try {
      await disconnectCalendar(id);
      setConnections(await listConnections());
      setMessage(null);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">
          {t("cal.title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("cal.sub")}</p>
      </div>

      {connections.map((c) => (
        <div
          key={c.id}
          className="flex flex-col gap-3 rounded-lg border border-border bg-surface-2/40 p-4"
        >
          <p className="flex flex-wrap items-center gap-2 text-sm text-foreground">
            <span
              aria-hidden
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: c.color }}
            />
            {c.calendar_name ?? t("cal.calendarFallback")}
            <span className="text-muted">
              — {c.username}@{c.server_url}
            </span>
            {c.mirror_bookings && (
              <span className="rounded-full border border-accent/50 px-2 py-0.5 text-xs text-accent">
                {t("cal.mirrorTarget")}
              </span>
            )}
          </p>
          <p className="text-xs text-muted">
            {t("cal.status")} {c.status}
            {c.last_synced_at &&
              ` · ${t("cal.lastSynced", { date: new Date(c.last_synced_at).toLocaleString() })}`}
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => sync(c.id)}
              disabled={busy}
              className={primaryButtonClass}
            >
              {busy ? "…" : t("cal.syncNow")}
            </button>
            {!c.mirror_bookings && (
              <button
                type="button"
                onClick={() => makeMirror(c.id)}
                disabled={busy}
                className="rounded-lg border border-border-strong px-4 py-2.5 text-sm text-muted transition hover:border-accent hover:text-accent"
              >
                {t("cal.makeMirror")}
              </button>
            )}
            <button
              type="button"
              onClick={() => disconnect(c.id)}
              disabled={busy}
              className="rounded-lg border border-border-strong px-4 py-2.5 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
            >
              {t("cal.disconnect")}
            </button>
          </div>
        </div>
      ))}

      {connections.length > 0 && (
        <p className="text-xs text-muted">{t("cal.mirrorHint")}</p>
      )}

      {connections.length > 0 && myCalendars.length > 0 && (
        <section className="border-t border-border pt-5">
          <h3 className="text-sm font-medium text-foreground">
            {t("cal.publishTitle")}
          </h3>
          <p className="mt-1 text-xs text-muted">{t("cal.publishSub")}</p>
          <div className="mt-3 flex flex-col gap-2">
            {myCalendars.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    aria-hidden
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: c.color }}
                  />
                  <span className="truncate text-foreground">{c.name}</span>
                </span>
                <select
                  value={c.push_connection_id ?? ""}
                  disabled={busy}
                  onChange={(e) => void publish(c.id, e.target.value || null)}
                  className="rounded-lg border border-border bg-surface-2 px-2 py-1 text-xs text-foreground"
                >
                  <option value="">{t("cal.publishNowhere")}</option>
                  {connections.map((conn) => (
                    <option key={conn.id} value={conn.id}>
                      {conn.calendar_name ?? conn.username}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </section>
      )}

      {!adding ? (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="self-start rounded-lg border border-dashed border-border px-4 py-2.5 text-sm text-muted transition hover:border-accent hover:text-accent"
        >
          {connections.length === 0 ? t("cal.connect") : t("cal.addAnother")}
        </button>
      ) : (
        <div className="flex flex-col gap-3">
          <input
            placeholder={t("cal.serverPh")}
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
            className={inputClass}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              placeholder={t("cal.username")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={inputClass}
            />
            <input
              type="password"
              placeholder={t("cal.appPassword")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
          </div>

          {calendars === null ? (
            <div className="flex gap-3">
              <button
                type="button"
                onClick={findCalendars}
                disabled={busy || !serverUrl || !username || !password}
                className={primaryButtonClass}
              >
                {busy ? t("cal.checking") : t("cal.findCalendars")}
              </button>
              <button
                type="button"
                onClick={resetForm}
                className="text-sm text-muted hover:text-foreground"
              >
                {t("common.cancel")}
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className={inputClass}
              >
                {calendars.map((c) => (
                  <option key={c.url} value={c.url}>
                    {c.name}
                  </option>
                ))}
              </select>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={connect}
                  disabled={busy}
                  className={primaryButtonClass}
                >
                  {busy ? t("cal.connecting") : t("cal.connect")}
                </button>
                <button
                  type="button"
                  onClick={() => setCalendars(null)}
                  className="text-sm text-muted hover:text-foreground"
                >
                  {t("cal.back")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}
      {message && <p className="text-sm text-accent">{message}</p>}
    </div>
  );
}
