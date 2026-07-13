import type { NextConfig } from "next";

// Proxy API calls through the frontend so the browser only ever talks to this origin
// (same-origin). The backend stays internal; no CORS, no exposed API port. The destination is
// resolved on the Next server, where the backend is reachable locally.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

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
  allowedDevOrigins: devOrigins,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_INTERNAL_URL}/:path*` },
      // The ghostboard portal discovers this app at <base_url>/.well-known/ghostapp.yaml, and
      // base_url is this origin — but the manifest is served by the backend, which is the single
      // place it is defined. Without this rewrite the portal gets a 404 from Next and the app is
      // simply invisible to the suite.
      {
        source: "/.well-known/ghostapp.yaml",
        destination: `${API_INTERNAL_URL}/.well-known/ghostapp.yaml`,
      },
    ];
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
