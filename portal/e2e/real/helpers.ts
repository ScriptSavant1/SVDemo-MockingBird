/**
 * Helpers for real E2E tests — no API mocking, real services required.
 *
 * Credentials (created by scripts/seed-users.ps1):
 *   ADMIN  : sv.admin  / Admin@2026!
 *   SV_TEAM: sv.user   / User@2026!
 */
import { Page, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

export const ADMIN = { username: "sv.admin", password: "Admin@2026!" };
export const SV_USER = { username: "sv.user", password: "User@2026!" };

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Combined CA LISA HTTP pair file (request + response concatenated, no BOM)
export const SAMPLE_ESP_COMBINED = path.resolve(
  __dirname,
  "../../../Sample_SV_Files/ESP/combined_request_response.txt",
);
// Legacy aliases kept for reference
export const SAMPLE_ESP_REQUEST = SAMPLE_ESP_COMBINED;
export const SAMPLE_ESP_RESPONSE = SAMPLE_ESP_COMBINED;

/** Log in via the real login page. Leaves page on dashboard "/" on success. */
export async function loginAs(
  page: Page,
  creds: { username: string; password: string },
) {
  await page.goto("/login");
  await page.fill("#username", creds.username);
  await page.fill("#password", creds.password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes("login"), {
    timeout: 8_000,
  });
}

/** Log out via the Sign out button. */
export async function logout(page: Page) {
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page).toHaveURL(/\/login/);
}

/** Wait for a job to reach DONE or FAILED status (polls the job page). */
export async function waitForJobDone(page: Page, timeoutMs = 15_000) {
  await page.waitForFunction(
    () => {
      const el =
        document.querySelector("[data-testid='job-status']") ??
        document.body;
      return /DONE|FAILED/.test(el.textContent ?? "");
    },
    { timeout: timeoutMs },
  );
}
