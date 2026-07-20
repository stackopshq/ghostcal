import { defineConfig } from "vitest/config";

// Unit tests for pure frontend logic (parsers, guards, mappers). Component/e2e coverage lives
// elsewhere; this suite stays fast and deterministic so it runs on every push.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    globals: false,
    // The zero-knowledge tests derive real Argon2id keys — deliberately expensive work that
    // takes seconds, not milliseconds. The 5s default put them close enough to the edge that
    // they failed intermittently on a loaded machine; a slow test is fine, a flaky one is not.
    testTimeout: 30_000,
  },
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
});
