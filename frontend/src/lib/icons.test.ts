/**
 * No emoji stands in for an icon.
 *
 * Emoji were doing that job in twenty-four places. They are not a typeface anyone chose: each
 * platform draws its own, at its own weight, in its own colours, and none of them follows the
 * accent or the text beside it. On a product sold on how it looks, the one element repeated on
 * every screen was the one we did not control.
 *
 * The weather glyphs are a different thing and are deliberately still allowed: `weatherGlyph()`
 * maps WMO codes to a symbol, so replacing them is a mapping to nine more drawn figures, not a
 * substitution. That is its own change, and this test will be tightened when it lands.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

/** Typographic marks, not pictures: ✓ and ✕ are punctuation and stay. */
const ALLOWED = new Set(["✓", "✕", "✔", "✖", "×", "→", "←", "·", "⌘", "↻", "⌄"]);

/** Weather, until the mapping moves to drawn figures. */
const WEATHER = new Set([
  "☀️", "⛅", "☁️", "🌫️", "🌦️", "🌧️", "🌨️", "⛈️", "🌡️",
  "☀", "☁", "🌫", "🌦", "🌧", "🌨", "⛈", "🌡",
]);

const PICTOGRAPH =
  /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/gu;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    if (!/\.tsx$/.test(name)) return [];
    return [path];
  });
}

describe("icons are drawn, not typed", () => {
  it("is actually reading components", () => {
    // A sweep that finds nothing passes the assertion below while proving nothing.
    expect(sourceFiles(SRC).length).toBeGreaterThan(30);
  });

  it("has no emoji standing in for an icon", () => {
    const strays: string[] = [];
    for (const file of sourceFiles(SRC)) {
      if (file.endsWith("icons.tsx")) continue; // its header names what it replaced
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(PICTOGRAPH)) {
        const char = m[0];
        if (char === "️") continue; // a variation selector rides on the char before it
        if (ALLOWED.has(char) || WEATHER.has(char)) continue;
        strays.push(`${file.slice(SRC.length + 1)}: ${char}`);
      }
    }

    expect(
      [...new Set(strays)],
      "these are emoji doing an icon's job. Every platform draws its own, so they follow neither " +
        "the accent nor the text colour beside them. Use a figure from components/icons.tsx",
    ).toEqual([]);
  });
});
