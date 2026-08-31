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
