import type { NextConfig } from "next";

// Proxy API calls through the frontend so the browser only ever talks to this origin
// (same-origin). The backend stays internal; no CORS, no exposed API port. The destination is
// resolved on the Next server, where the backend is reachable locally.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/:path*` }];
  },
};

export default nextConfig;
