"use client";

import { LOCALES, useI18n } from "@/lib/i18n";

export default function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale } = useI18n();
  return (
    <div className={`flex items-center gap-1 text-xs ${className}`}>
      {LOCALES.map((l) => (
        <button
          key={l.code}
          type="button"
          onClick={() => setLocale(l.code)}
          className={[
            "rounded px-1.5 py-0.5 transition",
            locale === l.code ? "text-accent" : "text-muted/60 hover:text-foreground",
          ].join(" ")}
          aria-pressed={locale === l.code}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
