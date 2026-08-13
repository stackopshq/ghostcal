// Relais vers l'API, résolu À CHAQUE REQUÊTE.
//
// Il remplace la réécriture `rewrites()` de next.config.ts, et la raison n'est
// pas stylistique : **les réécritures de Next sont figées à la construction**,
// pas lues à l'exécution. Leur destination part dans `.next/routes-manifest.json`
// au moment du build. L'image étant bâtie par la CI, où `API_INTERNAL_URL`
// n'existe pas, `next.config.ts` tombait sur son repli `http://localhost:8000`
// et cette valeur se retrouvait gravée dans l'image.
//
// Mesuré le 2026-08-13 : le conteneur avait pourtant `API_INTERNAL_URL=
// http://ghostcal-app:8000` dans son environnement et joignait parfaitement
// l'API — mais le relais tentait `127.0.0.1:8000`, où rien n'écoute. Le
// manifeste de l'image contenait bien `http://localhost:8000` en dur.
//
// Ce que ça cassait, et pourquoi ça s'est vu tard : `getAuthConfig()` avale
// l'erreur et rend `{ oidc_enabled: false }`. Une panne d'infrastructure
// devenait donc indiscernable d'une configuration volontaire — la page de
// connexion n'affichait simplement pas le bouton SSO, sans rien signaler.
//
// Ici, `process.env` est lu dans le corps du gestionnaire, donc à chaque
// requête. L'image redevient indépendante de son déploiement : le même artefact
// tourne derrière n'importe quel nom d'API sans être reconstruit.

import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function apiBase(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

// En-têtes propres au saut réseau : les retransmettre casse le relais, parce
// qu'ils décrivent la connexion précédente et non le message.
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

function forwardHeaders(src: Headers): Headers {
  const out = new Headers();
  src.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) out.set(key, value);
  });
  return out;
}

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const target = `${apiBase()}/${path.join("/")}${req.nextUrl.search}`;

  // `duplex: "half"` est requis dès qu'un corps est transmis en flux — sans lui
  // Node refuse la requête. Les méthodes sans corps ne doivent PAS en porter un,
  // d'où la distinction plutôt qu'un `body` systématique.
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers: forwardHeaders(req.headers),
    redirect: "manual",
    ...(hasBody ? { body: req.body, duplex: "half" as const } : {}),
  };

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (err) {
    // On dit ce qui a échoué et vers où. Un 502 muet renverrait le lecteur vers
    // l'application alors que le défaut est dans le chemin qui y mène —
    // exactement ce qui a coûté du temps le 2026-08-13.
    const detail = err instanceof Error ? err.message : String(err);
    return Response.json(
      { error: "upstream_unreachable", target: apiBase(), detail },
      { status: 502 },
    );
  }

  const headers = forwardHeaders(upstream.headers);
  return new Response(upstream.body, { status: upstream.status, headers });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function HEAD(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function OPTIONS(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
