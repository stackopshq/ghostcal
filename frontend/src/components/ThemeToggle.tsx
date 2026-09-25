"use client";

import {
  MoonIcon,
  SunIcon,
} from "@/components/icons";

// Flips the theme on <html> and persists it. The visible icon is driven purely by CSS from the
// data-theme attribute (see globals.css), so there is no React state and no hydration mismatch.
export default function ThemeToggle({ className = "" }: { className?: string }) {
  function toggle() {
    const root = document.documentElement;
    const next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    try {
      localStorage.setItem("gc_theme", next);
    } catch {
      /* ignore */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle light/dark theme"
      title="Toggle theme"
      className={`text-sm leading-none transition hover:opacity-80 ${className}`}
    >
      <span className="theme-icon-sun" aria-hidden>
        <SunIcon />
      </span>
      <span className="theme-icon-moon" aria-hidden>
        <MoonIcon />
      </span>
    </button>
  );
}
