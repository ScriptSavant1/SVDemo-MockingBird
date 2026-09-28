/**
 * Real E2E — upload errors reach the user as one coded line
 * (docs/ERROR_CODES.md), through the real ingestion-service. No mocking.
 */
import { test, expect } from "@playwright/test";
import fs from "fs";
import os from "os";
import path from "path";
import { ADMIN, loginAs } from "./helpers";

test.describe("Upload error messages (real)", () => {
  let projectId: string;
  let tmpDir: string;

  test.beforeAll(async ({ browser }) => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "mb-e2e-errors-"));
    const page = await browser.newPage();
    await loginAs(page, ADMIN);
    await page.getByTestId("new-project-button").click();
    await page.fill('[data-testid="name-input"]', `Error messages ${Date.now()}`);
    await page.fill('[data-testid="team-input"]', "E2E");
    await page.selectOption('[data-testid="environment-select"]', "TEST");
    await page.fill('[data-testid="tps-input"]', "100");
    await page.click('[data-testid="create-submit-button"]');
    await page.waitForURL(/\/projects\/([0-9a-f-]{36})/, { timeout: 10_000 });
    projectId = page.url().match(/\/projects\/([0-9a-f-]{36})/)?.[1] ?? "";
    await page.close();
  });

  test.afterAll(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
  });

  async function uploadSingle(page: import("@playwright/test").Page, name: string, content: string) {
    const file = path.join(tmpDir, name);
    fs.writeFileSync(file, content);
    await page.goto(`/projects/${projectId}/upload`);
    await page.getByTestId("file-input").setInputFiles(file);
    await page.getByRole("button", { name: /upload & generate/i }).click();
  }

  test("empty file → MB-UPL-001 naming the file", async ({ page }) => {
    await uploadSingle(page, "empty-spec.txt", "");
    await expect(page.getByTestId("upload-error-line")).toHaveText("MB-UPL-001 · 'empty-spec.txt' is empty");
  });

  test("unrecognised content → MB-UPL-003", async ({ page }) => {
    await uploadSingle(page, "notes.txt", "just some notes, not a spec");
    await expect(page.getByTestId("upload-error-line")).toContainText("MB-UPL-003 · File format not recognised.");
  });
});
