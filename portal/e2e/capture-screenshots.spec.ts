/**
 * Screenshot capture script for the User Guide.
 *
 * Run:  npx playwright test e2e/capture-screenshots.ts --reporter=list
 *
 * All API calls are mocked with page.route() — no backend needed.
 * Screenshots land in docs/screenshots/ at the repo root.
 */
import { test, expect, Page } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOTS_DIR = path.resolve(__dirname, "../../docs/screenshots");

// ── shared mock data ──────────────────────────────────────────────────────────

const ADMIN_TOKEN = "tok-admin-demo";
const USER_TOKEN = "tok-user-demo";

const ADMIN_LOGIN_RESP = {
  access_token: ADMIN_TOKEN,
  token_type: "Bearer",
  expires_in: 3600,
  username: "sv.admin",
  role: "ADMIN",
};
const USER_LOGIN_RESP = {
  access_token: USER_TOKEN,
  token_type: "Bearer",
  expires_in: 3600,
  username: "j.smith",
  role: "SV_TEAM",
};

const PROJECTS = [
  {
    id: "proj-001",
    name: "Payments API Stub",
    team: "Core Banking",
    environment: "TEST",
    expected_tps: 5000,
    description: "Stubs for the payments micro-service",
    status: "LIVE",
    stub_url: "https://stubs.mockingbird.internal/proj-001",
    api_key: "mb-key-7a3f9c2d",
    created_by: "sv.admin",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-06-10T14:30:00Z",
  },
  {
    id: "proj-002",
    name: "Account Enquiry Stub",
    team: "ESP Team",
    environment: "STAGING",
    expected_tps: 2000,
    description: "ESP account enquiry responses for regression suite",
    status: "DRAFT",
    stub_url: null,
    api_key: null,
    created_by: "j.smith",
    created_at: "2026-05-20T08:00:00Z",
    updated_at: "2026-05-20T08:00:00Z",
  },
  {
    id: "proj-003",
    name: "FX Rate Lookup Stub",
    team: "Treasury",
    environment: "TEST",
    expected_tps: 8000,
    description: "Mock FX rate feed for interest rate integration tests",
    status: "SUSPENDED",
    stub_url: null,
    api_key: null,
    created_by: "sv.admin",
    created_at: "2026-03-05T09:00:00Z",
    updated_at: "2026-06-15T11:00:00Z",
  },
];

const STUBS = [
  {
    id: "stub-001",
    project_id: "proj-001",
    name: "Payment Process Stub",
    format: "ca-lisa-http-pair",
    status: "READY",
    scenario_count: 3,
    created_at: "2026-01-15T10:05:00Z",
    updated_at: "2026-01-16T09:00:00Z",
  },
];

const USERS = [
  {
    id: "u-001",
    username: "sv.admin",
    email: "sv.admin@company.com",
    role: "ADMIN",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "u-002",
    username: "j.smith",
    email: "j.smith@company.com",
    role: "SV_TEAM",
    is_active: true,
    created_at: "2026-02-14T09:00:00Z",
  },
  {
    id: "u-003",
    username: "a.jones",
    email: "a.jones@company.com",
    role: "PROJECT_OWNER",
    is_active: true,
    created_at: "2026-03-10T11:30:00Z",
  },
  {
    id: "u-004",
    username: "b.carter",
    email: "b.carter@company.com",
    role: "VIEWER",
    is_active: false,
    created_at: "2026-04-01T08:00:00Z",
  },
];

const AUDIT_LOG = [
  { id: "a1", action: "user.login", username: "sv.admin", user_id: "u-001", detail: { ip: "10.0.0.5" }, created_at: "2026-06-21T08:14:00Z" },
  { id: "a2", action: "stub.generate", username: "j.smith", user_id: "u-002", detail: { project_id: "proj-001", stub_id: "stub-001" }, created_at: "2026-06-20T16:40:00Z" },
  { id: "a3", action: "project.create", username: "j.smith", user_id: "u-002", detail: { name: "Account Enquiry Stub" }, created_at: "2026-05-20T08:00:00Z" },
  { id: "a4", action: "user.create", username: "sv.admin", user_id: "u-001", detail: { new_username: "a.jones" }, created_at: "2026-03-10T11:30:00Z" },
];

// ── helpers ───────────────────────────────────────────────────────────────────

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

