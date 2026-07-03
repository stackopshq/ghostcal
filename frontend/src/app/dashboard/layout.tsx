"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import CommandPalette from "@/components/CommandPalette";
import { DashboardUserContext } from "@/components/dashboard-context";
import NotificationsManager from "@/components/NotificationsManager";
import OrgSwitcher from "@/components/OrgSwitcher";
import SuiteSwitcher from "@/components/SuiteSwitcher";
import { getMe, isAuthenticated, logout, type User } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const ICONS: Record<string, string> = {
  events: "M9 17l6-6-6-6M5 21V3",
  availability: "M12 7v5l3 2M12 21a9 9 0 100-18 9 9 0 000 18z",
  meetings: "M8 3v3M16 3v3M4 8h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z",
  calendar: "M8 3v3M16 3v3M4 8h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM9 13h2v2H9z",
  tasks: "M9 11l3 3 8-8M4 6h6M4 12h4M4 18h10",
  settings: "M4 21v-7M4 10V3M12 21v-9M12 5V3M20 21v-5M20 11V3M1 14h6M9 5h6M17 16h6",
  team: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75",
  polls: "M18 20V10M12 20V4M6 20v-6",
  analytics: "M3 3v18h18M7 16l4-4 3 3 5-6",
  profile: "M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z",
  plus: "M12 5v14M5 12h14",
  logout: "M16 17l5-5-5-5M21 12H9M13 21H5a2 2 0 01-2-2V5a2 2 0 012-2h8",
};

function Glyph({ d, className = "h-4 w-4" }: { d: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  );
}

const NAV = [
  { href: "/dashboard/event-types", labelKey: "nav.events", icon: ICONS.events },
  { href: "/dashboard/calendar", labelKey: "nav.calendar", icon: ICONS.calendar },
  { href: "/dashboard/tasks", labelKey: "nav.tasks", icon: ICONS.tasks },
  { href: "/dashboard/meetings", labelKey: "nav.meetings", icon: ICONS.meetings },
  { href: "/dashboard/analytics", labelKey: "nav.analytics", icon: ICONS.analytics },
  { href: "/dashboard/polls", labelKey: "nav.polls", icon: ICONS.polls },
  { href: "/dashboard/availability", labelKey: "nav.availability", icon: ICONS.availability },
  { href: "/dashboard/team", labelKey: "nav.team", icon: ICONS.team },
  { href: "/dashboard/profile", labelKey: "nav.profile", icon: ICONS.profile },
  { href: "/dashboard/settings", labelKey: "nav.settings", icon: ICONS.settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Preserve where the user was headed (path + query, e.g. a GhostMail ?add= deep link) so login
    // can send them back there instead of dropping the intent on the floor.
    const dest = window.location.pathname + window.location.search;
    const loginUrl = `/login?next=${encodeURIComponent(dest)}`;
    if (!isAuthenticated()) {
      router.replace(loginUrl);
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => router.replace(loginUrl))
      .finally(() => setReady(true));
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  if (!ready || !user) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <p className="text-sm text-muted">{t("common.loading")}</p>
      </div>
    );
  }

  const initials = user.name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex flex-1">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface-2/40 p-4">
        <Link href="/dashboard" className="mb-6 flex items-center gap-2 px-2 py-1">
          <span className="text-lg text-accent">●</span>
          <span className="text-lg font-semibold tracking-tight text-foreground">GhostCal</span>
        </Link>

        <SuiteSwitcher />

        <OrgSwitcher />

        <button
          type="button"
          onClick={() => window.dispatchEvent(new Event("gc:cmdk"))}
          className="mb-3 flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm text-muted transition hover:text-accent"
        >
          <span>{t("cmd.open")}</span>
          <kbd className="rounded border border-border-strong px-1.5 py-0.5 text-[10px]">⌘K</kbd>
        </button>

        <Link
          href="/dashboard/event-types"
          className="mb-6 flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.35)] transition hover:brightness-110"
        >
          <Glyph d={ICONS.plus} /> {t("dash.create")}
        </Link>

        <nav className="flex flex-col gap-1">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={[
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                  active
                    ? "bg-accent/10 text-accent"
                    : "text-muted hover:bg-surface hover:text-foreground",
                ].join(" ")}
              >
                <Glyph d={item.icon} /> {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto border-t border-border pt-4">
          <div className="flex items-center gap-3 px-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-accent/30 to-accent/5 text-xs font-semibold text-accent ring-1 ring-border-strong">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-foreground">{user.name}</p>
              <p className="truncate text-xs text-muted">{user.email}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="mt-3 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-surface hover:text-foreground"
          >
            <Glyph d={ICONS.logout} /> {t("dash.signOut")}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="min-w-0 flex-1">
        <DashboardUserContext.Provider value={user}>{children}</DashboardUserContext.Provider>
      </div>
      <NotificationsManager />
      <CommandPalette />
    </div>
  );
}
