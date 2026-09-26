import { describe, expect, it } from "vitest";
import {
  CODES_RESTANTS_INQUIETANTS,
  etapeDuSecondFacteur,
  resteDeCodesInquietant,
} from "./secondFacteurEtat";

const etat = (sur: Partial<{ enabled: boolean; pending: boolean; recovery_codes_remaining: number }> = {}) => ({
  enabled: false,
  pending: false,
  recovery_codes_remaining: 10,
  ...sur,
});

describe("etapeDuSecondFacteur", () => {
  it("attend d'avoir lu l'état avant de proposer quoi que ce soit", () => {
    expect(etapeDuSecondFacteur(null, false, false)).toBe("chargement");
  });

  // Le défaut mesuré sur GhostPass : un bouton « Activer la 2FA » proposé à quelqu'un qui
  // l'avait déjà activée. Le toucher aurait remis son secret à zéro.
  it("ne propose pas d'activer ce qui est déjà actif", () => {
    expect(etapeDuSecondFacteur(etat({ enabled: true }), false, false)).toBe("actif");
  });

  // `pending` : une ligne en base, aucune porte gardée tant qu'un premier code juste n'est
  // pas arrivé. L'annoncer « actif » promettrait une protection qui n'existe pas.
  it("un enrôlement commencé et jamais activé ne protège rien", () => {
    expect(etapeDuSecondFacteur(etat({ pending: true }), false, false)).toBe("inactif");
  });

  // Seul instant où les codes sont lisibles : ils passent devant TOUT, y compris devant un
  // état qui vient de basculer à « actif ».
  it("les codes à noter passent devant tout le reste", () => {
    expect(etapeDuSecondFacteur(etat({ enabled: true }), false, true)).toBe("codes-a-noter");
    expect(etapeDuSecondFacteur(null, true, true)).toBe("codes-a-noter");
  });

  it("l'enrôlement en cours l'emporte sur « inactif »", () => {
    expect(etapeDuSecondFacteur(etat(), true, false)).toBe("enrolement");
  });
});

describe("resteDeCodesInquietant", () => {
  it("alerte avant que la réserve soit vide, pas quand elle l'est", () => {
    expect(resteDeCodesInquietant(0)).toBe(true);
    expect(resteDeCodesInquietant(CODES_RESTANTS_INQUIETANTS)).toBe(true);
    expect(resteDeCodesInquietant(CODES_RESTANTS_INQUIETANTS + 1)).toBe(false);
    expect(resteDeCodesInquietant(10)).toBe(false);
  });
});
