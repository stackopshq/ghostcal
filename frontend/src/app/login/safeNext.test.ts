import { describe, expect, it } from "vitest";
import { safeNextPath } from "@/app/login/page";

// The ?next= destination (used by the GhostMail deep-link bridge through login) must never become
// an open redirect: only same-origin relative paths are allowed.
describe("safeNextPath", () => {
  it("keeps a same-origin relative path (incl. query)", () => {
    expect(safeNextPath("/dashboard/calendar?add=Lunch")).toBe("/dashboard/calendar?add=Lunch");
    expect(safeNextPath("/dashboard/tasks")).toBe("/dashboard/tasks");
  });

  it("falls back to /dashboard when next is missing", () => {
    expect(safeNextPath(null)).toBe("/dashboard");
    expect(safeNextPath("")).toBe("/dashboard");
  });

  it("rejects protocol-relative and absolute URLs (open-redirect guard)", () => {
    expect(safeNextPath("//evil.example.com")).toBe("/dashboard");
    expect(safeNextPath("https://evil.example.com")).toBe("/dashboard");
    expect(safeNextPath("http://evil.example.com")).toBe("/dashboard");
    expect(safeNextPath("/\\evil.example.com")).toBe("/dashboard");
    expect(safeNextPath("javascript:alert(1)")).toBe("/dashboard");
  });
});
