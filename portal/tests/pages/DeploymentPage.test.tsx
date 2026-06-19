import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { DeploymentPage } from "@/pages/DeploymentPage";
import { useAuthStore } from "@/store/auth";

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => vi.fn() };
});

const STUB_ID = "stub-abc";
const DEPLOYMENT_ID = "dep-123";
const PROJECT_ID = "proj-1";

const LIVE_DEPLOYMENT = {
  id: DEPLOYMENT_ID,
  stub_id: STUB_ID,
  project_id: PROJECT_ID,
  status: "LIVE",
  stub_url: "https://stub.internal:8080",
  ec2_ip: null,
  ec2_instance_id: null,
  created_at: "2026-06-18T12:00:00Z",
  updated_at: "2026-06-18T12:00:00Z",
};

const DONE_REPORT_JOB = {
  id: "job-report-1",
  status: "DONE",
  result: {
    pdf_key: "stubs/proj/dep/report.pdf",
    excel_key: "stubs/proj/dep/report.xlsx",
    ppt_key: "stubs/proj/dep/report.pptx",
  },
  error_message: null,
  created_at: "2026-06-18T11:00:00Z",
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        { initialEntries: [`/projects/${PROJECT_ID}/stubs/${STUB_ID}`] },
        createElement(
          Routes,
          null,
          createElement(Route, {
            path: "/projects/:projectId/stubs/:stubId",
            element: createElement(DeploymentPage),
          }),
        ),
      ),
    ),
  );
}

beforeEach(() => {
  useAuthStore.getState().login("tok", { username: "u", role: "SV_TEAM" });
  vi.stubGlobal("WebSocket", class {
    onopen: (() => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    close() {}
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  useAuthStore.getState().logout();
});

describe("DeploymentPage", () => {
  it("renders Overview tab by default and shows stub URL", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify([LIVE_DEPLOYMENT]), { status: 200 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Overview" })).toBeDefined();
    });
    expect(screen.getByRole("tab", { name: "Metrics History" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "Reports" })).toBeDefined();
    expect(screen.getByText("https://stub.internal:8080")).toBeDefined();
  });

  it("switches to Reports tab when clicked", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([LIVE_DEPLOYMENT]), { status: 200 }))
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));

    renderPage();

    await waitFor(() => screen.getByRole("tab", { name: "Reports" }));
    fireEvent.click(screen.getByRole("tab", { name: "Reports" }));

    await waitFor(() => {
      expect(screen.getByTestId("generate-report-button")).toBeDefined();
    });
  });

  it("shows report job list with download buttons when reports exist", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([LIVE_DEPLOYMENT]), { status: 200 }))
      .mockResolvedValue(new Response(JSON.stringify([DONE_REPORT_JOB]), { status: 200 }));

    renderPage();

    await waitFor(() => screen.getByRole("tab", { name: "Reports" }));
    fireEvent.click(screen.getByRole("tab", { name: "Reports" }));

    await waitFor(() => {
      expect(screen.getByTestId("reports-table")).toBeDefined();
    });
    expect(screen.getByTestId(`download-pdf-${DONE_REPORT_JOB.id}`)).toBeDefined();
    expect(screen.getByTestId(`download-excel-${DONE_REPORT_JOB.id}`)).toBeDefined();
    expect(screen.getByTestId(`download-ppt-${DONE_REPORT_JOB.id}`)).toBeDefined();
  });

  it("shows empty state when no reports exist", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([LIVE_DEPLOYMENT]), { status: 200 }))
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));

    renderPage();

    await waitFor(() => screen.getByRole("tab", { name: "Reports" }));
    fireEvent.click(screen.getByRole("tab", { name: "Reports" }));

    await waitFor(() => {
      expect(screen.getByText(/no reports yet/i)).toBeDefined();
    });
  });

  it("switches to Metrics History tab and shows range buttons", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify([LIVE_DEPLOYMENT]), { status: 200 }),
    );

    renderPage();

    await waitFor(() => screen.getByRole("tab", { name: "Metrics History" }));
    fireEvent.click(screen.getByRole("tab", { name: "Metrics History" }));

    await waitFor(() => {
      expect(screen.getByTestId("range-1h")).toBeDefined();
      expect(screen.getByTestId("range-6h")).toBeDefined();
      expect(screen.getByTestId("range-24h")).toBeDefined();
    });
  });
});
