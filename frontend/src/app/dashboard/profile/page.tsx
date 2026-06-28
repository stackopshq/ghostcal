"use client";

import ProfileSettings from "@/components/ProfileSettings";

export default function ProfilePage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Profile</h1>
        <p className="mt-1 text-sm text-muted">Your name, avatar, timezone and password.</p>
      </div>
      <section className="glass rounded-2xl p-6 sm:p-8">
        <ProfileSettings />
      </section>
    </main>
  );
}
