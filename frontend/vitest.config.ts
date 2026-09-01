import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      // `server-only` is a build-time guard with no runtime; neutralise it in tests.
      "server-only": fileURLToPath(new URL("./__tests__/empty-module.ts", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // e2e/ is Playwright's (`pnpm e2e`), not vitest's.
    exclude: ["node_modules", "e2e"],
  },
});
