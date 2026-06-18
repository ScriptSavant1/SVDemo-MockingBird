import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useAuthStore } from "@/store/auth";

const MOCK_TOKEN = "test-jwt-token";

beforeEach(() => {
  useAuthStore.getState().logout();
  vi.resetAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("injects Authorization header when token is set", async () => {
    useAuthStore.getState().login(MOCK_TOKEN, { username: "u", role: "SV_TEAM" });

    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "1" }), { status: 200 }),
    );

    const { api } = await import("@/api/client");
    await api.get("/api/v1/projects");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe(`Bearer ${MOCK_TOKEN}`);
  });

  it("does NOT inject Authorization header when logged out", async () => {
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify([]), { status: 200 }),
    );

    const { api } = await import("@/api/client");
    await api.get("/api/v1/projects");

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBeUndefined();
  });

  it("throws ApiError with status and detail on non-OK response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Not found", title: "Not Found" }), { status: 404 }),
    );

    const { api, ApiError } = await import("@/api/client");
    await expect(api.get("/api/v1/projects/missing")).rejects.toBeInstanceOf(ApiError);
  });

  it("calls logout and throws on 401 response", async () => {
    useAuthStore.getState().login(MOCK_TOKEN, { username: "u", role: "SV_TEAM" });

    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("", { status: 401 }),
    );

    const { api } = await import("@/api/client");
    await expect(api.get("/api/v1/projects")).rejects.toThrow();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
