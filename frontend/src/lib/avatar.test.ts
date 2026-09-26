// L'avatar téléversé s'affiche — ce qu'aucun test ne regardait.
//
// POURQUOI CE FICHIER EXISTE
// --------------------------
// Le téléversement marchait : la route existait, elle était branchée, elle
// écrivait, et cinq tests serveur le prouvaient. C'est l'AFFICHAGE qui ne
// pouvait pas marcher, pour deux raisons indépendantes dont chacune suffisait :
//
//   1. l'écran posait l'adresse dans `<img src="…">`, et un `<img>` n'envoie
//      JAMAIS d'en-tête `Authorization` — le navigateur ne met que les cookies.
//      La route exige `current_member`. Résultat : 401, `onError`, retour aux
//      initiales, exactement comme si l'on n'avait rien téléversé ;
//   2. l'adresse était construite à la main sans le préfixe de l'API. Elle
//      demandait `/v1/me/profile/avatar/…` à l'application Next, qui rend 404.
//
// Mesuré en production le 2026-09-26 : `/v1/me/profile/avatar/<id>` → 404,
// `/api/v1/me/profile/avatar/<id>` → 401. Aucune trace côté serveur, puisque
// la requête n'y arrivait pas.
//
// C'est le motif que ce projet rencontre sans cesse : la chose existait, rien
// ne la lisait. Les tests serveur restaient verts en le prouvant.

import { afterEach, describe, expect, it, vi } from "vitest";

const authedRequest = vi.fn<(...args: unknown[]) => Promise<unknown>>(
  async () =>
    new Response(new Blob(["octets"]), {
      headers: { "Content-Type": "image/webp" },
    }),
);
vi.mock("@/lib/auth", () => ({
  authedFetch: vi.fn(),
  authedRequest: (...args: unknown[]) => authedRequest(...args),
}));

import { chargerAvatar } from "@/lib/profile";

// jsdom n'implémente pas les URL d'objet.
const creees: Blob[] = [];
globalThis.URL.createObjectURL = ((b: Blob) => {
  creees.push(b);
  return `blob:faux/${creees.length}`;
}) as typeof URL.createObjectURL;

afterEach(() => {
  authedRequest.mockClear();
  creees.length = 0;
});

describe("chargerAvatar", () => {
  // LE test de ce fichier. S'il repasse par `<img src>`, `authedRequest` n'est
  // plus appelé et celui-ci rougit.
  it("demande l'image par le chemin authentifié, pas par une adresse nue", async () => {
    await chargerAvatar("11111111-2222-3333-4444-555555555555");
    expect(authedRequest).toHaveBeenCalledTimes(1);
    expect(authedRequest).toHaveBeenCalledWith(
      "/v1/me/profile/avatar/11111111-2222-3333-4444-555555555555",
    );
  });

  // Le préfixe de l'API n'est PAS écrit ici : c'est `authedRequest` qui le pose,
  // comme pour tous les autres appels. Le réécrire à la main est précisément ce
  // qui avait produit le 404.
  it("n'écrit pas le préfixe de l'API lui-même", async () => {
    await chargerAvatar("abc");
    const chemin = authedRequest.mock.calls[0][0] as string;
    expect(chemin.startsWith("/v1/")).toBe(true);
    expect(chemin).not.toContain("/api/");
    expect(chemin).not.toMatch(/^https?:/);
  });

  it("rend une URL d'objet construite à partir des octets reçus", async () => {
    const url = await chargerAvatar("abc");
    expect(url).toMatch(/^blob:/);
    expect(creees).toHaveLength(1);
    // Le type vient de l'en-tête de la réponse : c'est lui que `<img>` suivra.
    // Le Blob de jsdom n'a pas `.text()` : on vérifie ce qui compte ici, le type
    // porté par l'en-tête de la réponse — c'est lui que le `<img>` suivra.
    expect(creees[0].type).toBe("image/webp");
  });

  // L'écran s'appuie sur l'échec pour retomber sur les initiales : une erreur
  // avalée ici afficherait une image vide sans jamais montrer les initiales.
  it("laisse remonter l'échec au lieu de rendre une URL vide", async () => {
    authedRequest.mockRejectedValueOnce(new Error("401"));
    await expect(chargerAvatar("abc")).rejects.toThrow();
  });
});
