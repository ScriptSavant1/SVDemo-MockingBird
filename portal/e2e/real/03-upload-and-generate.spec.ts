/**
 * Real E2E — Upload a CA LISA spec file and generate a stub.
 *
 * Uses a real CA LISA sample file from Sample_SV_Files/ESP/.
 * Requires ingestion-service and project-service to be running.
 */
import { test, expect } from "@playwright/test";
import { ADMIN, SAMPLE_ESP_REQUEST, loginAs, waitForJobDone } from "./helpers";
import path from "path";

const PROJECT_NAME = `Upload Test ${Date.now()}`;

test.describe("Upload & Generate (real)", () => {
  let projectId: string;

  test.beforeAll(async ({ browser }) => {
    // Create a fresh project for upload tests
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, ADMIN);

    await page.getByTestId("new-project-button").click();
    await page.fill('[data-testid="name-input"]', PROJECT_NAME);
    await page.fill('[data-testid="team-input"]', "E2E Upload Team");
    await page.selectOption('[data-testid="environment-select"]', "TEST");
    await page.fill('[data-testid="tps-input"]', "500");
    await page.click('[data-testid="create-submit-button"]');
    await page.waitForURL(/\/projects\/([0-9a-f-]{36})/, { timeout: 8_000 });

    const match = page.url().match(/\/projects\/([0-9a-f-]{36})/);
    projectId = match?.[1] ?? "";
    await ctx.close();
  });

  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
  });

  test("upload page renders for the project", async ({ page }) => {
    await page.goto(`/projects/${projectId}/upload`);
    await expect(page.getByRole("heading", { name: /upload/i })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("button", { name: /upload & generate/i })).toBeDisabled();
  });

  test("can upload a CA LISA ESP file", async ({ page }) => {
    await page.goto(`/projects/${projectId}/upload`);

    await page.fill('[id="stub-name"]', "ESP Account Enquiry v1");

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_ESP_REQUEST);

    const submitBtn = page.getByRole("button", { name: /upload & generate/i });
    await expect(submitBtn).toBeEnabled({ timeout: 3_000 });
  });

  test("upload + generate redirects to job status page", async ({ page }) => {
    await page.goto(`/projects/${projectId}/upload`);

    await page.fill('[id="stub-name"]', `ESP Stub ${Date.now()}`);

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_ESP_REQUEST);

    await page.getByRole("button", { name: /upload & generate/i }).click();

    // Should redirect to job status
    await page.waitForURL(/\/jobs\/[0-9a-f-]{36}/, { timeout: 10_000 });
    await expect(page).toHaveURL(/\/jobs\//);
  });

  test("job completes successfully (DONE status)", async ({ page }) => {
    await page.goto(`/projects/${projectId}/upload`);
    await page.fill('[id="stub-name"]', `ESP Stub Done ${Date.now()}`);

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_ESP_REQUEST);
    await page.getByRole("button", { name: /upload & generate/i }).click();
    await page.waitForURL(/\/jobs\/[0-9a-f-]{36}/, { timeout: 10_000 });

    // Job should complete quickly (local dev — inline generation)
    await waitForJobDone(page, 15_000);

    const bodyText = await page.locator("body").textContent();
    expect(bodyText).toMatch(/DONE/);
    expect(bodyText).not.toMatch(/FAILED/);
  });

  test("stub appears in project after successful generate", async ({ page }) => {
    // Generate a stub then navigate back to project
    await page.goto(`/projects/${projectId}/upload`);
    await page.fill('[id="stub-name"]', `ESP Check Project ${Date.now()}`);

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_ESP_REQUEST);
    await page.getByRole("button", { name: /upload & generate/i }).click();
    await page.waitForURL(/\/jobs\/[0-9a-f-]{36}/, { timeout: 10_000 });
    await waitForJobDone(page, 15_000);

    // Go back to project
    await page.goto(`/projects/${projectId}`);
    // The stubs list should have at least one stub
    const stubRow = page.locator('[data-testid="stub-row"]')
      .or(page.locator('table tbody tr'))
      .or(page.getByText(/ESP/));
    await expect(stubRow.first()).toBeVisible({ timeout: 5_000 });
  });
});
