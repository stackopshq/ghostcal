"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { primaryButtonClass } from "@/components/AuthCard";
import { getMe, isAuthenticated, logout, type User } from "@/lib/auth";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  if (loading) {
    return (
      <main className="flex flex-1 items-center justify-center p-8">
        <p className="text-sm text-muted">Loading…</p>
      </main>
    );
  }

  if (!user) return null;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6 sm:p-10">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium tracking-wide text-muted">
          <span className="text-accent">●</span> GhostCal
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="rounded-lg border border-border-strong px-3 py-2 text-sm text-foreground transition hover:border-accent hover:text-accent"
        >
          Sign out
        </button>
      </header>

      <section className="glass rounded-2xl p-8">
        <h1 className="text-2xl font-semibold text-foreground">Welcome, {user.name}</h1>
        <p className="mt-1 text-sm text-muted">{user.email}</p>
        <p className="mt-4 text-sm text-muted">
          Set the hours you&apos;re available, then create bookable event types (coming next).
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/dashboard/availability" className={primaryButtonClass}>
            Edit availability
          </Link>
          <Link
            href="/dashboard/event-types"
            className="rounded-lg border border-border-strong px-4 py-2.5 text-sm font-medium text-foreground transition hover:border-accent hover:text-accent"
          >
            Event types
          </Link>
        </div>
      </section>
    </main>
  );
}
