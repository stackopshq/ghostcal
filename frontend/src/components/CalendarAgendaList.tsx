"use client";

import { useMemo } from "react";
import type { GridItem } from "@/components/CalendarTimeGrid";

/**
 * What is coming up, as a list.
 *
 * The month/week/day grids answer "when is this?". This one answers "what is next?" — which is the
 * question people actually open a calendar to ask, and the one a grid is worst at when the day is
 * mostly empty.
 *
 * Titles here are already decrypted: the page unseals them in the browser before handing them over,
 * exactly as the grid views get them. Nothing new is exposed by listing them.
 */
export default function CalendarAgendaList({
  items,
  locale,
  onEventClick,
  labels,
}: {
  items: GridItem[];
  locale: string;
  onEventClick: (item: GridItem) => void;
  labels: { allDay: string; empty: string; sharedReadOnly: string };
}) {
  const days = useMemo(() => {
    const byDay = new Map<string, { date: Date; items: GridItem[] }>();
    for (const item of [...items].sort((a, b) =>
      a.start.localeCompare(b.start),
    )) {
      const d = new Date(item.start);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const bucket = byDay.get(key);
      if (bucket) bucket.items.push(item);
      else
        byDay.set(key, {
          date: new Date(d.getFullYear(), d.getMonth(), d.getDate()),
          items: [item],
        });
    }
    return [...byDay.values()];
  }, [items]);

  if (days.length === 0) {
    return (
      <div className="glass rounded-lg p-10 text-center text-sm text-muted">
        {labels.empty}
      </div>
    );
  }

  const today = new Date();
  const isToday = (d: Date) =>
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate();

  return (
    <div className="glass flex flex-col divide-y divide-border rounded-lg">
      {days.map(({ date, items: dayItems }) => (
        <div
          key={date.toISOString()}
          className="flex gap-4 p-4 sm:gap-6 sm:p-5"
        >
          <div className="w-20 shrink-0 sm:w-28">
            <p
              className={`text-sm font-medium ${isToday(date) ? "text-accent" : "text-foreground"}`}
            >
              {date.toLocaleDateString(locale, {
                weekday: "short",
                day: "numeric",
              })}
            </p>
            <p className="text-xs text-muted">
              {date.toLocaleDateString(locale, { month: "short" })}
            </p>
          </div>

          <ul className="flex flex-1 flex-col gap-2">
            {dayItems.map((item) => (
              <li key={`${item.source}-${item.event_id ?? item.start}`}>
                <button
                  type="button"
                  onClick={() => onEventClick(item)}
                  className="flex w-full items-center gap-3 rounded-pill px-2 py-1.5 text-left transition hover:bg-surface-2/60"
                >
                  <span
                    aria-hidden
                    className="h-8 w-1 shrink-0 rounded-pill"
                    style={{ backgroundColor: item.color ?? "var(--accent)" }}
                  />
                  {/* `w-16 sm:w-24` : « 13:40 » n'a jamais eu besoin de 96 px.
                      Sur un écran de 390 px, ces 96 px se prenaient sur le
                      titre, qui est la seule chose qu'on cherche dans une
                      liste. */}
                  <span className="w-16 shrink-0 text-xs tabular-nums text-muted sm:w-24">
                    {item.all_day
                      ? labels.allDay
                      : new Date(item.start).toLocaleTimeString(locale, {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                  </span>
                  {/* `min-w-0` n'est pas cosmétique : un enfant flex refuse par
                      défaut de descendre sous la largeur de son contenu, donc
                      `truncate` ne s'applique JAMAIS sans lui. C'est pour ça
                      que la carte débordait de l'écran au lieu de couper. */}
                  <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                    {item.label}
                  </span>
                  {item.read_only && (
                    // Était `shrink-0` : ~200 px que rien ne pouvait reprendre,
                    // sur les 390 px d'un téléphone. Il ne restait plus de place
                    // pour le titre, réduit à « R… ». Sous `sm` un cadenas dit la
                    // même chose en 12 px, et la phrase reste accessible au
                    // lecteur d'écran comme au survol.
                    <span
                      title={labels.sharedReadOnly}
                      className="shrink-0 text-xs text-muted"
                    >
                      <span aria-hidden className="sm:hidden">
                        🔒
                      </span>
                      <span className="sr-only sm:not-sr-only">
                        {labels.sharedReadOnly}
                      </span>
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
