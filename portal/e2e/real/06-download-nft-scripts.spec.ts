/**
 * Real E2E — Download NFT Scripts ZIP (JMeter + DevWeb).
 *
 * Uploads a CA LISA sample file through the real portal UI, generates the
 * stub, clicks the "Download NFT Scripts" button, and verifies the
 * downloaded ZIP contains both a well-formed JMeter test plan and a
 * well-formed LoadRunner DevWeb (VuGen) project — the combined NFT script
 * generation feature (Phase 1 JMeter + Phase 2 DevWeb, see
 * docs/progress/PHASE1_JMETER_NFT_GENERATION.md and
 * docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md).
 */
import { test, expect } from "@playwright/test";
import { ADMIN, SAMPLE_ESP_REQUEST, loginAs, waitForJobDone } from "./helpers";
import JSZip from "jszip";
import { promises as fs } from "fs";

const PROJECT_NAME = `NFT Scripts Test ${Date.now()}`;

test.describe("Download NFT Scripts ZIP (real)", () => {
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
    await page.fill('[id="stub-name"]', "NFT Scripts Test Stub");
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_ESP_REQUEST);
    await page.getByRole("button", { name: /upload & generate/i }).click();
    await page.waitForURL(/\/jobs\/[0-9a-f-]{36}/, { timeout: 10_000 });
    await waitForJobDone(page, 15_000);

    await ctx.close();
  });

  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
  });

  test("Download NFT Scripts button downloads a ZIP with both JMeter and DevWeb projects", async ({ page }) => {
    await page.goto(`/projects/${projectId}`);

    const downloadButton = page.getByRole("button", { name: /download nft scripts/i });
    await expect(downloadButton).toBeVisible({ timeout: 10_000 });

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      downloadButton.click(),
    ]);

    expect(download.suggestedFilename()).toBe("nft-scripts.zip");

    const streamPath = await download.path();
    expect(streamPath).toBeTruthy();

    const zip = await JSZip.loadAsync(await fs.readFile(streamPath!));
    const names = Object.keys(zip.files);

    // ── top-level ──
    expect(names).toContain("README.md");

    // ── jmeter/ ──
    expect(names).toContain("jmeter/test-plan.jmx");
    expect(names).toContain("jmeter/README.md");
    expect(names.some((n) => n.startsWith("jmeter/data/") && n.endsWith(".csv"))).toBe(true);

    const jmx = await zip.file("jmeter/test-plan.jmx")!.async("string");
    expect(jmx).toContain("<jmeterTestPlan");
    expect(jmx).toContain("HTTPSamplerProxy");
    expect(jmx).toContain("${requestPath}");

    // ── devweb/ ──
    expect(names).toContain("devweb/main.js");
    expect(names).toContain("devweb/rts.yml");
    expect(names).toContain("devweb/parameters.yml");
    expect(names).toContain("devweb/tsconfig.json");
    expect(names).toContain("devweb/ScriptUploadMetadata.xml");
    expect(names.some((n) => n.startsWith("devweb/") && n.endsWith(".usr"))).toBe(true);
    expect(names.some((n) => n.startsWith("devweb/data/") && n.endsWith(".csv"))).toBe(true);
    // Vendor's proprietary SDK type file is deliberately not bundled
    expect(names.some((n) => n.endsWith("DevWebSdk.d.ts"))).toBe(false);

    const mainJs = await zip.file("devweb/main.js")!.async("string");
    expect(mainJs).toContain("load.action(");
    expect(mainJs).toContain("new load.Transaction(");
    expect(mainJs).toContain("load.params");

    const paramsYml = await zip.file("devweb/parameters.yml")!.async("string");
    expect(paramsYml).toContain("type: csv");
    expect(paramsYml).toContain("same as");
  });
});
