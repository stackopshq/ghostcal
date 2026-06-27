"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { inputClass, primaryButtonClass } from "@/components/AuthCard";
import { useDashboardUser } from "@/components/dashboard-context";
import { ApiError } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import {
  type BookingQuestion,
  createEventType,
  deleteEventType,
  embedSnippet,
  type EventType,
  type EventTypeInput,
  listEventTypes,
  LOCATION_LABELS,
  publicLink,
  updateEventType,
} from "@/lib/eventTypes";
import { listMembers, type Member } from "@/lib/team";

type FormState = EventTypeInput & { id: string | null };

const BLANK: FormState = {
  id: null,
  title: "",
  duration_min: 30,
  slot_interval_min: 30,
  location_type: "google_meet",
  active: true,
  questions: [],
  kind: "solo",
  host_ids: [],
  capacity: 1,
};

const KINDS: { value: string; label: string }[] = [
  { value: "solo", label: "Solo (just you)" },
  { value: "round_robin", label: "Round-robin (assign one host)" },
  { value: "collective", label: "Collective (all hosts attend)" },
  { value: "group", label: "Group (many invitees per slot)" },
];

const QUESTION_TYPES = ["text", "textarea", "phone", "select", "checkbox"] as const;

function toInput(x: EventTypeInput): EventTypeInput {
  return {
    title: x.title,
    duration_min: x.duration_min,
    slot_interval_min: x.slot_interval_min,
    location_type: x.location_type,
    active: x.active,
    questions: x.questions,
    kind: x.kind,
    host_ids: x.host_ids,
    capacity: x.capacity,
  };
}

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
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  async function reload() {
    setItems(await listEventTypes());
  }

  async function toggleActive(item: EventType) {
    setOpenMenu(null);
    await updateEventType(item.id, toInput({ ...item, active: !item.active }));
    await reload();
  }

  function startEdit(item: EventType) {
    setOpenMenu(null);
    setForm({ id: item.id, ...toInput(item) });
  }

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    Promise.all([listEventTypes(), listMembers().catch(() => [])])
      .then(([events, mem]) => {
        setItems(events);
        setMembers(mem);
      })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  async function save() {
    if (!form) return;
    setSaving(true);
    setError(null);
    const body = toInput(form);
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
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm text-muted">
              Type
              <select
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
                className={inputClass}
              >
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </label>
            {form.kind === "group" && (
              <label className="flex flex-col gap-1 text-sm text-muted">
                Capacity (invitees per slot)
                <input
                  type="number"
                  min={2}
                  value={form.capacity}
                  onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })}
                  className={inputClass}
                />
              </label>
            )}
          </div>

          {(form.kind === "round_robin" || form.kind === "collective") && (
            <div className="flex flex-col gap-2">
              <span className="text-sm text-muted">Hosts in the pool</span>
              {members.length === 0 && (
                <p className="text-xs text-muted/70">Invite teammates first (Team page).</p>
              )}
              <div className="flex flex-wrap gap-2">
                {members.map((m) => {
                  const on = form.host_ids.includes(m.user_id);
                  return (
                    <button
                      key={m.user_id}
                      type="button"
                      onClick={() =>
                        setForm({
                          ...form,
                          host_ids: on
                            ? form.host_ids.filter((id) => id !== m.user_id)
                            : [...form.host_ids, m.user_id],
                        })
                      }
                      className={[
                        "rounded-lg border px-3 py-1.5 text-sm transition",
                        on
                          ? "border-accent text-accent"
                          : "border-border-strong text-muted hover:text-foreground",
                      ].join(" ")}
                    >
                      {m.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <QuestionsBuilder
            questions={form.questions}
            onChange={(questions) => setForm({ ...form, questions })}
          />

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
            data-kind={item.kind}
          >
            <div>
              <p className="font-medium text-foreground">
                {item.title}
                {!item.active && <span className="ml-2 text-xs text-muted">(inactive)</span>}
              </p>
              <p className="text-sm text-muted">
                {item.duration_min} min ·{" "}
                {LOCATION_LABELS[item.location_type] ?? item.location_type}
                {item.kind !== "solo" && <span className="text-accent"> · {item.kind}</span>}
                {item.questions.length > 0 && ` · ${item.questions.length} questions`}
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
              <div className="relative">
                <button
                  type="button"
                  aria-label="More actions"
                  onClick={() => setOpenMenu(openMenu === item.id ? null : item.id)}
                  className="rounded-lg border border-border-strong px-3 py-2 text-sm text-foreground transition hover:border-accent hover:text-accent"
                >
                  ⋮
                </button>
                {openMenu === item.id && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setOpenMenu(null)} />
                    <div className="absolute right-0 z-20 mt-1 w-44 overflow-hidden rounded-lg border border-border-strong bg-surface shadow-2xl">
                      <button
                        type="button"
                        onClick={() => startEdit(item)}
                        className="block w-full px-4 py-2 text-left text-sm text-foreground transition hover:bg-surface-2"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          setOpenMenu(null);
                          await navigator.clipboard.writeText(embedSnippet(item));
                          setCopied(item.id);
                          setTimeout(() => setCopied(null), 1500);
                        }}
                        className="block w-full px-4 py-2 text-left text-sm text-foreground transition hover:bg-surface-2"
                      >
                        Copy embed code
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleActive(item)}
                        className="block w-full px-4 py-2 text-left text-sm text-foreground transition hover:bg-surface-2"
                      >
                        {item.active ? "Deactivate" : "Activate"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setOpenMenu(null);
                          remove(item);
                        }}
                        className="block w-full px-4 py-2 text-left text-sm text-red-400 transition hover:bg-surface-2"
                      >
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}

function QuestionsBuilder({
  questions,
  onChange,
}: {
  questions: BookingQuestion[];
  onChange: (questions: BookingQuestion[]) => void;
}) {
  const cls =
    "rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus:border-accent";

  function update(i: number, patch: Partial<BookingQuestion>) {
    onChange(questions.map((q, idx) => (idx === i ? { ...q, ...patch } : q)));
  }

  function add() {
    const id = `q${questions.length + 1}_${Math.random().toString(36).slice(2, 7)}`;
    onChange([...questions, { id, label: "", type: "text", required: false, options: [] }]);
  }

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <span className="text-sm text-muted">Custom questions for invitees</span>
      {questions.map((q, i) => (
        <div key={q.id} className="flex flex-col gap-2 rounded-lg border border-border p-3">
          <div className="flex flex-wrap gap-2">
            <input
              placeholder="Question label"
              value={q.label}
              onChange={(e) => update(i, { label: e.target.value })}
              className={`${cls} flex-1`}
            />
            <select
              value={q.type}
              onChange={(e) => update(i, { type: e.target.value as BookingQuestion["type"] })}
              className={cls}
            >
              {QUESTION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs text-muted">
              <input
                type="checkbox"
                checked={q.required}
                onChange={(e) => update(i, { required: e.target.checked })}
              />
              required
            </label>
            <button
              type="button"
              onClick={() => onChange(questions.filter((_, idx) => idx !== i))}
              className="rounded-lg border border-border-strong px-2 text-sm text-muted hover:text-red-400"
            >
              ✕
            </button>
          </div>
          {q.type === "select" && (
            <input
              placeholder="Options, comma-separated"
              value={q.options.join(", ")}
              onChange={(e) =>
                update(i, {
                  options: e.target.value
                    .split(",")
                    .map((o) => o.trim())
                    .filter(Boolean),
                })
              }
              className={cls}
            />
          )}
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="self-start text-sm text-accent hover:brightness-110"
      >
        + Add a question
      </button>
    </div>
  );
}
