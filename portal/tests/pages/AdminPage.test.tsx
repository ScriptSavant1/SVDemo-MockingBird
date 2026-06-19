import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { AdminPage } from "@/pages/AdminPage";
import { useAuthStore } from "@/store/auth";

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => vi.fn() };
});

const USERS_RESPONSE = {
  items: [
    {
      id: "user-1",
      username: "admin.user",
      email: "admin@company.com",
      role: "ADMIN",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "user-2",
      username: "sv.user",
      email: "sv@company.com",
      role: "SV_TEAM",
      is_active: false,
      created_at: "2026-02-01T00:00:00Z",
    },
  ],
  total: 2,
  limit: 50,
  offset: 0,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        { initialEntries: ["/admin"] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: "/admin", element: createElement(AdminPage) }),
        ),
      ),
    ),
  );
}

beforeEach(() => {
  useAuthStore.getState().login("tok", { username: "admin", role: "ADMIN" });
});

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.getState().logout();
});

describe("AdminPage — Users tab", () => {
  it("renders users table with rows", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(USERS_RESPONSE), { status: 200 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("users-table")).toBeDefined();
      expect(screen.getByText("admin.user")).toBeDefined();
      expect(screen.getByText("sv.user")).toBeDefined();
    });
  });

  it("shows New User button", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(USERS_RESPONSE), { status: 200 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("new-user-button")).toBeDefined();
    });
  });

  it("opens create user modal when New User clicked", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(USERS_RESPONSE), { status: 200 }),
    );

    renderPage();

    await waitFor(() => screen.getByTestId("new-user-button"));
    fireEvent.click(screen.getByTestId("new-user-button"));

    await waitFor(() => {
      expect(screen.getByTestId("create-user-form")).toBeDefined();
      expect(screen.getByTestId("new-user-username")).toBeDefined();
      expect(screen.getByTestId("new-user-email")).toBeDefined();
      expect(screen.getByTestId("new-user-password")).toBeDefined();
    });
  });

  it("shows reset password modal when button clicked", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(USERS_RESPONSE), { status: 200 }),
    );

    renderPage();

    await waitFor(() => screen.getByTestId(`reset-password-user-1`));
    fireEvent.click(screen.getByTestId("reset-password-user-1"));

    await waitFor(() => {
      expect(screen.getByTestId("reset-password-form")).toBeDefined();
      expect(screen.getByTestId("new-password-input")).toBeDefined();
    });
  });

  it("shows active/suspended badge based on is_active", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(USERS_RESPONSE), { status: 200 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("toggle-active-user-1").textContent).toBe("Active");
      expect(screen.getByTestId("toggle-active-user-2").textContent).toBe("Suspended");
    });
  });
});

describe("AdminPage — Audit Log tab", () => {
  it("switches to Audit Log tab and loads table", async () => {
    const auditResponse = {
      items: [
        {
          id: "audit-1",
          project_id: "proj-1",
          user_id: "user-1",
          username: "admin.user",
          action: "project.created",
          detail: { name: "My Stub" },
          ip_address: null,
          created_at: "2026-06-19T08:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    };

    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(USERS_RESPONSE), { status: 200 }))
      .mockResolvedValue(new Response(JSON.stringify(auditResponse), { status: 200 }));

    renderPage();

    await waitFor(() => screen.getByRole("tab", { name: "Audit Log" }));
    fireEvent.click(screen.getByRole("tab", { name: "Audit Log" }));

    await waitFor(() => {
      expect(screen.getByTestId("audit-table")).toBeDefined();
      expect(screen.getByText("project.created")).toBeDefined();
      expect(screen.getByText("admin.user")).toBeDefined();
    });
  });
});
