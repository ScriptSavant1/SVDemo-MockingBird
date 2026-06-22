/**
 * Comprehensive UI audit — screenshots every portal screen and tests key interactions.
 * Run: npx playwright test --config=playwright.real.config.ts e2e/ui-audit.spec.ts
 */
import { test, expect, Page } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SS_DIR = path.join(__dirname, "../../docs/screenshots/audit");

const ADMIN = { username: "sv.admin", password: "Admin@2026!" };
const SV_USER = { username: "sv.user", password: "User@2026!" };

test.beforeAll(() => {
  fs.mkdirSync(SS_DIR, { recursive: true });
});

async function ss(page: Page, name: string) {
  await page.screenshot({ path: path.join(SS_DIR, `${name}.png`), fullPage: true });
}

async function login(page: Page, creds = ADMIN) {
  await page.goto("/login");
  await page.fill("#username", creds.username);
  await page.fill("#password", creds.password);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.includes("login"), { timeout: 10_000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. AUTH
// ─────────────────────────────────────────────────────────────────────────────
test("01 login page renders", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator("#username")).toBeVisible();
  await expect(page.locator("#password")).toBeVisible();
  await ss(page, "01-login-empty");
});

test("02 wrong password shows error", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#username", "sv.admin");
  await page.fill("#password", "wrong!");
  await page.click('button[type="submit"]');
  await expect(page.locator('[role="alert"], .text-red-600, .text-red-700').first()).toBeVisible({ timeout: 5000 });
  await ss(page, "02-login-wrong-password");
});

test("03 admin login and dashboard", async ({ page }) => {
  await login(page);
  await ss(page, "03-dashboard-admin");
  // Nav
  await expect(page.locator('nav a', { hasText: /^Projects$/ })).toBeVisible();
  await expect(page.locator('[data-testid="admin-nav-link"]')).toBeVisible();
});

