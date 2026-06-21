import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { loginAs, mockProject, mockUpload, mockJob, MOCK_PROJECTS } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ID = MOCK_PROJECTS[0].id; // "proj-001"

// Path to a real CA LISA sample file in the repo
const ESP_REQUEST = path.resolve(
  __dirname,
  "../../Sample_SV_Files/ESP/1781082059482RTCAERv01_Request_20260610_100059.txt"
);
const ESP_RESPONSE = path.resolve(
  __dirname,
  "../../Sample_SV_Files/ESP/1781082059500RTCAERv01_Success1Response_20260610_100059.txt"
);

test.describe("Upload Spec File", () => {
  test.beforeEach(async ({ page }) => {
    await mockProject(page, MOCK_PROJECTS[0]);
    await loginAs(page);
  });

  test("upload page renders correctly", async ({ page }) => {
    await page.goto(`/projects/${PROJECT_ID}/upload`);

    await expect(page.getByRole("heading", { name: "Upload Spec File" })).toBeVisible();
    await expect(page.getByText("Back to project")).toBeVisible();
    await expect(page.getByRole("button", { name: /upload & generate/i })).toBeDisabled();
  });

  test("upload & generate button enabled after file selected", async ({ page }) => {
    await mockUpload(page, PROJECT_ID);

    await page.goto(`/projects/${PROJECT_ID}/upload`);

    // Find the hidden file input inside UploadZone and set a file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(ESP_REQUEST);

    const submitBtn = page.getByRole("button", { name: /upload & generate/i });
    await expect(submitBtn).toBeEnabled();
  });

  test("successful upload starts job and redirects to job status", async ({ page }) => {
    await mockUpload(page, PROJECT_ID, { valid: true });
    await mockJob(page, "job-001", "DONE");

    // Mock the generate endpoint
    await page.route(`**/api/v1/projects/${PROJECT_ID}/stubs/*/generate`, (route) =>
      route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ job_id: "job-001", status: "QUEUED", type: "GENERATE" }),
      })
    );

    await page.goto(`/projects/${PROJECT_ID}/upload`);

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(ESP_REQUEST);

    await page.getByRole("button", { name: /upload & generate/i }).click();

    // Should redirect to job status page
    await expect(page).toHaveURL(/\/jobs\/job-001/);
  });

  test("shows validation errors when file format is rejected", async ({ page }) => {
    await mockUpload(page, PROJECT_ID, {
      valid: false,
      errors: ["File format not recognised. Supported formats: CA LISA HTTP capture (.txt pair or .zip)."],
    });

    await page.goto(`/projects/${PROJECT_ID}/upload`);

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(ESP_REQUEST);

    await page.getByRole("button", { name: /upload & generate/i }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByText("Validation failed")).toBeVisible();
    await expect(page.getByText("File format not recognised")).toBeVisible();
  });

  test("stub name field can be filled", async ({ page }) => {
    await page.goto(`/projects/${PROJECT_ID}/upload`);

    const nameInput = page.getByPlaceholder("e.g. Payment API stub");
    await nameInput.fill("My ESP Stub");
    await expect(nameInput).toHaveValue("My ESP Stub");
  });

  test("cancel navigates back to project page", async ({ page }) => {
    await page.goto(`/projects/${PROJECT_ID}/upload`);

    await page.getByRole("button", { name: /cancel/i }).click();
    await expect(page).toHaveURL(`/projects/${PROJECT_ID}`);
  });

  test("upload with CA LISA ESP combined file (request + response)", async ({ page }) => {
    await mockUpload(page, PROJECT_ID, { valid: true });
    await mockJob(page, "job-001", "DONE");

    await page.route(`**/api/v1/projects/${PROJECT_ID}/stubs/*/generate`, (route) =>
      route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ job_id: "job-001", status: "QUEUED", type: "GENERATE" }),
      })
    );

    await page.goto(`/projects/${PROJECT_ID}/upload`);

    // Name the stub explicitly
    await page.fill('[id="stub-name"]', "ESP Account Enquiry Stub");

    // Attach the request file (combined with response in a real scenario, but we're mocking the API)
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(ESP_REQUEST);

    await page.getByRole("button", { name: /upload & generate/i }).click();

    await expect(page).toHaveURL(/\/jobs\/job-001/);
  });
});
