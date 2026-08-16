import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { openInGhostMail, resetGhostMailUrlCache } from "@/lib/ghostmail";

// The "Email guests" bridge opens GhostMail's composer via a deep-link. Assert the URL contract
// (path + query) GhostMail's /dashboard?compose= handler reads.
//
// The address now comes from the deployment at runtime rather than from a NEXT_PUBLIC_ variable
// compiled into the bundle, so these tests stub that lookup. That is the whole point of the change:
// one image serves every deployment, and the tests say which address it used.
vi.mock("@/lib/auth", () => ({ getAuthConfig: vi.fn() }));
import { getAuthConfig } from "@/lib/auth";

const MAIL = "https://ghostmail.example.com";

function withGhostMail(url: string | null) {
  vi.mocked(getAuthConfig).mockResolvedValue({
    oidc_enabled: false,
    ghostmail_url: url,
  });
}

beforeEach(() => {
  resetGhostMailUrlCache();
  withGhostMail(MAIL);
});
afterEach(() => vi.restoreAllMocks());

describe("openInGhostMail", () => {
  it("opens GhostMail's compose deep-link with recipients and subject", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await openInGhostMail({
      to: ["alice@northwind.io", "bob@aurora.dev"],
      subject: "Design review",
    });
    expect(open).toHaveBeenCalledTimes(1);
    const url = new URL((open.mock.calls[0] as [string])[0]);
    expect(url.origin).toBe(MAIL);
    expect(url.pathname).toBe("/dashboard");
    expect(url.searchParams.get("compose")).toBe("1");
    expect(url.searchParams.get("to")).toBe("alice@northwind.io,bob@aurora.dev");
    expect(url.searchParams.get("subject")).toBe("Design review");
  });

  it("targets a new tab with noopener", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await openInGhostMail({ to: ["a@b.co"], subject: "Hi" });
    expect(open.mock.calls[0][1]).toBe("_blank");
    expect(open.mock.calls[0][2]).toBe("noopener");
  });

  it("opens nothing when the deployment has no GhostMail", async () => {
    // The button is hidden in that case, but the guard belongs here too: a caller that shows it
    // anyway must learn nothing happened rather than open a tab into the void — which is exactly
    // what the compiled-in localhost default used to do.
    withGhostMail(null);
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const opened = await openInGhostMail({ to: ["a@b.co"], subject: "Hi" });
    expect(opened).toBe(false);
    expect(open).not.toHaveBeenCalled();
  });

  it("asks the deployment once, not once per click", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    await openInGhostMail({ to: ["a@b.co"], subject: "One" });
    await openInGhostMail({ to: ["a@b.co"], subject: "Two" });
    expect(vi.mocked(getAuthConfig)).toHaveBeenCalledTimes(1);
  });
});

describe("sending an availability link", () => {
  it("carries the link in the body — the link IS the message", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await openInGhostMail({
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

  it("omits the body entirely when there is none", async () => {
    // "Email these guests about this event" needs no body — the subject carries it, and an empty
    // body= in the URL would be noise GhostMail has to decide what to do with.
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await openInGhostMail({ to: ["a@b.co"], subject: "Design review" });
    const url = new URL((open.mock.calls[0] as [string])[0]);
    expect(url.searchParams.has("body")).toBe(false);
  });
});
