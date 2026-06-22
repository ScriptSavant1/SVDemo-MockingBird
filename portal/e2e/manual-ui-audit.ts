/**
 * Manual UI audit — screenshots every screen and tests key interactions.
 * Run with: npx ts-node --esm portal/e2e/manual-ui-audit.ts
 * OR via: npx playwright test portal/e2e/manual-ui-audit.ts
 */
import { chromium, Page, Browser } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SS_DIR = path.join(__dirname, "../../docs/screenshots/audit");

const ADMIN = { username: "sv.admin", password: "Admin@2026!" };
const SV_USER = { username: "sv.user", password: "User@2026!" };

const bugs: string[] = [];

function noteBug(id: string, description: string) {
  bugs.push(`${id}: ${description}`);
  console.log(`  [BUG] ${id}: ${description}`);
}

async function ss(page: Page, name: string) {
  const file = path.join(SS_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`  [SS] ${name}.png`);
}

async function login(page: Page, creds = ADMIN) {
  await page.goto("http://localhost:3000/login");
  await page.fill("#username", creds.username);
  await page.fill("#password", creds.password);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.includes("login"), { timeout: 10_000 });
}

async function main() {
  fs.mkdirSync(SS_DIR, { recursive: true });
  const browser: Browser = await chromium.launch({ headless: true });

  // ── 1. Login screen ───────────────────────────────────────────────────────
  console.log("\n=== 1. LOGIN ===");
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto("http://localhost:3000/login");
  await ss(page, "01-login-empty");

  // Wrong password
  await page.fill("#username", "sv.admin");
  await page.fill("#password", "wrongpass");
  await page.click('button[type="submit"]');
  await page.waitForTimeout(2000);
  const loginError = await page.locator('[role="alert"], .text-red-600, .text-red-700').first().isVisible();
  if (!loginError) noteBug("BUG-NEW-01", "Login: no error shown for wrong password");
  await ss(page, "02-login-wrong-password");

  // Correct login
  await page.fill("#username", ADMIN.username);
  await page.fill("#password", ADMIN.password);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.includes("login"), { timeout: 10_000 });
  await ss(page, "03-dashboard");

  // ── 2. Dashboard ──────────────────────────────────────────────────────────
  console.log("\n=== 2. DASHBOARD ===");

  // Verify nav items
  const projectsNav = await page.locator('nav a', { hasText: /^Projects$/ }).isVisible();
  if (!projectsNav) noteBug("BUG-NEW-02", "Nav: Projects link missing");
  const adminNav = await page.locator('[data-testid="admin-nav-link"]').isVisible();
  if (!adminNav) noteBug("BUG-NEW-03", "Nav: Admin link missing for ADMIN role");

  // Verify search bar
  const searchBar = await page.locator('input[placeholder*="Search"]').isVisible();
  if (!searchBar) noteBug("BUG-NEW-04", "Dashboard: search bar missing");

  // Verify status filter pills
  const allPill = await page.locator('button', { hasText: /^ALL/ }).isVisible();
  if (!allPill) noteBug("BUG-NEW-05", "Dashboard: ALL filter pill missing");

  // Verify grid/list toggle
  const gridToggle = await page.locator('button[title*="rid"], button[aria-label*="rid"], svg').first().isVisible();
  console.log(`  Grid toggle visible: ${gridToggle}`);

  // Test search
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(500);
  await ss(page, "04-dashboard-search");
  const espCards = await page.locator('[data-testid="project-card"], .cursor-pointer h3, h2, h3').filter({ hasText: /ESP/ }).count();
  console.log(`  Search 'ESP' found ${espCards} results`);
  if (espCards === 0) noteBug("BUG-NEW-06", "Dashboard search for ESP returned no results");

  // Clear search, test status filter
  await page.fill('input[placeholder*="Search"]', "");
  await page.waitForTimeout(300);

  // List view toggle
  await page.locator('button[title*="ist"], button[aria-label*="ist"]').first().click().catch(() => {
    page.locator('svg').nth(1).click();
  });
  await ss(page, "05-dashboard-list-view");

  // ── 3. Create New Project ─────────────────────────────────────────────────
  console.log("\n=== 3. NEW PROJECT ===");
  await page.locator('button', { hasText: /New Project/i }).click();
  await page.waitForURL("**/projects/new", { timeout: 5000 });
  await ss(page, "06-new-project-empty");

  // Fill form
  await page.fill('[name="name"], #name, input[placeholder*="name" i]', "Audit Test Project");
  await page.fill('[name="team"], #team, input[placeholder*="team" i]', "Audit Team");
  await ss(page, "07-new-project-filled");

  // Submit
  await page.locator('button[type="submit"], button', { hasText: /Create/i }).click();
  await page.waitForURL("**/projects/**", { timeout: 8000 });
  const newProjectUrl = page.url();
  const newProjectId = newProjectUrl.split("/projects/")[1]?.split("/")[0];
  console.log(`  Created project: ${newProjectId}`);
  await ss(page, "08-project-detail-new");

  // ── 4. Project Detail ─────────────────────────────────────────────────────
  console.log("\n=== 4. PROJECT DETAIL ===");

  // Verify stub table columns
  const nameCol = await page.locator('th', { hasText: /Name/i }).isVisible();
  const typeCol = await page.locator('th', { hasText: /Type/i }).isVisible();
  const statusCol = await page.locator('th', { hasText: /Status/i }).isVisible();
  if (!nameCol) noteBug("BUG-NEW-07", "ProjectPage: Name column missing");
  if (!typeCol) noteBug("BUG-NEW-08", "ProjectPage: Type column missing");
  if (!statusCol) noteBug("BUG-NEW-09", "ProjectPage: Status column missing");

  // Verify action buttons visible
  const editBtn = await page.locator('[data-testid="edit-project-button"]').isVisible();
  const archiveBtn = await page.locator('[data-testid="archive-project-button"]').isVisible();
  const uploadBtn = await page.locator('a button', { hasText: /Upload/i }).isVisible();
  if (!editBtn) noteBug("BUG-NEW-10", "ProjectPage: Edit button missing");
  if (!archiveBtn) noteBug("BUG-NEW-11", "ProjectPage: Archive button missing");
  if (!uploadBtn) noteBug("BUG-NEW-12", "ProjectPage: Upload Spec button missing");
  await ss(page, "09-project-detail-empty-stubs");

  // ── 5. Upload page ────────────────────────────────────────────────────────
  console.log("\n=== 5. UPLOAD PAGE ===");
  await page.locator('a', { hasText: /Upload Spec/i }).click();
  await page.waitForURL("**/upload", { timeout: 5000 });
  await ss(page, "10-upload-empty");

  // Verify second file slot appears for .txt
  const uploadZone = await page.locator('[data-testid="upload-zone"], .border-dashed').first().isVisible();
  if (!uploadZone) noteBug("BUG-NEW-13", "UploadPage: upload zone missing");
  await page.goBack();

  // ── 6. Edit Project modal ─────────────────────────────────────────────────
  console.log("\n=== 6. EDIT PROJECT ===");
  await page.locator('[data-testid="edit-project-button"]').click();
  await page.waitForTimeout(500);
  const editModal = await page.locator('[data-testid="edit-project-form"]').isVisible();
  if (!editModal) noteBug("BUG-NEW-14", "ProjectPage: Edit modal not opening");
  await ss(page, "11-edit-project-modal");
  await page.keyboard.press("Escape");

  // ── 7. Navigate to an existing project with READY stubs ───────────────────
  console.log("\n=== 7. EXISTING PROJECT WITH READY STUBS ===");
  await page.goto("http://localhost:3000/");
  await page.waitForTimeout(1000);

  // Find ESP project
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(500);
  const espCard = page.locator('.cursor-pointer, [role="button"], a').filter({ hasText: /^ESP$/ }).first();
  const espVisible = await espCard.isVisible();
  if (espVisible) {
    await espCard.click();
    await page.waitForURL("**/projects/**", { timeout: 5000 });
    await ss(page, "12-esp-project-stubs");

    // Verify Deploy and Download ZIP buttons are visible for READY stubs
    const deployBtn = await page.locator('button', { hasText: /^Deploy$/ }).first().isVisible();
    const downloadZipBtn = await page.locator('button', { hasText: /Download ZIP/i }).first().isVisible();
    const viewBtn = await page.locator('button', { hasText: /^View$/ }).first().isVisible();

    console.log(`  Deploy button: ${deployBtn}`);
    console.log(`  Download ZIP button: ${downloadZipBtn}`);
    console.log(`  View button: ${viewBtn}`);

    if (!deployBtn) noteBug("BUG-NEW-15", "ProjectPage: Deploy button not showing for READY stubs");
    if (!downloadZipBtn) noteBug("BUG-NEW-16", "ProjectPage: Download ZIP button not showing for READY stubs");

    // Check stub_type column is not "—"
    const typeDash = await page.locator('td', { hasText: /^—$/ }).count();
    if (typeDash > 0) noteBug("BUG-NEW-17", `ProjectPage: ${typeDash} table cells showing '—' (field mapping issue)`);

    // Test Deploy button (local dev → should immediately go LIVE)
    if (deployBtn) {
      const espProjectId = page.url().split("/projects/")[1]?.split("/")[0];
      await page.locator('button', { hasText: /^Deploy$/ }).first().click();
      await page.waitForTimeout(3000);
      await ss(page, "13-after-deploy");

      // Check if stub status changed
      const liveStatus = await page.locator('[data-status="LIVE"]').first().isVisible();
      const viewBtnAfter = await page.locator('button', { hasText: /^View$/ }).first().isVisible();
      console.log(`  After deploy: LIVE status=${liveStatus}, View btn=${viewBtnAfter}`);
      if (!liveStatus) noteBug("BUG-NEW-18", "ProjectPage: After deploy, stub status not showing LIVE (local dev simulation may not be working)");

      // Click View to go to DeploymentPage
      if (viewBtnAfter) {
        await page.locator('button', { hasText: /^View$/ }).first().click();
        await page.waitForURL("**/stubs/**", { timeout: 8000 });
        await ss(page, "14-deployment-page");

        // Verify tabs are visible
        const overviewTab = await page.locator('button, [role="tab"]', { hasText: /Overview/i }).isVisible();
        const historyTab = await page.locator('button, [role="tab"]', { hasText: /Metrics History/i }).isVisible();
        const reportsTab = await page.locator('button, [role="tab"]', { hasText: /Reports/i }).isVisible();
        if (!overviewTab) noteBug("BUG-NEW-19", "DeploymentPage: Overview tab missing");
        if (!historyTab) noteBug("BUG-NEW-20", "DeploymentPage: Metrics History tab missing");
        if (!reportsTab) noteBug("BUG-NEW-21", "DeploymentPage: Reports tab missing");

        // Click Reports tab
        if (reportsTab) {
          await page.locator('button, [role="tab"]', { hasText: /Reports/i }).click();
          await page.waitForTimeout(1000);
          await ss(page, "15-reports-tab");

          const generateBtn = await page.locator('[data-testid="generate-report-button"]').isVisible();
          if (!generateBtn) noteBug("BUG-NEW-22", "DeploymentPage Reports: Generate Report button missing (requires LIVE status)");

          // Click generate report
          if (generateBtn) {
            await page.locator('[data-testid="generate-report-button"]').click();
            await page.waitForTimeout(2000);
            await ss(page, "16-reports-after-generate");
            console.log("  Report generation triggered");
          }
        }

        // Click History tab
        await page.locator('button, [role="tab"]', { hasText: /Metrics History/i }).click();
        await page.waitForTimeout(1000);
        await ss(page, "17-metrics-history-tab");
      }
    }
  } else {
    noteBug("BUG-NEW-23", "Dashboard: ESP project not found in search results");
  }

  // ── 8. Admin panel ────────────────────────────────────────────────────────
  console.log("\n=== 8. ADMIN PANEL ===");
  await page.goto("http://localhost:3000/admin");
  await page.waitForTimeout(1000);
  await ss(page, "18-admin-panel");

  // Verify Users tab
  const usersTab = await page.locator('button, [role="tab"]', { hasText: /Users/i }).isVisible();
  if (!usersTab) noteBug("BUG-NEW-24", "Admin: Users tab missing");

  // Verify Audit Log tab
  const auditTab = await page.locator('button, [role="tab"]', { hasText: /Audit/i }).isVisible();
  if (!auditTab) noteBug("BUG-NEW-25", "Admin: Audit Log tab missing");

  // Check user table
  const userTable = await page.locator('[data-testid="user-table"], table').first().isVisible();
  if (!userTable) noteBug("BUG-NEW-26", "Admin: User table not visible on initial load");

  // Create user
  const createUserBtn = await page.locator('button', { hasText: /Create User|New User/i }).isVisible();
  if (createUserBtn) {
    await page.locator('button', { hasText: /Create User|New User/i }).click();
    await page.waitForTimeout(500);
    await ss(page, "19-create-user-modal");
    await page.keyboard.press("Escape");
  } else {
    noteBug("BUG-NEW-27", "Admin: Create User button missing");
  }

  // Audit log tab
  if (auditTab) {
    await page.locator('button, [role="tab"]', { hasText: /Audit/i }).click();
    await page.waitForTimeout(1000);
    await ss(page, "20-audit-log");
    const auditTable = await page.locator('[data-testid="audit-table"], table').first().isVisible();
    if (!auditTable) noteBug("BUG-NEW-28", "Admin Audit Log: table not visible");
  }

  // ── 9. SV_USER role — verify no Admin link ───────────────────────────────
  console.log("\n=== 9. SV_USER ROLE TEST ===");
  const page2 = await browser.newPage();
  await page2.setViewportSize({ width: 1440, height: 900 });
  await login(page2, SV_USER);
  await ss(page2, "21-svuser-dashboard");

  const adminLinkForUser = await page2.locator('[data-testid="admin-nav-link"]').isVisible();
  if (adminLinkForUser) noteBug("BUG-NEW-29", "Nav: Admin link visible for SV_TEAM role (should be hidden)");
  console.log(`  Admin link visible for SV_USER: ${adminLinkForUser}`);

  // Try accessing admin page directly — should redirect or 403
  await page2.goto("http://localhost:3000/admin");
  await page2.waitForTimeout(1000);
  const blockedAdmin = page2.url().includes("/admin");
  console.log(`  SV_USER can access /admin: ${blockedAdmin}`);
  await ss(page2, "22-svuser-admin-blocked");
  await page2.close();

  // ── 10. AI Generate page ──────────────────────────────────────────────────
  console.log("\n=== 10. AI GENERATE PAGE ===");
  // Go to ESP project
  await page.goto("http://localhost:3000/");
  await page.fill('input[placeholder*="Search"]', "ESP");
  await page.waitForTimeout(500);
  const espCard2 = page.locator('a, .cursor-pointer').filter({ hasText: /^ESP$/ }).first();
  if (await espCard2.isVisible()) {
    await espCard2.click();
    await page.waitForURL("**/projects/**", { timeout: 5000 });
    await page.locator('a', { hasText: /Generate with AI/i }).click();
    await page.waitForURL("**/ai-generate", { timeout: 5000 });
    await ss(page, "23-ai-generate-page");
    const aiPrompt = await page.locator('textarea, input[placeholder*="plain" i]').first().isVisible();
    if (!aiPrompt) noteBug("BUG-NEW-30", "AI Generate page: prompt input missing");
  }

  // ── 11. Sign out flow ─────────────────────────────────────────────────────
  console.log("\n=== 11. SIGN OUT ===");
  await page.goto("http://localhost:3000/");
  await page.locator('button', { hasText: /Sign out/i }).click();
  await page.waitForURL("**/login", { timeout: 5000 });
  await ss(page, "24-after-signout");
  const loginFormVisible = await page.locator('#username').isVisible();
  if (!loginFormVisible) noteBug("BUG-NEW-31", "After sign out: not redirected to login page");

  await browser.close();

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log("\n=== AUDIT SUMMARY ===");
  console.log(`Screenshots saved to: ${SS_DIR}`);
  console.log(`\nBugs found (${bugs.length}):`);
  if (bugs.length === 0) {
    console.log("  None — all checks passed!");
  } else {
    bugs.forEach((b) => console.log(`  ${b}`));
  }

  // Write results to file
  const reportPath = path.join(SS_DIR, "audit-report.json");
  fs.writeFileSync(reportPath, JSON.stringify({ bugs, timestamp: new Date().toISOString() }, null, 2));
  console.log(`\nReport: ${reportPath}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
