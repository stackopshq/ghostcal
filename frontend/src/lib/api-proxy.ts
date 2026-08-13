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
// l'API — mais le relais tentait `127.0.0.1:8000`, où rien n'écoute.
//
// Ici, `process.env` est lu dans le corps du gestionnaire, donc à chaque
// requête. L'image redevient indépendante de son déploiement : le même artefact
// tourne derrière n'importe quel nom d'API sans être reconstruit.

import { NextRequest } from "next/server";

export function apiBase(): string {
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

function forwardRequestHeaders(src: Headers): Headers {
  const out = new Headers();
  src.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) out.set(key, value);
  });
  return out;
}

// `Set-Cookie` est le seul en-tête que l'on ne peut pas recopier par
// `forEach` : celui-ci fusionne les valeurs répétées en une seule chaîne
// séparée par des virgules, et un cookie dont l'`Expires` contient déjà une
// virgule en ressort coupé en deux cookies invalides. Le navigateur les jette
// tous les deux, sans rien dire.
//
// Invisible tant que le relais ne servait que des lectures JSON. Le rappel
// OIDC, lui, pose la session — c'est la première réponse du relais dont les
// cookies décident de quelque chose.
function forwardResponseHeaders(src: Headers): Headers {
  const out = new Headers();
  src.forEach((value, key) => {
    const k = key.toLowerCase();
    if (k !== "set-cookie" && !HOP_BY_HOP.has(k)) out.set(key, value);
  });
  for (const cookie of src.getSetCookie?.() ?? []) out.append("set-cookie", cookie);
  return out;
}

/** Relaie la requête telle quelle vers `<API>/<path>`, en préservant la query. */
export async function proxyToApi(req: NextRequest, path: string[]): Promise<Response> {
  const target = `${apiBase()}/${path.join("/")}${req.nextUrl.search}`;

  // `duplex: "half"` est requis dès qu'un corps est transmis en flux — sans lui
  // Node refuse la requête. Les méthodes sans corps ne doivent PAS en porter un,
  // d'où la distinction plutôt qu'un `body` systématique.
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers: forwardRequestHeaders(req.headers),
    // `manual` : le rappel OIDC répond par une 302 qu'il faut transmettre au
    // navigateur, pas suivre depuis le serveur — c'est lui qui doit recevoir
    // la redirection, et les cookies qui l'accompagnent.
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

  return new Response(upstream.body, {
    status: upstream.status,
    headers: forwardResponseHeaders(upstream.headers),
  });
}
