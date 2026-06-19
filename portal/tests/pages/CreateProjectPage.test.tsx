import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { CreateProjectPage } from "@/pages/CreateProjectPage";
import { useAuthStore } from "@/store/auth";

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => vi.fn() };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        { initialEntries: ["/projects/new"] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: "/projects/new", element: createElement(CreateProjectPage) }),
        ),
      ),
    ),
  );
}

beforeEach(() => {
  useAuthStore.getState().login("tok", { username: "u", role: "SV_TEAM" });
});

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.getState().logout();
});

describe("CreateProjectPage", () => {
  it("renders all form fields", () => {
    renderPage();
    expect(screen.getByTestId("name-input")).toBeDefined();
    expect(screen.getByTestId("team-input")).toBeDefined();
    expect(screen.getByTestId("environment-select")).toBeDefined();
    expect(screen.getByTestId("tps-input")).toBeDefined();
    expect(screen.getByTestId("description-textarea")).toBeDefined();
    expect(screen.getByTestId("create-submit-button")).toBeDefined();
  });

  it("shows validation errors when submitted empty", async () => {
    renderPage();
    fireEvent.click(screen.getByTestId("create-submit-button"));
    await waitFor(() => {
      expect(screen.getByText(/name is required/i)).toBeDefined();
      expect(screen.getByText(/team is required/i)).toBeDefined();
    });
  });

  it("calls projectsApi.create with correct payload on valid submit", async () => {
    const projectResponse = {
      id: "new-id",
      name: "Test Stub",
      team: "Core Banking",
      environment: "TEST",
      expected_tps: 5000,
      description: null,
      status: "DRAFT",
      stub_url: null,
      api_key: null,
      created_by: "user-1",
      created_at: "2026-06-19T00:00:00Z",
      updated_at: "2026-06-19T00:00:00Z",
    };
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(projectResponse), { status: 201 }),
    );

    renderPage();
    fireEvent.change(screen.getByTestId("name-input"), { target: { value: "Test Stub" } });
    fireEvent.change(screen.getByTestId("team-input"), { target: { value: "Core Banking" } });
    fireEvent.change(screen.getByTestId("tps-input"), { target: { value: "5000" } });
    fireEvent.click(screen.getByTestId("create-submit-button"));

    await waitFor(() => {
      const call = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(call[0]).toBe("/api/v1/projects");
      const body = JSON.parse(call[1].body as string);
      expect(body.name).toBe("Test Stub");
      expect(body.team).toBe("Core Banking");
      expect(body.expected_tps).toBe(5000);
    });
  });

  it("shows API error message on failure", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Name already exists" }), { status: 409 }),
    );

    renderPage();
    fireEvent.change(screen.getByTestId("name-input"), { target: { value: "Dupe" } });
    fireEvent.change(screen.getByTestId("team-input"), { target: { value: "Team" } });
    fireEvent.click(screen.getByTestId("create-submit-button"));

    await waitFor(() => {
      expect(screen.getByTestId("create-error")).toBeDefined();
      expect(screen.getByText(/name already exists/i)).toBeDefined();
    });
  });

  it("environment select defaults to TEST", () => {
    renderPage();
    const sel = screen.getByTestId("environment-select") as HTMLSelectElement;
    expect(sel.value).toBe("TEST");
  });
});
