"use client";

import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import {
  createWebhook,
  deleteWebhook,
  listWebhookEvents,
  listWebhooks,
  type Webhook,
} from "@/lib/webhooks";

export default function WebhookSettings() {
  const t = useT();
  const [hooks, setHooks] = useState<Webhook[]>([]);
  const [events, setEvents] = useState<string[]>([]);
  const [url, setUrl] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([listWebhooks(), listWebhookEvents()])
      .then(([h, e]) => {
        if (!active) return;
        setHooks(h);
        setEvents(e);
      })
      .catch(() => active && setError(t("webhooks.errLoad")));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh]);

  function toggle(ev: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(ev)) next.delete(ev);
      else next.add(ev);
      return next;
    });
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSecret(null);
    if (picked.size === 0) {
      setError(t("webhooks.pickEvent"));
      return;
    }
    try {
      const created = await createWebhook(url, [...picked]);
      setSecret(created.secret);
      setUrl("");
      setPicked(new Set());
      setRefresh((r) => r + 1);
    } catch {
      setError(t("webhooks.errCreate"));
    }
  }

  async function remove(id: string) {
    await deleteWebhook(id);
    setRefresh((r) => r + 1);
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t("webhooks.title")}</h2>
        <p className="mt-1 text-sm text-muted">{t("webhooks.sub")}</p>
      </div>

      {hooks.map((h) => (
        <div
          key={h.id}
          className="flex items-center justify-between rounded-lg border border-border px-4 py-3 text-sm"
        >
          <div>
            <p className="text-foreground">{h.url}</p>
            <p className="text-muted">{h.event_types.join(", ")}</p>
          </div>
          <button
            type="button"
            onClick={() => remove(h.id)}
            className="text-muted transition hover:text-red-400"
          >
            {t("common.delete")}
          </button>
        </div>
      ))}

      {secret && (
        <p className="rounded-lg border border-accent/40 bg-surface-2/50 px-4 py-3 text-sm text-foreground">
          {t("webhooks.secretOnce")} <span className="text-accent">{secret}</span>
        </p>
      )}

      <form onSubmit={add} className="flex flex-col gap-3 border-t border-border pt-4">
        <input
          required
          type="url"
          placeholder="https://example.com/webhook"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="rounded border border-border-strong bg-surface-2 px-4 py-2.5 text-sm text-foreground outline-none focus:border-accent"
        />
        <div className="flex flex-wrap gap-2">
          {events.map((ev) => {
            const on = picked.has(ev);
            return (
              <button
                key={ev}
                type="button"
                onClick={() => toggle(ev)}
                className={[
                  "rounded-pill border px-3 py-1.5 text-xs transition",
                  on ? "border-accent text-accent" : "border-border-strong text-muted",
                ].join(" ")}
              >
                {ev}
              </button>
            );
          })}
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          className="self-start rounded-pill bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-[0_0_18px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition hover:brightness-110"
        >
          {t("webhooks.add")}
        </button>
      </form>
    </div>
  );
}
