"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useI18n } from "@/lib/i18n";

type Command = {
  id: string;
  label: string;
  hint?: string;
  keywords: string;
  run: () => void;
};

function setTheme(next: "light" | "dark") {
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("gc_theme", next);
  } catch {
    /* ignore */
  }
}

// Command palette (Cmd/Ctrl+K): fuzzy-jump to any page or action, keyboard-first — the Fantastical /
// Superhuman move. Opens on Cmd/Ctrl+K, filters as you type, arrow keys to move, Enter to run.
export default function CommandPalette() {
  const router = useRouter();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const go = useCallback(
    (path: string) => {
      setOpen(false);
      router.push(path);
    },
    [router],
  );

  const openPalette = useCallback(() => {
    setQuery("");
    setActive(0);
    setOpen(true);
  }, []);

  const commands = useMemo<Command[]>(
    () => [
      { id: "cal", label: t("cmd.goCalendar"), keywords: "calendar agenda", run: () => go("/dashboard/calendar") },
      { id: "tasks", label: t("cmd.goTasks"), keywords: "tasks todo", run: () => go("/dashboard/tasks") },
      { id: "new-event", label: t("cmd.newEvent"), hint: "N", keywords: "create event add", run: () => go("/dashboard/calendar#new") },
      { id: "new-task", label: t("cmd.newTask"), hint: "T", keywords: "create task add todo", run: () => go("/dashboard/tasks#new") },
      { id: "view-month", label: t("cmd.viewMonth"), keywords: "month calendar view", run: () => { localStorage.setItem("gc_cal_view", "month"); go("/dashboard/calendar"); } },
      { id: "view-week", label: t("cmd.viewWeek"), keywords: "week calendar view", run: () => { localStorage.setItem("gc_cal_view", "week"); go("/dashboard/calendar"); } },
      { id: "view-day", label: t("cmd.viewDay"), keywords: "day calendar view", run: () => { localStorage.setItem("gc_cal_view", "day"); go("/dashboard/calendar"); } },
      { id: "meetings", label: t("cmd.goMeetings"), keywords: "meetings bookings", run: () => go("/dashboard/meetings") },
      { id: "event-types", label: t("cmd.goEventTypes"), keywords: "event types scheduling", run: () => go("/dashboard/event-types") },
      { id: "availability", label: t("cmd.goAvailability"), keywords: "availability schedule", run: () => go("/dashboard/availability") },
      { id: "team", label: t("cmd.goTeam"), keywords: "team members", run: () => go("/dashboard/team") },
      { id: "settings", label: t("cmd.goSettings"), keywords: "settings", run: () => go("/dashboard/settings") },
      { id: "profile", label: t("cmd.goProfile"), keywords: "profile account", run: () => go("/dashboard/profile") },
      { id: "theme-dark", label: t("cmd.themeDark"), keywords: "dark theme appearance", run: () => { setTheme("dark"); setOpen(false); } },
      { id: "theme-light", label: t("cmd.themeLight"), keywords: "light theme appearance", run: () => { setTheme("light"); setOpen(false); } },
    ],
    [t, go],
  );

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => (c.label + " " + c.keywords).toLowerCase().includes(q));
  }, [commands, query]);

  // Global hotkey: Cmd/Ctrl+K opens the palette (Esc closes); a custom event opens it too (sidebar).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openPalette();
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("gc:cmdk", openPalette);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("gc:cmdk", openPalette);
    };
  }, [openPalette]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 p-4 pt-[15vh]"
      onClick={() => setOpen(false)}
    >
      <div
        className="glass glass-opaque w-full max-w-lg overflow-hidden rounded-lg border border-border shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          autoFocus
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, results.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              results[active]?.run();
            }
          }}
          placeholder={t("cmd.placeholder")}
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm text-foreground outline-none"
        />
        <ul className="max-h-80 overflow-y-auto py-1">
          {results.length === 0 && (
            <li className="px-4 py-3 text-sm text-muted">{t("cmd.noResults")}</li>
          )}
          {results.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => c.run()}
                className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm transition ${
                  i === active ? "bg-accent/15 text-accent" : "text-foreground hover:bg-surface-2/50"
                }`}
              >
                <span>{c.label}</span>
                {c.hint && <span className="text-xs text-muted">{c.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-2xs text-muted">
          <span>↑↓ {t("cmd.navigate")}</span>
          <span>↵ {t("cmd.select")}</span>
          <span>esc {t("cmd.close")}</span>
        </div>
      </div>
    </div>
  );
}