async function setupAdminMocks(page: Page) {
  await page.route("**/api/v1/auth/login", (r) => r.fulfill(json(ADMIN_LOGIN_RESP)));
  await page.route("**/api/v1/auth/logout", (r) => r.fulfill(json({})));
  await page.route("**/api/v1/projects", (r) => {
    if (r.request().method() === "GET") return r.fulfill(json(PROJECTS));
    return r.fulfill(json({ ...PROJECTS[1], id: "proj-new", name: "Card Fraud Detection Stub", status: "DRAFT" }, 201));
  });
  await page.route("**/api/v1/projects/proj-001", (r) => r.fulfill(json(PROJECTS[0])));
  await page.route("**/api/v1/projects/proj-001/stubs", (r) => r.fulfill(json(STUBS)));
  await page.route("**/api/v1/projects/proj-001/deployments", (r) => r.fulfill(json([])));
  await page.route("**/api/v1/admin/users*", (r) => {
    if (r.request().method() === "GET") return r.fulfill(json({ items: USERS, total: USERS.length, page: 1, size: 50 }));
    return r.fulfill(json({ id: "u-005", username: "new.user", email: "new.user@company.com", role: "VIEWER", is_active: true, created_at: "2026-06-21T12:00:00Z" }, 201));
  });
  await page.route("**/api/v1/admin/audit*", (r) =>
    r.fulfill(json({ items: AUDIT_LOG, total: AUDIT_LOG.length, page: 1, size: 50 }))
  );
  await page.route("**/api/v1/projects/proj-001/stubs/upload", (r) =>
    r.fulfill(json({ valid: true, format_detected: "ca-lisa-http-pair", stub_id: "stub-002", errors: [], warnings: [], stub_count: 2, scenario_count: 3 }))
  );
  await page.route("**/api/v1/projects/proj-001/stubs/*/generate", (r) =>
    r.fulfill(json({ job_id: "job-001", status: "QUEUED", type: "GENERATE" }, 202))
  );
  await page.route("**/api/v1/jobs/job-001", (r) =>
    r.fulfill(json({ id: "job-001", type: "GENERATE", status: "DONE", project_id: "proj-001", stub_id: "stub-002", result: { stub_id: "stub-002" }, error_message: null, created_at: "2026-06-21T12:00:00Z", updated_at: "2026-06-21T12:01:30Z" }))
  );
}

async function setupUserMocks(page: Page) {
  await page.route("**/api/v1/auth/login", (r) => r.fulfill(json(USER_LOGIN_RESP)));
  await page.route("**/api/v1/auth/logout", (r) => r.fulfill(json({})));
  await page.route("**/api/v1/projects", (r) => r.fulfill(json(PROJECTS.slice(0, 2))));
  await page.route("**/api/v1/projects/proj-002", (r) => r.fulfill(json(PROJECTS[1])));
  await page.route("**/api/v1/projects/proj-002/stubs", (r) => r.fulfill(json([])));
  await page.route("**/api/v1/projects/proj-002/deployments", (r) => r.fulfill(json([])));
  await page.route("**/api/v1/projects/proj-002/stubs/upload", (r) =>
    r.fulfill(json({ valid: true, format_detected: "ca-lisa-http-pair", stub_id: "stub-003", errors: [], warnings: [], stub_count: 1, scenario_count: 2 }))
  );
  await page.route("**/api/v1/projects/proj-002/stubs/*/generate", (r) =>
    r.fulfill(json({ job_id: "job-002", status: "QUEUED", type: "GENERATE" }, 202))
  );
  await page.route("**/api/v1/jobs/job-002", (r) =>
    r.fulfill(json({ id: "job-002", type: "GENERATE", status: "DONE", project_id: "proj-002", stub_id: "stub-003", result: {}, error_message: null, created_at: "2026-06-21T13:00:00Z", updated_at: "2026-06-21T13:01:45Z" }))
  );
}

async function shot(page: Page, name: string) {
  // Small settle time for animations
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(SHOTS_DIR, `${name}.png`), fullPage: false });
}

async function loginAs(page: Page, role: "admin" | "user") {
  const username = role === "admin" ? "sv.admin" : "j.smith";
  const password = "Password123!";
  await page.goto("/login");
  await page.fill("#username", username);
  await page.fill("#password", password);
  await shot(page, `${role}-01-login-filled`);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes("login"), { timeout: 5_000 });
}

// ── ADMIN screenshots ─────────────────────────────────────────────────────────

