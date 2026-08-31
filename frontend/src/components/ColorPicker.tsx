"use client";

import { useEffect, useRef, useState } from "react";

import { CAL_COLORS } from "@/lib/colors";

/**
 * The coloured dot in front of a calendar, which now also changes that colour.
 *
 * The colour could only be chosen when the calendar was created, so the only way to fix a bad
 * choice was to delete the calendar — taking its events with it — or, for a connected one, to
 * disconnect and retype the server password. The dot was already the thing on screen that means
 * "this calendar's colour", so it is what opens the palette.
 *
 * It stays a sibling of the row's own button rather than a child of it: a button inside a button
 * is invalid markup, and browsers resolve it by dropping one of them.
 */
export default function ColorPicker({
  value,
  hidden = false,
  label,
  onPick,
}: {
  value: string;
  /** The row is toggled off, so the dot renders hollow — same cue as before. */
  hidden?: boolean;
  label: string;
  onPick: (color: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);

  // Click anywhere else and the palette closes. Without this it survives navigation inside the
  // page and ends up floating over an unrelated row.
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  return (
    <span ref={box} className="relative inline-flex">
      <button
        type="button"
        aria-label={label}
        onClick={() => setOpen((o) => !o)}
        className="h-2.5 w-2.5 rounded-full transition hover:scale-125"
        style={{
          backgroundColor: hidden ? "transparent" : value,
          boxShadow: `inset 0 0 0 1.5px ${value}`,
        }}
      />
      {open && (
        <span className="glass absolute left-0 top-4 z-20 flex gap-1.5 rounded-lg border border-border p-2">
          {CAL_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              aria-label={c}
              onClick={() => {
                setOpen(false);
                if (c !== value) onPick(c);
              }}
              className="h-4 w-4 rounded-full transition hover:scale-110"
              style={{
                backgroundColor: c,
                boxShadow:
                  c === value ? "0 0 0 2px var(--color-foreground)" : undefined,
              }}
            />
          ))}
        </span>
      )}
    </span>
  );
}
