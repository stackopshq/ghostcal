import { afterEach, describe, expect, it } from "vitest";
import { completeOidcSession, getAccessToken } from "@/lib/auth";

// The OIDC callback delivers session tokens in the URL fragment. completeOidcSession must capture
// them into storage and strip the fragment; anything else must be a no-op.
afterEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/auth/callback");
});

describe("completeOidcSession", () => {
  it("captures tokens from the fragment and strips it", () => {
    window.history.replaceState(null, "", "/auth/callback#access_token=acc.1&refresh_token=ref.1");
    expect(completeOidcSession()).toBe(true);
    expect(getAccessToken()).toBe("acc.1");
    expect(localStorage.getItem("gc_refresh")).toBe("ref.1");
    expect(window.location.hash).toBe(""); // fragment removed from history
  });

  it("is a no-op when the fragment is absent or incomplete", () => {
    window.history.replaceState(null, "", "/auth/callback");
    expect(completeOidcSession()).toBe(false);
    expect(getAccessToken()).toBeNull();

    window.history.replaceState(null, "", "/auth/callback#access_token=only-access");
    expect(completeOidcSession()).toBe(false);
    expect(getAccessToken()).toBeNull();
  });
});
