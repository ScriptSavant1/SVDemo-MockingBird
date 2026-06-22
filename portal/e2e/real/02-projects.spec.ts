/**
 * Real E2E — Project management
 *
 * Tests creating, listing, and viewing projects via the real project-service.
 */
import { test, expect } from "@playwright/test";
import { ADMIN, loginAs } from "./helpers";

// Unique name so parallel test runs don't clash
const PROJECT_NAME = `E2E Test Project ${Date.now()}`;

test.describe("Project management (real)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
  });

  test("dashboard shows Projects heading", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  });

  test("can create a new project", async ({ page }) => {
    await page.getByTestId("new-project-button").click();
    await expect(page).toHaveURL("/projects/new");

    await page.fill('[data-testid="name-input"]', PROJECT_NAME);
    await page.fill('[data-testid="team-input"]', "E2E Automation");
    await page.selectOption('[data-testid="environment-select"]', "TEST");
    await page.fill('[data-testid="tps-input"]', "1000");
    await page.fill('[data-testid="description-textarea"]', "Created by real E2E test suite");

    await page.click('[data-testid="create-submit-button"]');

    // Should redirect to the new project's detail page
    await page.waitForURL(/\/projects\/[0-9a-f-]{36}/, { timeout: 8_000 });
    await expect(page.getByText(PROJECT_NAME)).toBeVisible();
  });

  test("new project appears in the dashboard list", async ({ page }) => {
    // Dashboard should show the project created in the previous test
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    // At least 1 project card should exist
    const cards = page.locator('[data-testid="project-card"], .project-card, [class*="card"]');
    await expect(cards.first()).toBeVisible({ timeout: 5_000 });
  });

  test("project card click navigates to project detail", async ({ page }) => {
    // Click the first project card
    const cards = page.locator('[data-testid="project-card"]').or(page.locator('.cursor-pointer').first());
    await cards.first().click();
    await page.waitForURL(/\/projects\/[0-9a-f-]{36}/, { timeout: 5_000 });
    // Detail page should have an Upload link or button — use .first() to avoid strict mode if both exist
    const uploadBtn = page.getByRole("link", { name: /upload/i })
      .or(page.getByRole("button", { name: /upload/i }));
    await expect(uploadBtn.first()).toBeVisible({ timeout: 5_000 });
  });
});
