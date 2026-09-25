/**
 * Every size and every radius in the interface comes from the suite's charter.
 *
 * The charter (`ghostsuite`, `tools/brand/emit_theme.py`) fixes seven typographic steps and four
 * radii. Tailwind offers many more, and its extras are not neutral: they are *not bridged*, so a
 * `text-3xl` silently takes Tailwind's own 1.875rem instead of anything the suite decided. An
 * arbitrary `text-[11px]` skips the scale altogether.
 *
 * Measured on 2026-08-30, before this was pinned: 3 × `text-3xl`, 1 × `text-4xl`, 11 ×
 * `text-[10px]` and 7 × `text-[11px]` — twenty-two places where the product had quietly written
 * its own scale. None of them looked wrong on screen, which is exactly why nobody caught them.
 *
 * This suite renders no components, so anything living in JSX is beyond the reach of a normal
 * test. Reading the source is the only form that reaches it — and the only one that will still be
 * there for the next screen somebody adds.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// Vitest roots at `frontend/`, and `import.meta.url` is not a file URL once the file has been
// transformed — the first attempt died on exactly that.
const SRC = join(process.cwd(), "src");

/** The charter's seven steps. `2xs` is ours — Tailwind has no such name. */
const TYPE_STEPS = new Set(["2xs", "xs", "sm", "base", "lg", "xl", "2xl"]);

/** The charter's four radii. The bare name is the step it calls DEFAULT. */
const RADIUS_STEPS = new Set(["", "sm", "lg", "pill"]);

/** Tailwind's `text-*` also carries colour and alignment; only lengths are sizes. */
const ARBITRARY_LENGTH = /^\[[0-9.]+(px|rem|em|pt|%)\]$/;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    if (!/\.tsx?$/.test(name) || /\.test\.tsx?$/.test(name)) return [];
    return [path];
  });
}

/** Every `text-…` and `rounded…` token in the tree, with where it was found. */
function tokens(): { file: string; token: string }[] {
  return sourceFiles(SRC).flatMap((file) => {
    const text = readFileSync(file, "utf8");
    return [...text.matchAll(/\b(?:text|rounded)(?:-[A-Za-z0-9[\]%.]+)*/g)].map(
      (m) => ({ file: file.slice(SRC.length + 1), token: m[0] }),
    );
  });
}


/** The opening tag starting at `from`, following JSX braces so `className={…}` stays intact. */
function openingTag(text: string, from: number): string {
  let depth = 0;
  for (let i = from; i < text.length; i++) {
    const c = text[i];
    if (c === "{") depth++;
    else if (c === "}") depth--;
    else if (c === ">" && depth === 0) return text.slice(from, i + 1);
  }
  return text.slice(from, from + 500);
}

/** Every `<button|input|select|textarea>` opening tag that names a radius of its own. */
function shapedElements(): { file: string; element: string; tag: string }[] {
  const found: { file: string; element: string; tag: string }[] = [];
  for (const file of sourceFiles(SRC)) {
    if (!file.endsWith(".tsx")) continue;
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(/<(button|input|select|textarea)\b/g)) {
      const tag = openingTag(text, m.index ?? 0);
      if (!/\brounded(-(sm|lg|pill))?\b/.test(tag)) continue; // defers to a shared constant
      found.push({ file: file.slice(SRC.length + 1), element: m[1], tag });
    }
  }
  return found;
}

describe("the interface stays on the suite's scale", () => {
  it("is actually reading the source tree", () => {
    // A scan that finds nothing passes every assertion below while proving nothing. If the root
    // ever moves, this is the test that says so instead of the suite going quietly green.
    expect(sourceFiles(SRC).length).toBeGreaterThan(50);
    expect(tokens().length).toBeGreaterThan(200);
  });

  it("uses no type size the charter does not define", () => {
    const strays = tokens()
      .filter(({ token }) => token.startsWith("text-"))
      .filter(({ token }) => {
        const rest = token.slice("text-".length);
        if (ARBITRARY_LENGTH.test(rest)) return true;
        // Tailwind's sizes above the charter's ceiling. Its lower ones share the charter's names.
        return /^(3xl|4xl|5xl|6xl|7xl|8xl|9xl)$/.test(rest);
      });

    expect(
      strays.map((s) => `${s.file}: ${s.token}`),
      "these sizes are not on the suite's scale: named ones fall back to Tailwind's own value, " +
        "arbitrary ones skip the scale entirely. The charter's steps are " +
        [...TYPE_STEPS].map((s) => `text-${s}`).join(", "),
    ).toEqual([]);
  });

  it("uses no radius the charter does not define", () => {
    const strays = tokens()
      .filter(({ token }) => token === "rounded" || token.startsWith("rounded-"))
      .filter(({ token }) => {
        // Directional variants (`rounded-t`, `rounded-tl`) carry the same steps; drop the side.
        const rest = token
          .slice("rounded".length)
          .replace(/^-(t|r|b|l|s|e|tl|tr|br|bl|ss|se|es|ee)(?=$|-)/, "");
        const step = rest.replace(/^-/, "");
        if (ARBITRARY_LENGTH.test(step)) return true;
        return !RADIUS_STEPS.has(step);
      });

    expect(
      strays.map((s) => `${s.file}: ${s.token}`),
      "these radii are not on the suite's scale. The charter's steps are rounded, rounded-sm, " +
        "rounded-lg, rounded-pill",
    ).toEqual([]);
  });
});

describe("shape says what an object is", () => {
  it("is reading tags, not just files", () => {
    // Same reason as above: a selector that matches nothing passes every assertion below.
    expect(shapedElements().length).toBeGreaterThan(50);
  });

  it("gives every button the control shape", () => {
    const strays = shapedElements()
      .filter((e) => e.element === "button")
      // A positioned block in the time grid is clickable content, not a control: its height is
      // computed, and one radius cannot give a 20px and a 200px block the same shape.
      .filter((e) => !e.tag.includes("absolute"))
      .filter((e) => !/\brounded-pill\b/.test(e.tag));

    expect(
      strays.map((e) => `${e.file}: ${e.tag.slice(0, 60)}…`),
      "a button is a control and controls are pill-shaped. Until 2026-08-31 the shared input and " +
        "the shared primary button carried the same radius, the same height and the same padding, " +
        "so on the privacy screen a field and a Save button differed only by colour",
    ).toEqual([]);
  });

  it("gives every field the input shape", () => {
    const strays = shapedElements()
      .filter((e) => e.element !== "button")
      .filter((e) => !/\brounded\b(?!-)/.test(e.tag));

    expect(
      strays.map((e) => `${e.file}: ${e.element}`),
      "something you fill has the input shape; the container around it is the one that carries lg",
    ).toEqual([]);
  });
});
