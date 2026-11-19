"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import Administration from "@/components/Administration";
import { useT } from "@/lib/i18n";

export default function AdminPage() {
  const t = useT();
  const router = useRouter();
  // The server answers 404 to an ordinary account: so does the page.
  const notFound = useCallback(() => router.replace("/dashboard"), [router]);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6 sm:p-10">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t("admin.title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("admin.sub")}</p>
      </div>
      <Administration onNotFound={notFound} />
    </main>
  );
}
