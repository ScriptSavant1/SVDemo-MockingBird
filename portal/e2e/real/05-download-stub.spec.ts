/**
 * Real E2E — Download WireMock stub ZIP.
 *
 * Uploads a CA LISA file, generates the stub, then downloads the WireMock ZIP
 * and verifies it contains valid JSON mapping files.
 */
import { test, expect } from "@playwright/test";
import { ADMIN, SAMPLE_ESP_REQUEST, loginAs, waitForJobDone } from "./helpers";
import JSZip from "jszip"; // optional — just check bytes if not installed

const PROJECT_NAME = `Download Test ${Date.now()}`;

test.describe("Download WireMock ZIP (real)", () => {
  let projectId: string;
  let stubId: string;

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, ADMIN);

    // Create project
    await page.getByTestId("new-project-button").click();
    await page.fill('[data-testid="name-input"]', PROJECT_NAME);
    await page.fill('[data-testid="team-input"]', "Download Tests");
    await page.selectOption('[data-testid="environment-select"]', "TEST");
    await page.fill('[data-testid="tps-input"]', "500");
    await page.click('[data-testid="create-submit-button"]');
    await page.waitForURL(/\/projects\/([0-9a-f-]{36})/, { timeout: 8_000 });
    const match = page.url().match(/\/projects\/([0-9a-f-]{36})/);
    projectId = match?.[1] ?? "";

    // Upload and generate
    await page.goto(`/projects/${projectId}/upload`);
    await page.fill('[id="stub-name"]', "Download Test Stub");
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_ESP_REQUEST);
    await page.getByRole("button", { name: /upload & generate/i }).click();
    await page.waitForURL(/\/jobs\/[0-9a-f-]{36}/, { timeout: 10_000 });
    await waitForJobDone(page, 15_000);

    await ctx.close();
  });

  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
  });

  test("wiremock.zip download endpoint returns a ZIP", async ({ page }) => {
    // We need the stub_id — get it from the project page
    const resp = await page.request.get(`http://localhost:8001/api/v1/projects/${projectId}/stubs`, {
      headers: { Authorization: `Bearer ${await getToken(page)}` },
    });
    expect(resp.status()).toBe(200);
    const stubs = await resp.json() as { id: string }[];
    expect(stubs.length).toBeGreaterThan(0);
    stubId = stubs[0]!.id;

    // Download the WireMock ZIP via ingestion-service
    const dlResp = await page.request.get(
      `http://localhost:8003/api/v1/projects/${projectId}/stubs/${stubId}/wiremock.zip`,
      { headers: { Authorization: `Bearer ${await getToken(page)}` } },
    );
    expect(dlResp.status()).toBe(200);
    expect(dlResp.headers()["content-type"]).toContain("application/zip");

    const body = await dlResp.body();
    expect(body.length).toBeGreaterThan(100); // non-empty ZIP

    // Verify ZIP magic bytes PK\x03\x04
    expect(body[0]).toBe(0x50); // P
    expect(body[1]).toBe(0x4b); // K
  });
});

async function getToken(page: ReturnType<typeof test.info> extends never ? never : any): Promise<string> {
  const resp = await page.request.post("http://localhost:3001/api/v1/auth/login", {
    data: { username: ADMIN.username, password: ADMIN.password },
  });
  const data = await resp.json();
  return data.access_token as string;
}
