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

// Content-Security-Policy. `wasm-unsafe-eval` lets the vendored crypto core load hash-wasm's
// Argon2id WebAssembly (AES-GCM and X25519 are native WebCrypto and need nothing extra). Framing
// is intentionally left open so the booking widget can be embedded on third-party sites.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  allowedDevOrigins: devOrigins,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
