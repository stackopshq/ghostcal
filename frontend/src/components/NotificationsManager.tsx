"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getActiveOrg } from "@/lib/auth";
import { getAgenda } from "@/lib/agenda";
import { useI18n } from "@/lib/i18n";
import {
  enableNotifications,
  notifyOnce,
  notificationsEnabled,
  notificationsPermission,
  notificationsSupported,
} from "@/lib/notify";
import { listTasks } from "@/lib/tasks";
import {
  getUnlockedKeys,
  openContent,
  openTaskContent,
  openWithOrgKeys,
} from "@/lib/zk";

const POLL_MS = 30_000;
// Fire only when the reminder moment just arrived (so opening the app hours later doesn't replay
// stale reminders). Two poll cycles of slack.
const FRESH_MS = 90_000;
const DISMISS_KEY = "gc_notify_prompt_dismissed";

function hm(iso: string, locale: string): string {
  return new Date(iso).toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function NotificationsManager() {
  const { locale, t } = useI18n();
  const [showPrompt, setShowPrompt] = useState(false);
  const scanning = useRef(false);

  // Decide whether to show the one-time enable prompt (supported, undecided, not dismissed).
  useEffect(() => {
    if (
      notificationsSupported() &&
      notificationsPermission() === "default" &&
      localStorage.getItem(DISMISS_KEY) !== "1"
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setShowPrompt(true);
    }
  }, []);

  const scan = useCallback(async () => {
    if (scanning.current || !notificationsEnabled()) return;
    const keys = getUnlockedKeys(getActiveOrg());
    if (!keys) return;
    scanning.current = true;
    try {
      const now = Date.now();
      const fresh = (reminderAt: number) =>
        reminderAt <= now && now - reminderAt < FRESH_MS;

      // Events: reminder fires at (start - reminder_minutes).
      const from = new Date(now - 60_000).toISOString();
      const to = new Date(now + 25 * 3_600_000).toISOString();
      const agenda = await getAgenda(from, to);
      for (const it of agenda) {
        if (it.source !== "event" || it.reminder_minutes == null || !it.content)
          continue;
        const reminderAt =
          new Date(it.start).getTime() - it.reminder_minutes * 60_000;
        if (!fresh(reminderAt)) continue;
        let title = t("calendar.untitled");
        try {
          title =
            (await openWithOrgKeys(keys, it.content, openContent)).title ||
            title;
        } catch {
          continue;
        }
        notifyOnce(
          `ev:${it.event_id}:${it.start}`,
          `${t("notify.eventPrefix")} ${title}`,
          `${t("notify.at")} ${hm(it.start, locale)}`,
        );
      }

      // Tasks: reminder fires at (due - reminder_minutes).
      const tasks = await listTasks();
      for (const task of tasks) {
        if (
          task.completed ||
          task.due_at == null ||
          task.reminder_minutes == null ||
          !task.content
        )
          continue;
        const reminderAt =
          new Date(task.due_at).getTime() - task.reminder_minutes * 60_000;
        if (!fresh(reminderAt)) continue;
        let title = t("calendar.untitled");
        try {
          title =
            (await openWithOrgKeys(keys, task.content, openTaskContent))
              .title || title;
        } catch {
          continue;
        }
        notifyOnce(
          `task:${task.id}`,
          `${t("notify.taskPrefix")} ${title}`,
          `${t("notify.due")} ${hm(task.due_at, locale)}`,
        );
      }
    } catch {
      /* transient network/lock errors are ignored — the next tick retries */
    } finally {
      scanning.current = false;
    }
  }, [t, locale]);

  useEffect(() => {
    void scan();
    const id = setInterval(() => void scan(), POLL_MS);
    return () => clearInterval(id);
  }, [scan]);

  async function onEnable() {
    await enableNotifications();
    setShowPrompt(false);
    void scan();
  }
  function onDismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setShowPrompt(false);
  }

  if (!showPrompt) return null;
  return (
    <div className="glass fixed bottom-16 right-4 z-40 flex max-w-xs flex-col gap-2 rounded border border-border p-3 text-sm shadow-lg">
      <p className="text-foreground">{t("notify.promptTitle")}</p>
      <p className="text-xs text-muted">{t("notify.promptBody")}</p>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onDismiss}
          className="text-xs text-muted hover:text-foreground"
        >
          {t("notify.notNow")}
        </button>
        <button
          type="button"
          onClick={onEnable}
          className="rounded-pill bg-accent px-3 py-1 text-xs font-semibold text-accent-ink hover:brightness-110"
        >
          {t("notify.enable")}
        </button>
      </div>
    </div>
  );
}
