"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { primaryButtonClass } from "@/components/AuthCard";
import { type InvitePreview, getEventInvite, respondEventInvite } from "@/lib/agenda";
import { useI18n } from "@/lib/i18n";
import {
  CalendarIcon,
} from "@/components/icons";

// Public RSVP page for a personal-event invitation. Zero-knowledge: the server only knows the time
// (the invitee already got the full details in the emailed ICS). No account required.
export default function InvitePage() {
  const { locale, t } = useI18n();
  const params = useParams();
  const token = String(params.token);
  const [preview, setPreview] = useState<InvitePreview | null | "loading">("loading");
  const [responded, setResponded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPreview(await getEventInvite(token));
  }, [token]);

  useEffect(() => {
    // Fetch-on-mount: the invitation preview comes from the network.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function respond(status: string) {
    if (await respondEventInvite(token, status)) {
      setResponded(status);
      await load();
    }
  }

  const when =
    preview && preview !== "loading"
      ? new Date(preview.start_at).toLocaleString(locale, {
          weekday: "long",
          year: "numeric",
          month: "long",
          day: "numeric",
          hour: preview.all_day ? undefined : "2-digit",
          minute: preview.all_day ? undefined : "2-digit",
        })
      : "";

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="glass flex w-full max-w-md flex-col gap-4 rounded-lg p-6 sm:p-8">
        <div className="flex items-center gap-2">
          <span aria-hidden className="text-2xl text-accent">
            <CalendarIcon />
          </span>
          <h1 className="text-xl font-semibold text-foreground">{t("invite.title")}</h1>
        </div>

        {preview === "loading" && <p className="text-sm text-muted">{t("common.loading")}</p>}
        {preview === null && <p className="text-sm text-red-400">{t("invite.notFound")}</p>}

        {preview && preview !== "loading" && (
          <>
            <p className="text-sm text-muted">{t("invite.when")}</p>
            <p className="text-foreground">{when}</p>
            <p className="text-xs text-muted">{t("invite.detailsNote")}</p>

            {responded ? (
              <p className="text-sm text-accent">
                {t("invite.thanks")} · {t(`att.${responded}`)}
              </p>
            ) : (
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => respond("accepted")}
                  className={primaryButtonClass}
                >
                  {t("invite.accept")}
                </button>
                <button
                  type="button"
                  onClick={() => respond("tentative")}
                  className="rounded-pill border border-border-strong px-4 py-2 text-sm text-foreground hover:bg-surface"
                >
                  {t("invite.maybe")}
                </button>
                <button
                  type="button"
                  onClick={() => respond("declined")}
                  className="rounded-pill border border-border-strong px-4 py-2 text-sm text-muted hover:text-red-400"
                >
                  {t("invite.decline")}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
