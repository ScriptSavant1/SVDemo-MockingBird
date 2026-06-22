/**
 * Playwright config for REAL E2E tests — hits actual running services.
 *
 * Prerequisites (all must be running):
 *   auth-service      :3001   (JWT_SECRET set)
 *   project-service   :8001
 *   ingestion-service :8003
 *   portal (Vite)     :3000   (npm run dev)
 *
 * Run:  cd portal && npx playwright test --config=playwright.real.config.ts
 *       OR from repo root: scripts/run-real-tests.ps1
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e/real",
  fullyParallel: false,   // serial — tests share auth state via created users
  retries: 1,
  workers: 1,
  reporter: [["html", { open: "never", outputFolder: "playwright-report-real" }], ["list"]],
  use: {
    baseURL: "http://localhost:3000",
    viewport: { width: 1280, height: 800 },
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on-first-retry",
    // No route mocking — all API calls go to real services
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Expect services to be already running (start-services.ps1 handles startup)
  // We do NOT define webServer here because start-services.ps1 manages them
});
