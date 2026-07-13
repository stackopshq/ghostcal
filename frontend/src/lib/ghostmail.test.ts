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

describe("sending an availability link", () => {
  it("carries the link in the body — the link IS the message", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    openInGhostMail({
      to: [],
      subject: "When I am free",
      body: "Here is when I am busy:\n\nhttps://cal.example.com/b/tok3n\n",
    });
    const url = new URL((open.mock.calls[0] as [string])[0]);
    expect(url.searchParams.get("body")).toContain(
      "https://cal.example.com/b/tok3n",
    );
    // No recipients: "who is this for" is a question for the composer, not for us.
    expect(url.searchParams.get("to")).toBe("");
  });

  it("omits the body entirely when there is none", () => {
    // "Email these guests about this event" needs no body — the subject carries it, and an empty
    // body= in the URL would be noise GhostMail has to decide what to do with.
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    openInGhostMail({ to: ["a@b.co"], subject: "Design review" });
    const url = new URL((open.mock.calls[0] as [string])[0]);
    expect(url.searchParams.has("body")).toBe(false);
  });
});
