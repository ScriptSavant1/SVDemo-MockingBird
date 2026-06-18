import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { AiGeneratePage } from "@/pages/AiGeneratePage";
import { useAuthStore } from "@/store/auth";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

const SAMPLE_COLLECTION = {
  info: {
    name: "Payment API",
    schema: "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
  },
  item: [],
};

const GENERATE_RESPONSE = {
  generation_id: "gen-123",
  detected_intent: "A REST API for processing card payments",
  suggested_stub_name: "Payment API",
  spec_format: "postman_v21",
  spec_content: JSON.stringify(SAMPLE_COLLECTION),
  estimated_stub_count: 3,
  model_used: "claude-sonnet-4-6",
  input_tokens: 200,
  output_tokens: 800,
  created_at: "2026-06-18T12:00:00Z",
};

function renderPage(projectId = "proj-1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        { initialEntries: [`/projects/${projectId}/ai-generate`] },
        createElement(
          Routes,
          null,
          createElement(Route, {
            path: "/projects/:projectId/ai-generate",
            element: createElement(AiGeneratePage),
          }),
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

describe("AiGeneratePage", () => {
  it("renders textarea and disabled generate button initially", () => {
    renderPage();
    expect(screen.getByTestId("description-input")).toBeDefined();
    expect(screen.getByTestId("generate-button")).toBeDisabled();
  });

  it("enables generate button when description is long enough", () => {
    renderPage();
    const textarea = screen.getByTestId("description-input");
    fireEvent.change(textarea, {
      target: { value: "A payment processing REST API with create and refund endpoints" },
    });
    expect(screen.getByTestId("generate-button")).not.toBeDisabled();
  });

  it("shows spec preview after successful generation", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(GENERATE_RESPONSE), { status: 201 }),
    );

    renderPage();

    fireEvent.change(screen.getByTestId("description-input"), {
      target: { value: "A payment processing REST API with create and refund endpoints" },
    });
    fireEvent.click(screen.getByTestId("generate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("spec-preview")).toBeDefined();
    });

    expect(screen.getByTestId("stub-name-input")).toBeDefined();
    const nameInput = screen.getByTestId("stub-name-input") as HTMLInputElement;
    expect(nameInput.value).toBe("Payment API");
  });

  it("shows rate-limit error on 429 response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Rate limit exceeded: max 10 AI generations per hour." }),
        { status: 429 },
      ),
    );

    renderPage();

    fireEvent.change(screen.getByTestId("description-input"), {
      target: { value: "A payment processing REST API with create and refund endpoints" },
    });
    fireEvent.click(screen.getByTestId("generate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toBeDefined();
    });
    expect(screen.getByTestId("error-message").textContent).toMatch(/rate limit/i);
  });
});