test.describe("Admin screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await setupAdminMocks(page);
  });

  test("01 login page", async ({ page }) => {
    await page.goto("/login");
    await shot(page, "admin-00-login-empty");
    await page.fill("#username", "sv.admin");
    await shot(page, "admin-01-login-filled");
  });

  test("02 dashboard", async ({ page }) => {
    await loginAs(page, "admin");
    await shot(page, "admin-02-dashboard");
  });

  test("03 create project", async ({ page }) => {
    await loginAs(page, "admin");
    await page.getByTestId("new-project-button").click();
    await expect(page).toHaveURL("/projects/new");
    await shot(page, "admin-03-create-project-empty");

    await page.fill('[data-testid="name-input"]', "Card Fraud Detection Stub");
    await page.fill('[data-testid="team-input"]', "Fraud & Risk");
    await page.selectOption('[data-testid="environment-select"]', "TEST");
    await page.fill('[data-testid="tps-input"]', "3000");
    await page.fill('[data-testid="description-textarea"]', "Stubs for the fraud detection scoring API");
    await shot(page, "admin-04-create-project-filled");

    await page.click('button[type="submit"]');
    await shot(page, "admin-05-project-created");
  });

  test("04 project detail", async ({ page }) => {
    await loginAs(page, "admin");
    await page.getByText("Payments API Stub").click();
    await expect(page).toHaveURL("/projects/proj-001");
    await shot(page, "admin-06-project-detail");
  });

  test("05 upload page", async ({ page }) => {
    await loginAs(page, "admin");
    await page.goto("/projects/proj-001/upload");
    await shot(page, "admin-07-upload-empty");

    await page.fill('[id="stub-name"]', "Payment Process Stub v2");
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "payment_stubs.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("={Method=\"POST\" URL=\"/api/payment\"}Body\nResponseHeader={StatusCode=\"200\"}Response"),
    });
    await shot(page, "admin-08-upload-file-selected");

    await page.getByRole("button", { name: /upload & generate/i }).click();
    await expect(page).toHaveURL(/\/jobs\//);
    await shot(page, "admin-09-job-status");
  });

  test("06 admin panel — users", async ({ page }) => {
    await loginAs(page, "admin");
    await page.getByTestId("admin-nav-link").click();
    await expect(page).toHaveURL("/admin");
    await shot(page, "admin-10-admin-users");
  });

  test("07 admin panel — create user modal", async ({ page }) => {
    await loginAs(page, "admin");
    await page.goto("/admin");
    await page.getByTestId("new-user-button").click();
    await shot(page, "admin-11-create-user-empty");

    await page.fill('[data-testid="new-user-username"]', "c.brown");
    await page.fill('[data-testid="new-user-email"]', "c.brown@company.com");
    await page.fill('[data-testid="new-user-password"]', "Temp@2026!");
    await page.selectOption('[data-testid="new-user-role"]', "SV_TEAM");
    await shot(page, "admin-12-create-user-filled");

    await page.getByTestId("create-user-submit").click();
    await shot(page, "admin-13-user-created");
  });

  test("08 admin panel — audit log", async ({ page }) => {
    await loginAs(page, "admin");
    await page.goto("/admin");
    await page.getByRole("tab", { name: "Audit Log" }).click();
    await shot(page, "admin-14-audit-log");
  });
});

// ── USER (SV_TEAM) screenshots ────────────────────────────────────────────────

test.describe("User screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await setupUserMocks(page);
  });

  test("01 login page", async ({ page }) => {
    await page.goto("/login");
    await shot(page, "user-01-login");
    await page.fill("#username", "j.smith");
    await shot(page, "user-01-login-filled");
  });

  test("02 dashboard — user view", async ({ page }) => {
    await loginAs(page, "user");
    await shot(page, "user-02-dashboard");
  });

  test("03 project detail", async ({ page }) => {
    await loginAs(page, "user");
    await page.getByText("Account Enquiry Stub").click();
    await expect(page).toHaveURL("/projects/proj-002");
    await shot(page, "user-03-project-detail");
  });

  test("04 upload stub file", async ({ page }) => {
    await loginAs(page, "user");
    await page.goto("/projects/proj-002/upload");
    await shot(page, "user-04-upload-empty");

    await page.fill('[id="stub-name"]', "Account Enquiry Stub v1");
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "account_stubs.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("={Method=\"POST\" URL=\"/api/accounts\"}Body\nResponseHeader={StatusCode=\"200\"}Response"),
    });
    await shot(page, "user-05-upload-file-selected");

    await page.getByRole("button", { name: /upload & generate/i }).click();
    await expect(page).toHaveURL(/\/jobs\//);
    await shot(page, "user-06-job-status");
  });

  test("05 no admin link visible", async ({ page }) => {
    await loginAs(page, "user");
    await shot(page, "user-07-no-admin-link");
  });
});
