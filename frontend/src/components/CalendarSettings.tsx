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
  setMirrorDetail,
  setMirrorTarget,
  syncConnection,
} from "@/lib/calendar";
import {
  CALDAV_PROVIDERS,
  connectionLabel,
  looksLikePublishedFeed,
  providerFor,
  providerIdForServer,
} from "@/lib/caldavProviders";
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

  // Defaults to iCloud rather than to nothing: an empty picker asks the same unanswerable question
  // the free-text field used to.
  const [providerId, setProviderId] = useState(CALDAV_PROVIDERS[0].id);
  const [serverUrl, setServerUrl] = useState(
    CALDAV_PROVIDERS[0].serverUrl ?? "",
  );
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
    // Back to the default provider, and to ITS address — clearing the field would leave the picker
    // saying iCloud above an empty URL, which is the disagreement this form existed to remove.
    setProviderId(CALDAV_PROVIDERS[0].id);
    setServerUrl(CALDAV_PROVIDERS[0].serverUrl ?? "");
    setUsername("");
    setPassword("");
    setError(null);
  }

  /** Host + account for a connection, so the list never shows two at-signs in a row. */
  function label(c: Connection) {
    return connectionLabel(c.server_url, c.username);
  }

  async function chooseDetail(id: string, detail: "busy" | "detailed") {
    setBusy(true);
    setError(null);
    try {
      await setMirrorDetail(id, detail);
      setConnections(await listConnections());
    } catch (e) {
      setError(errorText(e, t));
    } finally {
      setBusy(false);
    }
  }

  async function findCalendars() {
    // Caught here, before the network: a published feed answers "could not reach the calendar
    // server", which is true and tells the user nothing about what they actually did.
    if (looksLikePublishedFeed(serverUrl)) {
      setError(t("cal.feedNotServer"));
      return;
    }
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

  const provider = providerFor(providerId);

  if (loading) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">
          {t("cal.title")}
        </h2>
        {/* Five words, above the paragraph rather than inside it. Two forms on this page accept a
            calendar address and nothing said which took what; the error message now points at the
            right one, but only after the mistake. What separates them is not the protocol — it is
            what you do with the calendar, and that is the sentence. */}
        <p className="mt-1 text-sm font-medium text-foreground">
          {t("cal.whatFor")}
        </p>
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
              className="h-2.5 w-2.5 rounded-pill"
              style={{ backgroundColor: c.color }}
            />
            {c.calendar_name ?? t("cal.calendarFallback")}
            {/* Host first, then the account. It used to render `username@server_url`, which put
                two at-signs in a row: `clara@example.com@https://caldav.icloud.com/`. */}
            <span className="text-muted">
              · {label(c).host} · {label(c).account}
            </span>
            {c.mirror_bookings && (
              <span className="rounded-pill border border-accent/50 px-2 py-0.5 text-xs text-accent">
                {t("cal.mirrorTarget")}
              </span>
            )}
          </p>
          <p className="text-xs text-muted">
            {t("cal.status")} {c.status}
            {c.last_synced_at &&
              ` · ${t("cal.lastSynced", { date: new Date(c.last_synced_at).toLocaleString() })}`}
          </p>
          {c.mirror_bookings && (
            <div className="flex flex-col gap-2 rounded border border-border-strong p-3">
              <p className="text-sm font-medium text-foreground">
                {t("cal.mirrorDetailTitle")}
              </p>
              <div className="flex flex-wrap gap-2">
                {(["busy", "detailed"] as const).map((detail) => (
                  <button
                    key={detail}
                    type="button"
                    onClick={() => void chooseDetail(c.id, detail)}
                    disabled={busy}
                    className={`rounded-pill border px-4 py-2 text-sm transition ${
                      c.mirror_detail === detail
                        ? "border-accent text-accent"
                        : "border-border-strong text-muted hover:border-accent hover:text-accent"
                    }`}
                  >
                    {detail === "busy" ? t("cal.mirrorBusy") : t("cal.mirrorDetailed")}
                  </button>
                ))}
              </div>
              {/* The warning names who actually receives it, and names nobody when we have not
                  established who that is — a self-hosted server belongs to someone we never
                  identified, and inventing a company would be worse than naming none. */}
              <p className="text-xs text-amber-300">
                {providerIdForServer(c.server_url)
                  ? t("cal.mirrorWarnKnown", { host: t(label(c).host) })
                  : t("cal.mirrorWarnUnknown")}
              </p>
              <p className="text-xs text-muted">{t("cal.mirrorBusyNote")}</p>
            </div>
          )}

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
                className="rounded-pill border border-border-strong px-4 py-2.5 text-sm text-muted transition hover:border-accent hover:text-accent"
              >
                {t("cal.makeMirror")}
              </button>
            )}
            <button
              type="button"
              onClick={() => disconnect(c.id)}
              disabled={busy}
              className="rounded-pill border border-border-strong px-4 py-2.5 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
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
                    className="h-2.5 w-2.5 shrink-0 rounded-pill"
                    style={{ backgroundColor: c.color }}
                  />
                  <span className="truncate text-foreground">{c.name}</span>
                </span>
                <select
                  value={c.push_connection_id ?? ""}
                  disabled={busy}
                  onChange={(e) => void publish(c.id, e.target.value || null)}
                  className="rounded border border-border bg-surface-2 px-2 py-1 text-xs text-foreground"
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
          className="self-start rounded-pill border border-dashed border-border px-4 py-2.5 text-sm text-muted transition hover:border-accent hover:text-accent"
        >
          {connections.length === 0 ? t("cal.connect") : t("cal.addAnother")}
        </button>
      ) : (
        <div className="flex flex-col gap-3">
          {/* The picker comes first because it answers the question the URL field used to ask and
              could not: for iCloud there is no address to find, it is a constant. */}
          <label className="flex flex-col gap-1 text-sm text-muted">
            {t("cal.providerLabel")}
            <select
              value={providerId}
              onChange={(e) => {
                const p = providerFor(e.target.value);
                setProviderId(p.id);
                setServerUrl(p.serverUrl ?? "");
                setError(null);
              }}
              className={inputClass}
            >
              {CALDAV_PROVIDERS.map((p) => (
                <option key={p.id} value={p.id}>
                  {t(p.nameKey)}
                </option>
              ))}
            </select>
          </label>

          {provider.helpKey && (
            <p
              className={`text-xs ${provider.supported ? "text-muted" : "text-amber-300"}`}
            >
              {t(provider.helpKey)}
            </p>
          )}

          {provider.supported && (
            <>
              {/* Only shown where the address genuinely varies. A field pre-filled with a constant
                  invites editing something that must not be edited. */}
              {provider.serverUrl === null && (
                <label className="flex flex-col gap-1 text-sm text-muted">
                  {t("cal.serverLabel")}
                  <input
                    placeholder={
                      provider.urlTemplateKey ? t(provider.urlTemplateKey) : ""
                    }
                    value={serverUrl}
                    onChange={(e) => setServerUrl(e.target.value)}
                    className={inputClass}
                  />
                </label>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                {/* Labels, not placeholders. A placeholder disappears exactly when it is needed —
                    when the field has just been filled, and possibly with the wrong thing. On a
                    password field the dots hide the only hint there was. */}
                <label className="flex flex-col gap-1 text-sm text-muted">
                  {t(provider.usernameKey)}
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className={inputClass}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm text-muted">
                  {t("cal.passwordLabel")}
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={inputClass}
                  />
                </label>
              </div>
            </>
          )}

          {calendars === null ? (
            <div className="flex gap-3">
              <button
                type="button"
                onClick={findCalendars}
                disabled={
                  busy ||
                  !provider.supported ||
                  !serverUrl ||
                  !username ||
                  !password
                }
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
