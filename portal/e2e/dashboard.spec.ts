import { test, expect } from "@playwright/test";
import { loginAs, mockProjects, MOCK_PROJECTS } from "./fixtures";

test.describe("Dashboard", () => {
  test("shows projects list after login", async ({ page }) => {
    await loginAs(page);

    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(page.getByText("Payments API Stub")).toBeVisible();
    await expect(page.getByText("Account Enquiry Stub")).toBeVisible();
  });

  test("shows empty state when no projects", async ({ page }) => {
    await loginAs(page, { projects: [] });

    await expect(page.getByText("No projects yet.")).toBeVisible();
    await expect(page.getByText("Create your first project.")).toBeVisible();
  });

  test("shows New Project button for ADMIN role", async ({ page }) => {
    await loginAs(page);

    const btn = page.getByTestId("new-project-button");
    await expect(btn).toBeVisible();
  });

  test("shows status badge on project cards", async ({ page }) => {
    await loginAs(page);

    // "LIVE" and "DRAFT" status badges should appear
    await expect(page.getByText("LIVE")).toBeVisible();
    await expect(page.getByText("DRAFT")).toBeVisible();
  });

  test("clicking a project card navigates to the project page", async ({ page }) => {
    await mockProjects(page, [MOCK_PROJECTS[0]]);
    await page.route("**/api/v1/projects/proj-001", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_PROJECTS[0]),
      })
    );
    await page.route("**/api/v1/projects/proj-001/stubs", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await loginAs(page, { projects: [MOCK_PROJECTS[0]] });
    await page.getByText("Payments API Stub").click();
    await expect(page).toHaveURL("/projects/proj-001");
  });

  test("nav header shows username and role", async ({ page }) => {
    await loginAs(page);

    const userInfo = page.getByTestId("user-info");
    await expect(userInfo).toContainText("admin");
    await expect(userInfo).toContainText("ADMIN");
  });

  test("admin nav link visible for admin users", async ({ page }) => {
    await loginAs(page);

    await expect(page.getByTestId("admin-nav-link")).toBeVisible();
  });

  test("sign out clears session and redirects to login", async ({ page }) => {
    await loginAs(page);

    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