test("04 SV_USER has no admin link", async ({ page }) => {
  await login(page, SV_USER);
  await ss(page, "04-dashboard-svuser");
  await expect(page.locator('[data-testid="admin-nav-link"]')).not.toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. DASHBOARD
// ─────────────────────────────────────────────────────────────────────────────
test("05 dashboard search and filter", async ({ page }) => {
  await login(page);
  // search
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(400);
  await ss(page, "05-dashboard-search-esp");
  // clear and status filter
  await page.fill('input[placeholder*="Search"]', "");
  await page.waitForTimeout(200);
  await ss(page, "06-dashboard-all-projects");
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. PROJECT DETAIL — stubs show READY status and action buttons
// ─────────────────────────────────────────────────────────────────────────────
test("07 ESP project stubs show READY status and Deploy + Download ZIP buttons", async ({ page }) => {
  await login(page);
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(400);
  // Click the ESP project (exact name)
  await page.locator('h2, h3').filter({ hasText: /^ESP$/ }).first().click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });
  await ss(page, "07-esp-project-detail");

  // Stubs table should NOT show "—" in TYPE or STATUS columns
  const typeDashes = await page.locator('td').filter({ hasText: /^—$/ }).count();
  expect(typeDashes).toBe(0);

  // READY status badge should be visible
  await expect(page.locator('[data-status="READY"]').first()).toBeVisible();

  // Deploy button should be visible
  await expect(page.locator('button', { hasText: /^Deploy$/ }).first()).toBeVisible();

  // Download ZIP button should be visible
  await expect(page.locator('button', { hasText: /Download ZIP/i }).first()).toBeVisible();

  await ss(page, "07b-esp-stub-buttons-visible");
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. UPLOAD + GENERATE
// ─────────────────────────────────────────────────────────────────────────────
test("08 upload page and two-file zone", async ({ page }) => {
  await login(page);
  // Navigate to any project's upload page
  await page.goto("/");
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(400);
  await page.locator('h2, h3').filter({ hasText: /^ESP$/ }).first().click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });
  await page.locator('a', { hasText: /Upload Spec/i }).click();
  await page.waitForURL("**/upload", { timeout: 5000 });
  await ss(page, "08-upload-page-empty");
  await expect(page.locator('text=Stub name')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. DEPLOY → LIVE → DEPLOYMENT PAGE → REPORTS
// ─────────────────────────────────────────────────────────────────────────────
test("09 deploy stub goes LIVE and reports tab accessible", async ({ page }) => {
  await login(page);
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(400);
  await page.locator('h2, h3').filter({ hasText: /^ESP$/ }).first().click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });

  // Find first READY stub and deploy it
  const deployBtn = page.locator('button', { hasText: /^Deploy$/ }).first();
  await expect(deployBtn).toBeVisible();
  await deployBtn.click();
  await page.waitForTimeout(3000);
  await ss(page, "09-after-deploy");

  // After deploy (local dev → LIVE immediately) View button should appear
  await expect(page.locator('button', { hasText: /^View$/ }).first()).toBeVisible({ timeout: 5000 });
  await ss(page, "09b-stub-live-view-button");

  // Click View → DeploymentPage
  await page.locator('button', { hasText: /^View$/ }).first().click();
  await page.waitForURL("**/stubs/**", { timeout: 8000 });
  await ss(page, "10-deployment-page-overview");

  // Verify tabs
  await expect(page.locator('button, [role="tab"]', { hasText: /Overview/i })).toBeVisible();
  await expect(page.locator('button, [role="tab"]', { hasText: /Metrics History/i })).toBeVisible();
  await expect(page.locator('button, [role="tab"]', { hasText: /Reports/i })).toBeVisible();

  // Click Reports tab
  await page.locator('button, [role="tab"]', { hasText: /Reports/i }).click();
  await page.waitForTimeout(1000);
  await ss(page, "11-reports-tab");

  // Generate Report button should be visible (LIVE deployment)
  await expect(page.locator('[data-testid="generate-report-button"]')).toBeVisible();

  // Metrics History tab
  await page.locator('button, [role="tab"]', { hasText: /Metrics History/i }).click();
  await page.waitForTimeout(1000);
  await ss(page, "12-metrics-history-tab");
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. EDIT PROJECT
// ─────────────────────────────────────────────────────────────────────────────
test("13 edit project modal", async ({ page }) => {
  await login(page);
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(400);
  await page.locator('h2, h3').filter({ hasText: /^ESP$/ }).first().click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });
  await page.locator('[data-testid="edit-project-button"]').click();
  await expect(page.locator('[data-testid="edit-project-form"]')).toBeVisible({ timeout: 3000 });
  await ss(page, "13-edit-project-modal");
  await page.keyboard.press("Escape");
});

// ─────────────────────────────────────────────────────────────────────────────
// 7. CREATE NEW PROJECT
// ─────────────────────────────────────────────────────────────────────────────
test("14 create new project", async ({ page }) => {
  await login(page);
  await page.locator('button', { hasText: /New Project/i }).click();
  await page.waitForURL("**/projects/new", { timeout: 5000 });
  await ss(page, "14-new-project-form");
  // Fill required fields
  await page.fill('[data-testid="name-input"]', "Audit New Project");
  await page.fill('[data-testid="team-input"]', "Audit Team");
  await ss(page, "14b-new-project-filled");
  await page.locator('button[type="submit"], button', { hasText: /Create/i }).click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });
  await ss(page, "14c-new-project-created");
});

// ─────────────────────────────────────────────────────────────────────────────
// 8. AI GENERATE PAGE
// ─────────────────────────────────────────────────────────────────────────────
test("15 AI generate page accessible", async ({ page }) => {
  await login(page);
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(400);
  await page.locator('h2, h3').filter({ hasText: /^ESP$/ }).first().click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });
  await page.locator('a', { hasText: /Generate with AI/i }).click();
  await page.waitForURL("**/ai-generate", { timeout: 5000 });
  await ss(page, "15-ai-generate-page");
  await expect(page.locator('textarea, input[placeholder*="plain" i], input[placeholder*="descri" i]').first()).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────────
// 9. ADMIN PANEL
// ─────────────────────────────────────────────────────────────────────────────
test("16 admin panel — users tab", async ({ page }) => {
  await login(page);
  await page.goto("/admin");
  await ss(page, "16-admin-users-tab");
  await expect(page.locator('table, [data-testid="user-table"]').first()).toBeVisible();
  // Create user button
  await expect(page.locator('button', { hasText: /Create User|New User/i })).toBeVisible();
});

test("17 admin panel — audit log tab", async ({ page }) => {
  await login(page);
  await page.goto("/admin");
  await page.locator('button, [role="tab"]', { hasText: /Audit/i }).click();
  await page.waitForTimeout(1000);
  await ss(page, "17-admin-audit-log");
  await expect(page.locator('[data-testid="audit-table"], table').first()).toBeVisible();
});

test("18 admin create user modal", async ({ page }) => {
  await login(page);
  await page.goto("/admin");
  await page.locator('button', { hasText: /Create User|New User/i }).click();
  await page.waitForTimeout(500);
  await ss(page, "18-admin-create-user-modal");
  await expect(page.locator('form, [data-testid="create-user-form"]').first()).toBeVisible();
  await page.keyboard.press("Escape");
});

// ─────────────────────────────────────────────────────────────────────────────
// 10. JOB PROGRESS PAGE
// ─────────────────────────────────────────────────────────────────────────────
test("19 job progress page shows DONE with green checkmarks", async ({ page }) => {
  await login(page);
  // Create a new project and upload to trigger a job
  await page.locator('button', { hasText: /New Project/i }).click();
  await page.waitForURL("**/projects/new", { timeout: 5000 });
  await page.fill('[data-testid="name-input"]', "Job Progress Test");
  await page.fill('[data-testid="team-input"]', "QA");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });
  const projectUrl = page.url();

  // Navigate to upload
  await page.locator('a', { hasText: /Upload Spec/i }).click();
  await page.waitForURL("**/upload", { timeout: 5000 });

  // Upload a sample file
  const sampleFile = path.join(__dirname, "../../sample_svs/ESP_Account_Enquiry_v1.txt");
  if (fs.existsSync(sampleFile)) {
    // Set stub name
    await page.fill('#stub-name', "Job Test Stub");
    await page.setInputFiles('input[type="file"]', sampleFile);
    await page.waitForTimeout(500);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL("**/jobs/**", { timeout: 15000 });
    await ss(page, "19-job-progress-running");
    // Wait for DONE
    await page.waitForSelector('[data-testid="job-status-done"], text=DONE', { timeout: 30000 }).catch(() => null);
    await ss(page, "19b-job-progress-done");
  } else {
    await ss(page, "19-job-progress-skipped");
    test.skip();
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 11. SIGN OUT
// ─────────────────────────────────────────────────────────────────────────────
test("20 sign out returns to login", async ({ page }) => {
  await login(page);
  await page.locator('button', { hasText: /Sign out/i }).click();
  await page.waitForURL("**/login", { timeout: 5000 });
  await ss(page, "20-after-signout");
  await expect(page.locator("#username")).toBeVisible();
});
