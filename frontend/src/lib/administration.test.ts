import { describe, expect, it } from "vitest";
import {
  actionsFor,
  confirmationMatches,
  needsConfirmation,
  type AdminAccount,
} from "@/lib/administration";
import { ApiError } from "@/lib/api";
import { lireLEchecDeConnexion } from "@/lib/deuxiemeFacteur";

const account: AdminAccount = {
  id: "3f1c",
  email: "camille.martin@exemple.ch",
  name: "Camille Martin",
  created_at: "2026-11-01T09:00:00Z",
  email_verified: true,
  last_login_at: null,
  two_factor_enabled: false,
  suspended_at: null,
  is_admin: false,
};

describe("administration", () => {
  it("an administrator is out of reach of the view", () => {
    expect(actionsFor({ ...account, is_admin: true })).toEqual([]);
  });

  it("offers suspend or reactivate, never both", () => {
    expect(actionsFor(account)).toEqual(["suspend", "delete"]);
    expect(actionsFor({ ...account, suspended_at: "2026-11-19T10:00:00Z" })).toEqual([
      "reactivate",
      "delete",
    ]);
  });

  it("the typed address is compared as the server compares it", () => {
    expect(confirmationMatches(account, "  Camille.Martin@Exemple.ch ")).toBe(true);
    expect(confirmationMatches(account, "camille@exemple.ch")).toBe(false);
  });

  it("only opening sign-up asks for confirmation", () => {
    expect(needsConfirmation(true)).toBe(true);
    expect(needsConfirmation(false)).toBe(false);
  });
});

describe("codes the server sends", () => {
  it("reads the machine code beside the message", () => {
    const body = JSON.stringify({ detail: { detail: "registration is closed", code: "registration_closed" } });
    expect(new ApiError(403, body).code).toBe("registration_closed");
    expect(new ApiError(403, JSON.stringify({ detail: "email not verified" })).code).toBe("");
    expect(new ApiError(502, "<html>bad gateway</html>").code).toBe("");
  });

  it("a suspended account is not told to verify its address", () => {
    const suspended = {
      status: 403,
      message: JSON.stringify({ detail: { detail: "account suspended", code: "account_suspended" } }),
    };
    expect(lireLEchecDeConnexion(suspended, false)).toEqual({ quoi: "compte-suspendu" });
    const unverified = { status: 403, message: JSON.stringify({ detail: "email not verified" }) };
    expect(lireLEchecDeConnexion(unverified, false)).toEqual({ quoi: "email-non-verifie" });
  });
});
