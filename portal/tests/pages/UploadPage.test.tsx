import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { UploadPage } from "@/pages/UploadPage";
import { useAuthStore } from "@/store/auth";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderUpload(projectId = "proj-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        { initialEntries: [`/projects/${projectId}/upload`] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: "/projects/:projectId/upload", element: createElement(UploadPage) }),
        ),
      ),
    ),
  );
}

beforeEach(() => {
  useAuthStore.getState().login("tok", { username: "u", role: "SV_TEAM" });
  vi.resetAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.getState().logout();
});

describe("UploadPage", () => {
  it("renders stub name input and upload zone", () => {
    renderUpload();
    expect(screen.getByLabelText(/stub name/i)).toBeDefined();
    expect(screen.getByTestId("upload-zone")).toBeDefined();
  });

  it("submit button is disabled when no file selected", () => {
    renderUpload();
    const btn = screen.getByRole("button", { name: /upload & generate/i });
    expect(btn).toBeDisabled();
  });

  it("shows validation errors returned from ingestion API", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ valid: false, errors: ["Missing response body on line 42"], stub_id: null, warnings: [], stub_count: 0, scenario_count: 0, format_detected: null }),
        { status: 200 },
      ),
    );

    renderUpload();

    const input = screen.getByTestId("file-input");
    const file = new File(["data"], "spec.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    fireEvent.click(screen.getByRole("button", { name: /upload & generate/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText(/missing response body/i)).toBeDefined();
    });
  });

  it("navigates to job status page on successful upload and generate", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ valid: true, stub_id: "stub-abc", errors: [], warnings: [], stub_count: 3, scenario_count: 5, format_detected: "level-1-txt" }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ job_id: "job-xyz", status: "QUEUED", type: "PARSE" }),
          { status: 202 },
        ),
      );

    renderUpload();

    const input = screen.getByTestId("file-input");
    const file = new File(["data"], "spec.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    fireEvent.click(screen.getByRole("button", { name: /upload & generate/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        expect.stringContaining("/jobs/job-xyz"),
      );
    });
  });
});
