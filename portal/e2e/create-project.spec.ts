import { test, expect } from "@playwright/test";
import { loginAs, MOCK_NEW_PROJECT } from "./fixtures";

test.describe("Create Project", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("navigates to create project page from dashboard", async ({ page }) => {
    await page.getByTestId("new-project-button").click();
    await expect(page).toHaveURL("/projects/new");
    await expect(page.getByRole("heading", { name: "New Project" })).toBeVisible();
  });

  test("shows validation errors when submitting empty form", async ({ page }) => {
    await page.goto("/projects/new");

    await page.getByTestId("create-submit-button").click();

    await expect(page.getByText("Name is required")).toBeVisible();
    await expect(page.getByText("Team is required")).toBeVisible();
  });

  test("creates project and navigates to project page on success", async ({ page }) => {
    // Mock the POST /projects response
    await page.route("**/api/v1/projects", async (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(MOCK_NEW_PROJECT),
        });
      }
      return route.continue();
    });

    // Mock the project detail page that we'll be redirected to
    await page.route("**/api/v1/projects/proj-new", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_NEW_PROJECT),
      })
    );
    await page.route("**/api/v1/projects/proj-new/stubs", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await page.goto("/projects/new");

    await page.getByTestId("name-input").fill("New Test Project");
    await page.getByTestId("team-input").fill("QA Team");
    await page.getByTestId("environment-select").selectOption("TEST");
    await page.getByTestId("tps-input").fill("1000");
    await page.getByTestId("description-textarea").fill("Created during E2E test");

    await page.getByTestId("create-submit-button").click();

    await expect(page).toHaveURL("/projects/proj-new");
  });

  test("shows API error when creation fails", async ({ page }) => {
    await page.route("**/api/v1/projects", async (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Conflict",
            status: 409,
            detail: "A project with this name already exists.",
          }),
        });
      }
      return route.continue();
    });

    await page.goto("/projects/new");
    await page.getByTestId("name-input").fill("Duplicate Project");
    await page.getByTestId("team-input").fill("SV Team");
    await page.getByTestId("create-submit-button").click();

    await expect(page.getByTestId("create-error")).toBeVisible();
    await expect(page.getByTestId("create-error")).toContainText(
      "A project with this name already exists."
    );
  });

  test("cancel returns to dashboard", async ({ page }) => {
    await page.goto("/projects/new");
    await page.getByRole("button", { name: /cancel/i }).click();
    await expect(page).toHaveURL("/");
  });

  test("validates TPS range", async ({ page }) => {
    await page.goto("/projects/new");

    await page.getByTestId("name-input").fill("Test");
    await page.getByTestId("team-input").fill("Team");
    await page.getByTestId("tps-input").fill("0");  // below minimum
    await page.getByTestId("create-submit-button").click();

    await expect(page.getByText("Must be 1 – 100,000")).toBeVisible();
  });
});
