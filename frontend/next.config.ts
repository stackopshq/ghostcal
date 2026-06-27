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

const nextConfig: NextConfig = {
  allowedDevOrigins: devOrigins,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/:path*` }];
  },
};

export default nextConfig;
