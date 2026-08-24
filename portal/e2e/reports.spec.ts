import { test, expect } from "@playwright/test";
import { loginAs, MOCK_PROJECTS } from "./fixtures";

test.describe("Reports hub", () => {
  test("nav link is visible and navigates to the Reports hub", async ({ page }) => {
    await loginAs(page);

    const link = page.getByTestId("reports-nav-link");
    await expect(link).toBeVisible();
    await link.click();

    await expect(page).toHaveURL("/reports");
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
  });

  test("lists deployed (LIVE/SUSPENDED) projects, each linking to its project page", async ({ page }) => {
    await loginAs(page);
    await page.goto("/reports");

    // MOCK_PROJECTS includes a LIVE project ("Payments API Stub") — DRAFT/other
    // statuses should not appear here since reports only exist once deployed.
    const liveProject = MOCK_PROJECTS.find((p) => p.status === "LIVE")!;
    await expect(page.getByText(liveProject.name)).toBeVisible();

    await page.getByText(liveProject.name).click();
    await expect(page).toHaveURL(`/projects/${liveProject.id}`);
  });
});
