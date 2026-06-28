"use client";

import ProfileSettings from "@/components/ProfileSettings";
import { useT } from "@/lib/i18n";

export default function ProfilePage() {
  const t = useT();
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t("profile.pageTitle")}</h1>
        <p className="mt-1 text-sm text-muted">{t("profile.pageSub")}</p>
      </div>
      <section className="glass rounded-2xl p-6 sm:p-8">
        <ProfileSettings />
      </section>
    </main>
  );
}
