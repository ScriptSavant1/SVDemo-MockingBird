import { test, expect } from "@playwright/test";
import { loginAs, mockProjects, MOCK_PROJECTS } from "./fixtures";

test.describe("Dashboard — delete project (ADMIN only)", () => {
  test("admin sees a delete button and can delete a project after confirming", async ({ page }) => {
    let deleteCalled = false;
    await page.route(`**/api/v1/projects/${MOCK_PROJECTS[0].id}`, (route) => {
      if (route.request().method() === "DELETE") {
        deleteCalled = true;
        return route.fulfill({ status: 204, body: "" });
      }
      return route.continue();
    });

    await loginAs(page); // sv.admin per fixtures default

    const firstCard = page.getByTestId("project-card-wrapper").first();
    await firstCard.getByTestId("delete-project-button").click({ force: true });

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Delete project" })).toBeVisible();
    await expect(dialog.getByText(MOCK_PROJECTS[0].name)).toBeVisible();

    // Re-mock the list so the post-delete refetch shows the project gone.
    await mockProjects(page, MOCK_PROJECTS.slice(1));
    await page.getByTestId("confirm-delete-project-button").click();

    await expect(page.getByRole("heading", { name: "Delete project" })).not.toBeVisible();
    expect(deleteCalled).toBe(true);
  });

  test("shows an inline error when delete fails, without closing the modal", async ({ page }) => {
    await page.route(`**/api/v1/projects/${MOCK_PROJECTS[0].id}`, (route) => {
      if (route.request().method() === "DELETE") {
        return route.fulfill({ status: 403, body: JSON.stringify({ detail: "Admin role required" }) });
      }
      return route.continue();
    });

    await loginAs(page);
    const firstCard = page.getByTestId("project-card-wrapper").first();
    await firstCard.getByTestId("delete-project-button").click({ force: true });
    await page.getByTestId("confirm-delete-project-button").click();

    await expect(page.getByRole("alert")).toContainText("Admin role required");
    await expect(page.getByRole("heading", { name: "Delete project" })).toBeVisible();
  });

  test("SV_TEAM users do not see a delete button", async ({ page }) => {
    await loginAs(page, { username: "j.smith", role: "SV_TEAM" });
    await expect(page.getByTestId("project-card").first()).toBeVisible();
    await expect(page.getByTestId("delete-project-button")).not.toBeVisible();
  });
});

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

    // Scoped to the badge itself — the dashboard's status-filter pills also
    // render "LIVE"/"DRAFT" as plain button text, so an unscoped getByText
    // matches both.
    await expect(page.getByTestId("status-badge").getByText("LIVE")).toBeVisible();
    await expect(page.getByTestId("status-badge").getByText("DRAFT")).toBeVisible();
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
