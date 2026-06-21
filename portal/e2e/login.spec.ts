import { test, expect } from "@playwright/test";
import { mockAuth, mockProjects } from "./fixtures";

test.describe("Login page", () => {
  test("renders the login form", async ({ page }) => {
    await page.goto("/login");

    await expect(page.locator("h1")).toHaveText("Mockingbird");
    await expect(page.getByText("Service Virtualisation Platform")).toBeVisible();
    await expect(page.locator("#username")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("shows validation when submitting empty form", async ({ page }) => {
    await page.goto("/login");
    // HTML5 required fields prevent submission — username field should be focused
    await page.click('button[type="submit"]');
    // We should still be on /login (browser validation blocks submission)
    await expect(page).toHaveURL(/\/login/);
  });

  test("shows error message on invalid credentials", async ({ page }) => {
    await mockAuth(page, { failLogin: true });

    await page.goto("/login");
    await page.fill("#username", "wronguser");
    await page.fill("#password", "wrongpass");
    await page.click('button[type="submit"]');

    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Invalid username or password");
    // Still on login page
    await expect(page).toHaveURL(/\/login/);
  });

  test("redirects to dashboard on valid credentials", async ({ page }) => {
    await mockAuth(page);
    await mockProjects(page);

    await page.goto("/login");
    await page.fill("#username", "admin");
    await page.fill("#password", "password123");
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL("/");
    // Dashboard should show the nav header
    await expect(page.getByText("Mockingbird").first()).toBeVisible();
  });

  test("sign in button shows loading state while request is in flight", async ({ page }) => {
    // Delay the auth response so we can observe the loading state
    await page.route("**/api/v1/auth/login", async (route) => {
      await new Promise((r) => setTimeout(r, 400));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "tok",
          token_type: "Bearer",
          expires_in: 3600,
          username: "admin",
          role: "ADMIN",
        }),
      });
    });
    await mockProjects(page);

    await page.goto("/login");
    await page.fill("#username", "admin");
    await page.fill("#password", "pass");

    const btn = page.getByRole("button", { name: /sign in/i });
    await btn.click();
    // Button should be disabled while loading
    await expect(btn).toBeDisabled();
    // Wait for redirect
    await page.waitForURL("/");
  });

  test("unauthenticated visit to / redirects to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });
});
