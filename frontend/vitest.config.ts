import { defineConfig } from "vitest/config";

// Unit tests for pure frontend logic (parsers, guards, mappers). Component/e2e coverage lives
// elsewhere; this suite stays fast and deterministic so it runs on every push.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    globals: false,
  },
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
});
