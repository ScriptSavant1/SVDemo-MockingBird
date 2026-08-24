/**
 * Shared fixtures and mock data for Playwright E2E tests.
 *
 * All API calls are intercepted at the browser level via page.route(), so no
 * backend services need to be running during E2E tests.
 */
import { Page, Route } from "@playwright/test";

// ── mock data ─────────────────────────────────────────────────────────────────

export const MOCK_USER = {
  id: "11111111-0000-0000-0000-000000000001",
  username: "admin",
  email: "admin@company.com",
  role: "ADMIN",
};

// Matches the real auth-service response shape (services/auth-service/src/routes/auth.ts):
// { access_token, token_type, expires_in, user: { id, username, email, role } }.
// LoginPage.tsx reads res.user.username / res.user.role — a flat shape here
// silently breaks every mocked login (this bit the E2E suite for a while).
export const MOCK_LOGIN_RESPONSE = {
  access_token: "test-token-abc123",
  token_type: "Bearer",
  expires_in: 3600,
  user: MOCK_USER,
};

export const MOCK_PROJECTS = [
  {
    id: "proj-001",
    name: "Payments API Stub",
    team: "Core Banking",
    environment: "TEST",
    expected_tps: 5000,
    description: "Stubs for the payments micro-service",
    status: "LIVE",
    stub_url: "https://stub.example.com/proj-001",
    api_key: "key-xyz",
    created_by: "admin",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-06-10T14:30:00Z",
  },
  {
    id: "proj-002",
    name: "Account Enquiry Stub",
    team: "ESP Team",
    environment: "STAGING",
    expected_tps: 2000,
    description: null,
    status: "DRAFT",
    stub_url: null,
    api_key: null,
    created_by: "admin",
    created_at: "2026-05-20T08:00:00Z",
    updated_at: "2026-05-20T08:00:00Z",
  },
];

export const MOCK_NEW_PROJECT = {
  id: "proj-new",
  name: "New Test Project",
  team: "QA Team",
  environment: "TEST",
  expected_tps: 1000,
  description: "Created during E2E test",
  status: "DRAFT",
  stub_url: null,
  api_key: null,
  created_by: "admin",
  created_at: "2026-06-21T12:00:00Z",
  updated_at: "2026-06-21T12:00:00Z",
};

// ── API mock helpers ──────────────────────────────────────────────────────────

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/** Intercept auth endpoints. Call before navigating to login. */
export async function mockAuth(
  page: Page,
  opts: { failLogin?: boolean; role?: string; username?: string } = {}
) {
  await page.route("**/api/v1/auth/login", (route) => {
    if (opts.failLogin) {
      return json(route, { detail: "Invalid username or password" }, 401);
    }
    if (opts.role || opts.username) {
      return json(route, {
        ...MOCK_LOGIN_RESPONSE,
        user: {
          ...MOCK_USER,
          role: opts.role ?? MOCK_USER.role,
          username: opts.username ?? MOCK_USER.username,
        },
      });
    }
    return json(route, MOCK_LOGIN_RESPONSE);
  });

  await page.route("**/api/v1/auth/logout", (route) => json(route, {}));
}

/** Intercept the projects list endpoint. */
export async function mockProjects(page: Page, projects = MOCK_PROJECTS) {
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "GET") {
      // projectsApi.list() reads a paginated envelope ({ items, total, limit,
      // offset }, see portal/src/api/types.ts ProjectPage) — a bare array here
      // silently resolves to an empty list (page.items is undefined on an array).
      return json(route, { items: projects, total: projects.length, limit: 50, offset: 0 });
    }
    // POST /projects → create
    return json(route, MOCK_NEW_PROJECT, 201);
  });
}

/** Intercept a single project endpoint. */
export async function mockProject(page: Page, project = MOCK_PROJECTS[0]) {
  await page.route(`**/api/v1/projects/${project.id}`, (route) =>
    json(route, project)
  );
  await page.route(`**/api/v1/projects/${project.id}/stubs`, (route) =>
    json(route, [])
  );
}

/** Mock the ingestion upload endpoint. */
export async function mockUpload(
  page: Page,
  projectId: string,
  opts: { valid?: boolean; errors?: string[] } = {}
) {
  const valid = opts.valid ?? true;
  await page.route(
    `**/api/v1/projects/${projectId}/stubs/upload`,
    (route) => {
      if (valid) {
        return json(route, {
          valid: true,
          format_detected: "ca-lisa-http-pair",
          stub_id: "stub-001",
          errors: [],
          warnings: [],
          stub_count: 1,
          scenario_count: 1,
        });
      }
      return json(route, {
        valid: false,
        format_detected: null,
        stub_id: null,
        errors: opts.errors ?? ["File format not recognised."],
        warnings: [],
        stub_count: 0,
        scenario_count: 0,
      });
    }
  );

  await page.route(`**/api/v1/projects/${projectId}/generate`, (route) =>
    json(route, { job_id: "job-001" }, 202)
  );
}

/** Mock a job status endpoint. */
export async function mockJob(
  page: Page,
  jobId: string,
  status: "QUEUED" | "RUNNING" | "DONE" | "FAILED" = "DONE"
) {
  await page.route(`**/api/v1/jobs/${jobId}`, (route) =>
    json(route, {
      id: jobId,
      type: "GENERATE",
      status,
      project_id: "proj-001",
      stub_id: "stub-001",
      result: status === "DONE" ? { stub_id: "stub-001" } : null,
      error_message: status === "FAILED" ? "Build failed" : null,
      created_at: "2026-06-21T12:00:00Z",
      updated_at: "2026-06-21T12:01:00Z",
    })
  );
}

// ── login helper ──────────────────────────────────────────────────────────────

/**
 * Log in through the UI.  Mocks the auth API, fills the login form, submits,
 * and waits for the dashboard to load.  The projects API is also mocked so the
 * dashboard renders successfully.
 */
export async function loginAs(
  page: Page,
  opts: { username?: string; password?: string; role?: string; projects?: typeof MOCK_PROJECTS } = {}
) {
  const username = opts.username ?? "admin";
  const password = opts.password ?? "password123";

  await mockAuth(page, { role: opts.role, username: opts.username });
  await mockProjects(page, opts.projects);

  await page.goto("/login");
  await page.fill("#username", username);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  // Wait until we've left /login (redirect to dashboard)
  await page.waitForURL((url) => !url.pathname.includes("login"), { timeout: 5_000 });
}
