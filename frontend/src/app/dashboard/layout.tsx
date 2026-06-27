"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DashboardUserContext } from "@/components/dashboard-context";
import { getMe, isAuthenticated, logout, type User } from "@/lib/auth";

const ICONS: Record<string, string> = {
  events: "M9 17l6-6-6-6M5 21V3",
  availability: "M12 7v5l3 2M12 21a9 9 0 100-18 9 9 0 000 18z",
  meetings: "M8 3v3M16 3v3M4 8h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z",
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
  { href: "/dashboard/event-types", label: "Event types", icon: ICONS.events },
  { href: "/dashboard/meetings", label: "Meetings", icon: ICONS.meetings },
  { href: "/dashboard/availability", label: "Availability", icon: ICONS.availability },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => router.replace("/login"))
      .finally(() => setReady(true));
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  if (!ready || !user) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <p className="text-sm text-muted">Loading…</p>
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

        <Link
          href="/dashboard/event-types"
          className="mb-6 flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_rgba(0,240,255,0.35)] transition hover:brightness-110"
        >
          <Glyph d={ICONS.plus} /> Create
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
                <Glyph d={item.icon} /> {item.label}
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
            <Glyph d={ICONS.logout} /> Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="min-w-0 flex-1">
        <DashboardUserContext.Provider value={user}>{children}</DashboardUserContext.Provider>
      </div>
    </div>
  );
}
