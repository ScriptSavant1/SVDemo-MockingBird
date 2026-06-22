/**
 * Real E2E — Authentication
 *
 * Tests login, logout, invalid credentials, and role display
 * against the live auth-service on :3001.
 */
import { test, expect } from "@playwright/test";
import { ADMIN, SV_USER, loginAs, logout } from "./helpers";

test.describe("Authentication (real)", () => {
  test("login page renders", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("h1, h2").first()).toBeVisible();
    await expect(page.locator("#username")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("invalid credentials show error", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#username", "nobody");
    await page.fill("#password", "wrongpassword");
    await page.click('button[type="submit"]');
    await expect(page.getByRole("alert").or(page.locator("[data-testid='login-error']"))).toBeVisible({ timeout: 5_000 });
  });

  test("admin can log in and sees ADMIN badge", async ({ page }) => {
    await loginAs(page, ADMIN);
    await expect(page).toHaveURL("/");
    await expect(page.getByTestId("user-info")).toContainText(ADMIN.username);
    await expect(page.getByTestId("user-info")).toContainText("ADMIN");
  });

  test("admin sees Admin nav link", async ({ page }) => {
    await loginAs(page, ADMIN);
    await expect(page.getByTestId("admin-nav-link")).toBeVisible();
  });

  test("sv.user can log in and sees SV_TEAM badge", async ({ page }) => {
    await loginAs(page, SV_USER);
    await expect(page).toHaveURL("/");
    await expect(page.getByTestId("user-info")).toContainText(SV_USER.username);
    await expect(page.getByTestId("user-info")).toContainText("SV_TEAM");
  });

  test("sv.user does NOT see Admin nav link", async ({ page }) => {
    await loginAs(page, SV_USER);
    await expect(page.getByTestId("admin-nav-link")).not.toBeVisible();
  });

  test("admin can sign out and gets redirected to /login", async ({ page }) => {
    await loginAs(page, ADMIN);
    await logout(page);
    await expect(page).toHaveURL(/\/login/);
  });

  test("unauthenticated navigation to / redirects to /login", async ({ page }) => {
    // Clear any session
    await page.goto("/login");
    await page.evaluate(() => sessionStorage.clear());
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });
});
