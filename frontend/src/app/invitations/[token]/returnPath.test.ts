import { describe, expect, it } from "vitest";
import { invitationReturnPath } from "@/app/invitations/[token]/page";
import { safeNextPath } from "@/app/login/page";

// Sign-in from an invitation must come back to the invitation, grant key included, or the
// acceptance never fires (production, 2026-10-20: login landed on the dashboard instead).
describe("invitationReturnPath", () => {
  it("points back at the invitation page", () => {
    expect(invitationReturnPath("abc123", "")).toBe("/invitations/abc123");
  });

  it("carries the #k= grant key, which only the browser ever sees", () => {
    expect(invitationReturnPath("abc123", "#k=s3cr3t")).toBe("/invitations/abc123#k=s3cr3t");
  });

  it("survives the login ?next= guard round-trip", () => {
    const dest = invitationReturnPath("abc123", "#k=s3cr3t");
    const query = new URLSearchParams(`next=${encodeURIComponent(dest)}`);
    expect(safeNextPath(query.get("next"))).toBe(dest);
  });
});
