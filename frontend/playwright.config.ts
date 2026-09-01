import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end suite: drives a real browser against the running stack (frontend +
 * backend + Postgres, brought up separately via `make e2e` or docker compose).
 * Tests share database state, so they run serially and reset the DB per test.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
