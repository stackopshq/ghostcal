import { afterEach, describe, expect, it, vi } from "vitest";
import { openInGhostMail } from "@/lib/ghostmail";

// The "Email guests" bridge opens GhostMail's composer via a deep-link. Assert the URL contract
// (path + query) GhostMail's /dashboard?compose= handler reads.
afterEach(() => vi.restoreAllMocks());

describe("openInGhostMail", () => {
  it("opens GhostMail's compose deep-link with recipients and subject", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    openInGhostMail({ to: ["alice@northwind.io", "bob@aurora.dev"], subject: "Design review" });
    expect(open).toHaveBeenCalledTimes(1);
    const url = new URL((open.mock.calls[0] as [string])[0]);
    expect(url.pathname).toBe("/dashboard");
    expect(url.searchParams.get("compose")).toBe("1");
    expect(url.searchParams.get("to")).toBe("alice@northwind.io,bob@aurora.dev");
    expect(url.searchParams.get("subject")).toBe("Design review");
  });

  it("targets a new tab with noopener", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    openInGhostMail({ to: ["a@b.co"], subject: "Hi" });
    expect(open.mock.calls[0][1]).toBe("_blank");
    expect(open.mock.calls[0][2]).toBe("noopener");
  });
});
