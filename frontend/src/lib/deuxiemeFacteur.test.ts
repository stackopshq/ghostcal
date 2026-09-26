import { describe, expect, it } from "vitest";
import { lireLEchecDeConnexion } from "./deuxiemeFacteur";

// FastAPI imbrique : le corps réel est `{"detail": {"detail": …, "mfa_required": true}}`.
const corps = (interieur: Record<string, unknown>) => JSON.stringify({ detail: interieur });

const REQUIS = corps({ detail: "two-factor code required", mfa_required: true, mfa_type: "totp" });
const REFUSE = corps({ detail: "invalid two-factor code", mfa_required: true, mfa_type: "totp" });
const VERROU = corps({
  detail: "too many two-factor attempts",
  mfa_required: true,
  mfa_type: "totp",
  locked_until: "2026-09-26T22:30:00+00:00",
});

describe("lireLEchecDeConnexion", () => {
  it("réclame le code quand le serveur le demande", () => {
    expect(lireLEchecDeConnexion({ status: 401, message: REQUIS }, false)).toEqual({
      quoi: "demander-le-code",
    });
  });

  // Les deux 401 portent la MÊME forme. Seul « ai-je envoyé un code ? » les sépare, et c'est
  // une information du client, pas une phrase anglaise du serveur.
  it("distingue « il me faut un code » de « ce code est faux » sans lire la prose du serveur", () => {
    expect(lireLEchecDeConnexion({ status: 401, message: REFUSE }, true)).toEqual({
      quoi: "code-refuse",
    });
    // Même corps, l'autre situation : le serveur redemande après un code juste mais périmé.
    expect(lireLEchecDeConnexion({ status: 401, message: REQUIS }, true)).toEqual({
      quoi: "code-refuse",
    });
  });

  it("le verrouillage n'est pas un code refusé, et porte son échéance", () => {
    const r = lireLEchecDeConnexion({ status: 429, message: VERROU }, true);
    expect(r.quoi).toBe("verrouille");
    expect(r.quoi === "verrouille" && r.jusqua?.toISOString()).toBe("2026-09-26T22:30:00.000Z");
  });

  it("un verrouillage sans échéance lisible reste un verrouillage", () => {
    for (const mauvaise of [corps({ mfa_required: true }), corps({ mfa_required: true, locked_until: "hier" })]) {
      const r = lireLEchecDeConnexion({ status: 429, message: mauvaise }, true);
      expect(r).toEqual({ quoi: "verrouille", jusqua: null });
    }
  });

  it("un 401 sans mfa_required reste un refus d'identifiants", () => {
    expect(lireLEchecDeConnexion({ status: 401, message: '{"detail":"invalid email or password"}' }, false)).toEqual({
      quoi: "identifiants-refuses",
    });
  });

  it("l'adresse non vérifiée garde son propre message", () => {
    expect(lireLEchecDeConnexion({ status: 403, message: '{"detail":"email not verified"}' }, false)).toEqual({
      quoi: "email-non-verifie",
    });
  });

  it("un corps illisible ne fait pas tomber la lecture", () => {
    for (const brut of ["<html>502</html>", "", "null"]) {
      expect(lireLEchecDeConnexion({ status: 502, message: brut }, false)).toEqual({ quoi: "autre" });
    }
    expect(lireLEchecDeConnexion(null, false)).toEqual({ quoi: "autre" });
    expect(lireLEchecDeConnexion(undefined, true)).toEqual({ quoi: "autre" });
  });
});
