"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getActiveOrg } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { parseQuickAdd } from "@/lib/quickAdd";
import {
  completeTask,
  createTask,
  deleteTask,
  listTasks,
  type Task,
  updateTask,
} from "@/lib/tasks";
import { getUnlockedKeys, openTaskContent, sealTaskContent } from "@/lib/zk";

type Decorated = Task & { title: string; notes: string };

// Content-less email reminder offsets (minutes before the due date). "At time" = 0.
const REMINDERS: { value: string; key: string }[] = [
  { value: "", key: "tasks.remindNone" },
  { value: "0", key: "tasks.remindAt" },
  { value: "10", key: "tasks.remind10m" },
  { value: "60", key: "tasks.remind1h" },
  { value: "1440", key: "tasks.remind1d" },
];

function dueLabel(iso: string, locale: string): { text: string; overdue: boolean } {
  const d = new Date(iso);
  const now = new Date();
  const overdue = d.getTime() < now.getTime();
  const sameDay = d.toDateString() === now.toDateString();
  const text = sameDay
    ? d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(locale, { weekday: "short", month: "short", day: "numeric" });
  return { text, overdue };
}

export default function TasksPage() {
  const { locale, t } = useI18n();
  const [tasks, setTasks] = useState<Decorated[]>([]);
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [quick, setQuick] = useState("");
  const [busy, setBusy] = useState(false);

  // Parse a due date out of the quick-add text (title is what's left once the date is removed).
  const parsed = useMemo(() => (quick.trim() ? parseQuickAdd(quick, locale) : null), [quick, locale]);

  const load = useCallback(async () => {
    setLoading(true);
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys) {
      setLocked(true);
      setLoading(false);
      return;
    }
    setLocked(false);
    try {
      const raw = await listTasks();
      const decorated = await Promise.all(
        raw.map(async (task) => {
          let title = "";
          let notes = "";
          if (task.content) {
            try {
              const c = await openTaskContent(task.content, keys.privateKey);
              title = c.title;
              notes = c.notes;
            } catch {
              title = t("calendar.locked");
            }
          }
          return { ...task, title, notes };
        }),
      );
      setTasks(decorated);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // Fetch-on-mount: tasks come from the network and are decrypted asynchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function add() {
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys?.publicKey || !quick.trim()) return;
    setBusy(true);
    try {
      // If the text carries a date/time, use it as the due date and the leftover as the title;
      // otherwise the whole text is the title.
      const title = parsed?.title || quick.trim();
      const dueAt =
        parsed && !parsed.allDay
          ? new Date(`${parsed.date}T${parsed.start}:00`).toISOString()
          : parsed?.allDay
            ? new Date(`${parsed.date}T09:00:00`).toISOString()
            : null;
      const content = await sealTaskContent({ title, notes: "" }, keys.publicKey);
      await createTask({ content, due_at: dueAt });
      setQuick("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function toggle(task: Decorated) {
    await completeTask(task.id, !task.completed);
    await load();
  }

  async function rename(task: Decorated) {
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys?.publicKey) return;
    const next = window.prompt(t("tasks.rename"), task.title);
    if (next === null || next.trim() === task.title) return;
    const content = await sealTaskContent({ title: next.trim(), notes: task.notes }, keys.publicKey);
    await updateTask(task.id, {
      content,
      due_at: task.due_at,
      reminder_minutes: task.reminder_minutes,
    });
    await load();
  }

  // Set/clear the content-less email reminder (minutes before the due date). Re-seals the content
  // because the update endpoint replaces the whole task.
  async function setReminder(task: Decorated, minutes: number | null) {
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys?.publicKey) return;
    const content = await sealTaskContent({ title: task.title, notes: task.notes }, keys.publicKey);
    await updateTask(task.id, { content, due_at: task.due_at, reminder_minutes: minutes });
    await load();
  }

  async function remove(task: Decorated) {
    await deleteTask(task.id);
    await load();
  }

  const active = tasks.filter((task) => !task.completed);
  const done = tasks.filter((task) => task.completed);

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-5 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t("tasks.title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("tasks.sub")}</p>
      </div>

      {locked && (
        <p className="glass flex items-center gap-2 rounded-xl border-l-[3px] border-l-accent p-3 text-sm text-accent/90">
          <span aria-hidden>🔒</span> {t("calendar.locked")}
        </p>
      )}

      {!locked && (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void add();
            }}
            className="flex items-center gap-2"
          >
            <span aria-hidden className="text-lg text-accent">
              ✓
            </span>
            <input
              value={quick}
              onChange={(e) => setQuick(e.target.value)}
              placeholder={t("tasks.quickAdd")}
              className="flex-1 rounded-lg border border-border bg-surface-2/40 px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
            <button
              type="submit"
              disabled={busy || !quick.trim()}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-40"
            >
              {busy ? t("common.saving") : t("tasks.add")}
            </button>
          </form>
          {parsed && !parsed.allDay && (
            <p className="px-1 text-xs text-muted">
              {t("tasks.duePreview")}: <span className="text-accent">{`${parsed.date} ${parsed.start}`}</span>
            </p>
          )}

          {loading && <p className="text-sm text-muted">{t("common.loading")}</p>}

          {!loading && (
            <ul className="flex flex-col gap-1">
              {active.length === 0 && <li className="text-sm text-muted">{t("tasks.empty")}</li>}
              {active.map((task) => {
                const due = task.due_at ? dueLabel(task.due_at, locale) : null;
                return (
                  <li
                    key={task.id}
                    className="group flex items-center gap-3 rounded-lg border border-border bg-surface-2/30 px-3 py-2"
                  >
                    <button
                      type="button"
                      aria-label={t("tasks.complete")}
                      onClick={() => toggle(task)}
                      className="h-4 w-4 shrink-0 rounded-full border border-border-strong transition hover:border-accent"
                    />
                    <button
                      type="button"
                      onDoubleClick={() => rename(task)}
                      className="flex-1 truncate text-left text-sm text-foreground"
                    >
                      {task.title || t("calendar.untitled")}
                    </button>
                    {due && (
                      <span className={`text-xs ${due.overdue ? "text-red-400" : "text-muted"}`}>
                        {due.text}
                      </span>
                    )}
                    {task.due_at && (
                      <label
                        className="flex items-center gap-1 text-xs text-muted"
                        title={t("tasks.reminder")}
                      >
                        <span aria-hidden className={task.reminder_minutes != null ? "text-accent" : ""}>
                          🔔
                        </span>
                        <select
                          value={task.reminder_minutes ?? ""}
                          onChange={(e) =>
                            setReminder(task, e.target.value === "" ? null : Number(e.target.value))
                          }
                          className="cursor-pointer rounded border border-border bg-transparent py-0.5 text-xs text-muted outline-none focus:border-accent"
                        >
                          {REMINDERS.map((r) => (
                            <option key={r.key} value={r.value}>
                              {t(r.key)}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                    <button
                      type="button"
                      aria-label={t("common.delete")}
                      onClick={() => remove(task)}
                      className="text-muted opacity-0 transition group-hover:opacity-100 hover:text-red-400"
                    >
                      ✕
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {done.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="mt-2 px-1 text-xs uppercase tracking-wide text-muted">
                {t("tasks.completed")}
              </p>
              {done.map((task) => (
                <div
                  key={task.id}
                  className="group flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm"
                >
                  <button
                    type="button"
                    aria-label={t("tasks.reopen")}
                    onClick={() => toggle(task)}
                    className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent text-[10px] text-accent-ink"
                  >
                    ✓
                  </button>
                  <span className="flex-1 truncate text-muted line-through">
                    {task.title || t("calendar.untitled")}
                  </span>
                  <button
                    type="button"
                    aria-label={t("common.delete")}
                    onClick={() => remove(task)}
                    className="text-muted opacity-0 transition group-hover:opacity-100 hover:text-red-400"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
