/**
 * Real E2E — Download NFT JMeter ZIP.
 *
 * Uploads a CA LISA sample file through the real portal UI, generates the
 * stub, clicks the "Download NFT Scripts" button, and verifies the
 * downloaded ZIP is a real, well-formed JMeter test plan (test-plan.jmx +
 * a CSV data file + README.md) — this is the on-demand JMeter NFT script
 * generation feature (Phase 1, see docs/progress/PHASE1_JMETER_NFT_GENERATION.md).
 */
import { test, expect } from "@playwright/test";
import { ADMIN, SAMPLE_ESP_REQUEST, loginAs, waitForJobDone } from "./helpers";
import JSZip from "jszip";
import { promises as fs } from "fs";

const PROJECT_NAME = `NFT JMeter Test ${Date.now()}`;

test.describe("Download NFT JMeter ZIP (real)", () => {
  let projectId: string;

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, ADMIN);

    await page.getByTestId("new-project-button").click();
    await page.fill('[data-testid="name-input"]', PROJECT_NAME);
    await page.fill('[data-testid="team-input"]', "NFT Tests");
    await page.selectOption('[data-testid="environment-select"]', "TEST");
    await page.fill('[data-testid="tps-input"]', "500");
    await page.click('[data-testid="create-submit-button"]');
    await page.waitForURL(/\/projects\/([0-9a-f-]{36})/, { timeout: 8_000 });
    const match = page.url().match(/\/projects\/([0-9a-f-]{36})/);
    projectId = match?.[1] ?? "";

    await page.goto(`/projects/${projectId}/upload`);
    await page.fill('[id="stub-name"]', "NFT JMeter Test Stub");
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_ESP_REQUEST);
    await page.getByRole("button", { name: /upload & generate/i }).click();
    await page.waitForURL(/\/jobs\/[0-9a-f-]{36}/, { timeout: 10_000 });
    await waitForJobDone(page, 15_000);

    await ctx.close();
  });

  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
  });

  test("Download NFT Scripts button downloads a real, well-formed JMeter test plan ZIP", async ({ page }) => {
    await page.goto(`/projects/${projectId}`);

    const downloadButton = page.getByRole("button", { name: /download nft scripts/i });
    await expect(downloadButton).toBeVisible({ timeout: 10_000 });

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      downloadButton.click(),
    ]);

    expect(download.suggestedFilename()).toBe("nft-jmeter.zip");

    const streamPath = await download.path();
    expect(streamPath).toBeTruthy();

    const zip = await JSZip.loadAsync(await fs.readFile(streamPath!));
    const names = Object.keys(zip.files);

    expect(names).toContain("test-plan.jmx");
    expect(names).toContain("README.md");
    expect(names.some((n) => n.startsWith("data/") && n.endsWith(".csv"))).toBe(true);

    const jmx = await zip.file("test-plan.jmx")!.async("string");
    expect(jmx).toContain("<jmeterTestPlan");
    expect(jmx).toContain("HTTPSamplerProxy");
    expect(jmx).toContain("${requestPath}");
    expect(jmx).toContain("${requestBody}");
    expect(jmx).toContain("${expectedStatus}");

    const csvName = names.find((n) => n.startsWith("data/") && n.endsWith(".csv"))!;
    const csv = await zip.file(csvName)!.async("string");
    expect(csv.split("\n")[0].trim()).toBe("requestPath,requestBody,expectedStatus");

    const readme = await zip.file("README.md")!.async("string");
    expect(readme.toLowerCase()).toContain("ws-security");
  });
});
