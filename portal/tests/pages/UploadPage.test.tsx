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

  describe("batch mode — combined (default): one stub for the whole batch", () => {
    it("zips every selected file into ONE upload, regardless of file count", async () => {
      // This is the regression case: 4 files from one client (2 request/response
      // pairs) must become exactly 1 stub, not 2 — the backend's ZIP-upload path
      // does the pairing server-side once the zip arrives.
      vi.spyOn(global, "fetch")
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ valid: true, stub_id: "stub-combined", errors: [], warnings: [], stub_count: 2, scenario_count: 2, format_detected: "ca-lisa-http-pair" }),
            { status: 200 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ job_id: "job-combined", status: "QUEUED", type: "GENERATE" }), { status: 202 }),
        );

      renderUpload();
      fireEvent.click(screen.getByTestId("mode-batch"));

      const input = screen.getByTestId("batch-file-input");
      const files = [
        new File(["a"], "CreateAdviserPOST_Request.txt", { type: "text/plain" }),
        new File(["b"], "CreateAdviserPost_Response.txt", { type: "text/plain" }),
        new File(["c"], "GetAdvisers_Request.txt", { type: "text/plain" }),
        new File(["d"], "GetAdvisersByID_Response.txt", { type: "text/plain" }),
      ];
      fireEvent.change(input, { target: { files } });

      fireEvent.click(screen.getByRole("button", { name: /upload & generate \(1 stub\)/i }));

      await waitFor(() => {
        expect(screen.getByText(/1 of 1 stub created successfully/i)).toBeDefined();
      });

      // Exactly ONE upload + one generate call, not four (or two) independent ones.
      expect(global.fetch).toHaveBeenCalledTimes(2);
      const uploadCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const uploadBody = uploadCall[1].body as FormData;
      const uploadedFile = uploadBody.get("file") as File;
      expect(uploadedFile.name).toBe("Combined Spec.zip");
      expect(uploadedFile.type).toBe("application/zip");
    });

    it("uses the entered stub name for the zip filename", async () => {
      vi.spyOn(global, "fetch")
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ valid: true, stub_id: "stub-x", errors: [], warnings: [], stub_count: 1, scenario_count: 1, format_detected: "ca-lisa-http-pair" }),
            { status: 200 },
          ),
        )
        .mockResolvedValueOnce(new Response(JSON.stringify({ job_id: "job-x", status: "QUEUED", type: "GENERATE" }), { status: 202 }));

      renderUpload();
      fireEvent.click(screen.getByTestId("mode-batch"));

      const input = screen.getByTestId("batch-file-input");
      fireEvent.change(input, { target: { files: [new File(["a"], "req.txt", { type: "text/plain" })] } });
      fireEvent.change(screen.getByLabelText(/stub name/i), { target: { value: "Wealth Adviser API" } });

      fireEvent.click(screen.getByRole("button", { name: /upload & generate \(1 stub\)/i }));

      await waitFor(() => {
        expect(screen.getByText(/1 of 1 stub created successfully/i)).toBeDefined();
      });

      const uploadCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const uploadBody = uploadCall[1].body as FormData;
      expect(uploadBody.get("stub_name")).toBe("Wealth Adviser API");
      expect((uploadBody.get("file") as File).name).toBe("Wealth Adviser API.zip");
    });
  });

  describe("batch mode — separate: one stub per file", () => {
    async function selectSeparateMode() {
      fireEvent.click(screen.getByTestId("mode-batch"));
      fireEvent.click(screen.getByLabelText(/one stub per file/i));
    }

    it("uploads one stub per file", async () => {
      vi.spyOn(global, "fetch")
        // file A: upload
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ valid: true, stub_id: "stub-a", errors: [], warnings: [], stub_count: 1, scenario_count: 1, format_detected: "level-1-txt" }),
            { status: 200 },
          ),
        )
        // file A: generate
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ job_id: "job-a", status: "QUEUED", type: "GENERATE" }), { status: 202 }),
        )
        // file B: upload — fails validation
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ valid: false, stub_id: null, errors: ["Bad format"], warnings: [], stub_count: 0, scenario_count: 0, format_detected: null }),
            { status: 200 },
          ),
        );

      renderUpload();
      await selectSeparateMode();
      expect(screen.getByTestId("batch-upload-zone")).toBeDefined();

      const input = screen.getByTestId("batch-file-input");
      const fileA = new File(["data-a"], "serviceA.txt", { type: "text/plain" });
      const fileB = new File(["data-b"], "serviceB.txt", { type: "text/plain" });
      fireEvent.change(input, { target: { files: [fileA, fileB] } });

      expect(screen.getByText("serviceA.txt")).toBeDefined();
      expect(screen.getByText("serviceB.txt")).toBeDefined();

      fireEvent.click(screen.getByRole("button", { name: /upload & generate \(2\)/i }));

      await waitFor(() => {
        expect(screen.getByText(/1 of 2 stubs created successfully, 1 failed/i)).toBeDefined();
      });

      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    it("auto-pairs CA LISA request/response halves into one combined upload per pair", async () => {
      vi.spyOn(global, "fetch")
        // one upload call for the merged pair
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ valid: true, stub_id: "stub-pair", errors: [], warnings: [], stub_count: 1, scenario_count: 1, format_detected: "ca-lisa-http-pair" }),
            { status: 200 },
          ),
        )
        // generate for that stub
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ job_id: "job-pair", status: "QUEUED", type: "GENERATE" }), { status: 202 }),
        );

      renderUpload();
      await selectSeparateMode();

      const input = screen.getByTestId("batch-file-input");
      const reqFile = new File(["req-body"], "Payments_Request_20260610_100059.txt", { type: "text/plain" });
      const respFile = new File(["resp-body"], "Payments_Response_20260610_100059.txt", { type: "text/plain" });
      fireEvent.change(input, { target: { files: [reqFile, respFile] } });

      // Preview shows the detected pair before submitting
      await waitFor(() => {
        expect(screen.getByTestId("batch-pairing-preview")).toBeDefined();
      });

      fireEvent.click(screen.getByRole("button", { name: /upload & generate \(1\)/i }));

      await waitFor(() => {
        expect(screen.getByText(/1 of 1 stub created successfully/i)).toBeDefined();
      });

      // Exactly one upload + one generate call — not two failed independent uploads
      expect(global.fetch).toHaveBeenCalledTimes(2);
      const uploadCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const uploadBody = uploadCall[1].body as FormData;
      const uploadedFile = uploadBody.get("file") as File;
      expect(uploadedFile.name).toContain("Payments_Request_20260610_100059");
      expect(uploadedFile.name).toContain("Payments_Response_20260610_100059");
      expect(uploadBody.get("stub_name")).toBe("Payments_Request_20260610_100059");
    });

    it("does not block remaining files when one file's generate call fails", async () => {
      vi.spyOn(global, "fetch")
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ valid: true, stub_id: "stub-a", errors: [], warnings: [], stub_count: 1, scenario_count: 1, format_detected: "level-1-txt" }),
            { status: 200 },
          ),
        )
        .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "boom" }), { status: 500 }));

      renderUpload();
      await selectSeparateMode();

      const input = screen.getByTestId("batch-file-input");
      const fileA = new File(["data-a"], "serviceA.txt", { type: "text/plain" });
      fireEvent.change(input, { target: { files: [fileA] } });

      fireEvent.click(screen.getByRole("button", { name: /upload & generate \(1\)/i }));

      await waitFor(() => {
        expect(screen.getByText(/0 of 1 stub created successfully, 1 failed/i)).toBeDefined();
      });
    });
  });
});
