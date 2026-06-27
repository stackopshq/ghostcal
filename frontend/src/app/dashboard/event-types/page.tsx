"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { useDashboardUser } from "@/components/dashboard-context";
import { ApiError } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import {
  createEventType,
  deleteEventType,
  listEventTypes,
  LOCATION_LABELS,
  publicLink,
  updateEventType,
  type EventType,
  type EventTypeInput,
} from "@/lib/eventTypes";

const BLANK: EventTypeInput & { id: string | null } = {
  id: null,
  title: "",
  duration_min: 30,
  slot_interval_min: 30,
  location_type: "google_meet",
  active: true,
};

export default function EventTypesPage() {
  const router = useRouter();
  const host = useDashboardUser();
  const hostInitials = host
    ? host.name
        .split(" ")
        .map((p) => p[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : "";
  const [items, setItems] = useState<EventType[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<(EventTypeInput & { id: string | null }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  async function reload() {
    setItems(await listEventTypes());
  }

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    listEventTypes()
      .then(setItems)
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  async function save() {
    if (!form) return;
    setSaving(true);
    setError(null);
    const body: EventTypeInput = {
      title: form.title,
      duration_min: form.duration_min,
      slot_interval_min: form.slot_interval_min,
      location_type: form.location_type,
      active: form.active,
    };
    try {
      if (form.id) await updateEventType(form.id, body);
      else await createEventType(body);
      setForm(null);
      await reload();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 422
          ? "Check the fields — duration and interval must be positive."
          : "Could not save. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function remove(item: EventType) {
    if (!confirm(`Delete "${item.title}"?`)) return;
    try {
      await deleteEventType(item.id);
      await reload();
    } catch (e) {
      alert(
        e instanceof ApiError && e.status === 409
          ? "This event type has bookings and can't be deleted."
          : "Could not delete. Please try again.",
      );
    }
  }

  async function copy(item: EventType) {
    await navigator.clipboard.writeText(publicLink(item));
    setCopied(item.id);
    setTimeout(() => setCopied(null), 1500);
  }

  if (loading) {
    return (
      <main className="flex flex-1 items-center justify-center p-8">
        <p className="text-sm text-muted">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-6 sm:p-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Event types</h1>
          <p className="mt-1 text-sm text-muted">
            Create bookable meeting types and share their link.
          </p>
        </div>
        {!form && (
          <button type="button" onClick={() => setForm({ ...BLANK })} className={primaryButtonClass}>
            + New event type
          </button>
        )}
      </div>

      {host && (
        <div className="flex items-center gap-3 border-b border-border pb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-accent/30 to-accent/5 text-xs font-semibold text-accent ring-1 ring-border-strong">
            {hostInitials}
          </div>
          <span className="text-sm font-medium text-foreground">{host.name}</span>
        </div>
      )}

      {form && (
        <section className="glass flex flex-col gap-4 rounded-2xl p-6">
          <h2 className="text-sm font-medium text-foreground">
            {form.id ? "Edit event type" : "New event type"}
          </h2>
          <input
            placeholder="Title (e.g. Intro call)"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className={inputClass}
          />
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="flex flex-col gap-1 text-sm text-muted">
              Duration (min)
              <input
                type="number"
                min={1}
                value={form.duration_min}
                onChange={(e) => setForm({ ...form, duration_min: Number(e.target.value) })}
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-muted">
              Slot every (min)
              <input
                type="number"
                min={1}
                value={form.slot_interval_min}
                onChange={(e) =>
                  setForm({ ...form, slot_interval_min: Number(e.target.value) })
                }
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-muted">
              Location
              <select
                value={form.location_type}
                onChange={(e) => setForm({ ...form, location_type: e.target.value })}
                className={inputClass}
              >
                {Object.entries(LOCATION_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm({ ...form, active: e.target.checked })}
            />
            Active (bookable)
          </label>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="flex items-center gap-3">
            <button type="button" onClick={save} disabled={saving} className={primaryButtonClass}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => {
                setForm(null);
                setError(null);
              }}
              className="text-sm text-muted hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </section>
      )}

      {items.length === 0 && !form && (
        <p className="text-sm text-muted">No event types yet. Create one to get a booking link.</p>
      )}

      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <div
            key={item.id}
            className="glass flex flex-col gap-3 rounded-2xl border-l-[3px] border-l-accent p-5 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="font-medium text-foreground">
                {item.title}
                {!item.active && <span className="ml-2 text-xs text-muted">(inactive)</span>}
              </p>
              <p className="text-sm text-muted">
                {item.duration_min} min · {LOCATION_LABELS[item.location_type] ?? item.location_type}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={publicLink(item)}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-border-strong px-3 py-2 text-sm text-foreground transition hover:border-accent hover:text-accent"
              >
                Open ↗
              </a>
              <button
                type="button"
                onClick={() => copy(item)}
                className="rounded-lg border border-border-strong px-3 py-2 text-sm text-foreground transition hover:border-accent hover:text-accent"
              >
                {copied === item.id ? "Copied ✓" : "Copy link"}
              </button>
              <button
                type="button"
                onClick={() =>
                  setForm({
                    id: item.id,
                    title: item.title,
                    duration_min: item.duration_min,
                    slot_interval_min: item.slot_interval_min,
                    location_type: item.location_type,
                    active: item.active,
                  })
                }
                className="rounded-lg border border-border-strong px-3 py-2 text-sm text-foreground transition hover:border-accent hover:text-accent"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => remove(item)}
                className="rounded-lg border border-border-strong px-3 py-2 text-sm text-muted transition hover:border-red-400 hover:text-red-400"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
