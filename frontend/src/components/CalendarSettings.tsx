"use client";

import { useEffect, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import {
  connectCalendar,
  disconnectCalendar,
  getCalendarStatus,
  listCalendars,
  syncCalendar,
  type CalendarInfo,
  type CalendarStatus,
} from "@/lib/calendar";

function errorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 401) return "Invalid calendar credentials.";
  if (e instanceof ApiError && e.status === 502) return "Could not reach the calendar server.";
  return "Something went wrong. Please try again.";
}

export default function CalendarSettings() {
  const [status, setStatus] = useState<CalendarStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const [serverUrl, setServerUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [calendars, setCalendars] = useState<CalendarInfo[] | null>(null);
  const [selected, setSelected] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getCalendarStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
  }, []);

  async function findCalendars() {
    setBusy(true);
    setError(null);
    try {
      const list = await listCalendars({ server_url: serverUrl, username, password });
      setCalendars(list);
      setSelected(list[0]?.url ?? "");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const chosen = calendars?.find((c) => c.url === selected);
      const updated = await connectCalendar({
        server_url: serverUrl,
        username,
        password,
        calendar_url: selected,
        calendar_name: chosen?.name ?? null,
      });
      setStatus(updated);
      setCalendars(null);
      setPassword("");
      setMessage("Calendar connected and synced.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function sync() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await syncCalendar();
      setMessage(`Synced ${res.synced} busy block(s).`);
      setStatus(await getCalendarStatus());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!confirm("Disconnect this calendar?")) return;
    setBusy(true);
    try {
      await disconnectCalendar();
      setStatus(null);
      setMessage(null);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted">Loading…</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Connected calendar</h2>
        <p className="mt-1 text-sm text-muted">
          Connect a CalDAV calendar (iCloud, Nextcloud, Fastmail…) so your busy times block
          availability and bookings appear on it.
        </p>
      </div>

      {status?.connected ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface-2/40 p-4">
          <p className="text-sm text-foreground">
            <span className="text-accent">●</span> {status.calendar_name ?? "Calendar"}{" "}
            <span className="text-muted">— {status.username}@{status.server_url}</span>
          </p>
          <p className="text-xs text-muted">
            Status: {status.status}
            {status.last_synced_at &&
              ` · last synced ${new Date(status.last_synced_at).toLocaleString()}`}
          </p>
          <div className="flex gap-3">
            <button type="button" onClick={sync} disabled={busy} className={primaryButtonClass}>
              {busy ? "…" : "Sync now"}
            </button>
            <button
              type="button"
              onClick={disconnect}
              disabled={busy}
              className="rounded-lg border border-border-strong px-4 py-2.5 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
            >
              Disconnect
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <input
            placeholder="CalDAV server URL (e.g. https://caldav.fastmail.com/)"
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
            className={inputClass}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={inputClass}
            />
            <input
              type="password"
              placeholder="App password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
          </div>

          {calendars === null ? (
            <button
              type="button"
              onClick={findCalendars}
              disabled={busy || !serverUrl || !username || !password}
              className={primaryButtonClass}
            >
              {busy ? "Checking…" : "Find calendars"}
            </button>
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
                <button type="button" onClick={connect} disabled={busy} className={primaryButtonClass}>
                  {busy ? "Connecting…" : "Connect"}
                </button>
                <button
                  type="button"
                  onClick={() => setCalendars(null)}
                  className="text-sm text-muted hover:text-foreground"
                >
                  Back
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
