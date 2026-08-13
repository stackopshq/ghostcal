// Le rappel OIDC arrive ici, et nulle part ailleurs.
//
// L'API construit son `redirect_uri` à partir de sa propre base publique, et
// annonce donc `https://<origine>/v1/auth/oidc/callback`. Or, publiquement,
// l'API n'est joignable que sous `/api` : le navigateur revenait de Cloudflare
// Access sur un chemin que Next ne connaissait pas, et prenait un **404** au
// dernier pas de la connexion.
//
// Le défaut est antérieur au relais à l'exécution : `/v1/*` n'a jamais été
// servi par cette origine. Il était simplement **inatteignable**, parce que le
// bouton SSO ne s'affichait pas — personne n'avait jamais pu cliquer dessus.
// Un défaut que rien ne peut atteindre ne se signale pas ; il attend.
//
// Deux façons de refermer ça, et le choix est celui du 2026-08-13 : servir le
// chemin de rappel ici, plutôt que de corriger la base publique de l'API et
// d'ajouter un `redirect_uri` chez Cloudflare Access. Aucun objet d'identité
// n'est touché, ce qui vaut mieux qu'une reconstruction pour un tel gain.
//
// La portée est délibérément `/v1/auth/*` et non `/v1/*` : seule
// l'authentification a besoin d'être atteinte sous ce préfixe, et l'API reste
// autrement joignable par le seul `/api`.

import { NextRequest } from "next/server";
import { proxyToApi } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Ctx = { params: Promise<{ path: string[] }> };

const prefix = (p: string[]) => ["v1", "auth", ...p];

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxyToApi(req, prefix((await ctx.params).path));
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxyToApi(req, prefix((await ctx.params).path));
}
