import type { NextConfig } from "next";

// The browser only ever talks to this origin: the backend stays internal, no CORS, no exposed API
// port. The forwarding itself lives in src/app/api/[...path]/route.ts and NOT in a rewrite here —
// `rewrites()` is evaluated at build time and its destination is frozen into the image, so an image
// built by CI (where API_INTERNAL_URL is unset) carried `http://localhost:8000` for good. See the
// header of that file for what it cost.

// Origins allowed to load dev-server resources (HMR, RSC) when not on localhost — otherwise the
// page renders but never hydrates, and forms fall back to a native submit. Comma-separated.
const devOrigins = (process.env.DEV_ORIGINS ?? "10.25.0.19,dev-kevin")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

// The Content-Security-Policy (with a per-request nonce and frame-ancestors) is set in
// src/middleware.ts. These are the static, request-independent security headers.
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), browsing-topics=()",
  },
];

const nextConfig: NextConfig = {
  // Sortie autonome : Next produit un serveur qui n'embarque que les modules
  // réellement atteints, lancé par `node server.js`. Ajouté le 2026-08-12 pour
  // que l'image de production cesse de transporter l'arbre de développement et
  // le npm global — Trivy y trouvait tar 7.5.11 (critique), sigstore, picomatch
  // et ip-address, aucun d'eux nécessaire pour servir des pages.
  output: "standalone",
  allowedDevOrigins: devOrigins,
  async rewrites() {
    return [
      // The ghostboard portal discovers this app at <base_url>/.well-known/ghostapp.yaml, and
      // base_url is this origin — but the manifest is served by the backend, which is the single
      // place it is defined. Without this rewrite the portal gets a 404 from Next and the app is
      // simply invisible to the suite.
      //
      // The destination is a PATH ON THIS ORIGIN, not the backend URL: it lands on the route
      // handler, which resolves the backend at request time. A dot-prefixed segment cannot be a
      // route folder, hence the detour rather than a second handler.
      { source: "/.well-known/ghostapp.yaml", destination: "/api/.well-known/ghostapp.yaml" },
    ];
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
