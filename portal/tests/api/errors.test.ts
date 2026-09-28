import { describe, it, expect, vi, afterEach } from "vitest";
import {
  ApiError,
  apiErrorFromResponse,
  fetchOrNetworkError,
  NETWORK_ERROR_CODE,
  NO_DETAIL_ERROR_CODE,
} from "@/api/client";

afterEach(() => {
  vi.restoreAllMocks();
});

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status });
}

describe("apiErrorFromResponse", () => {
  it("reads the backend's Problem JSON — code, detail and ref", async () => {
    const err = await apiErrorFromResponse(
      json({ type: "t", title: "Server error", status: 500, code: "MB-SYS-001", detail: "Unexpected error in ingestion-service (ref a1b2c3d4)", ref: "a1b2c3d4" }, 500),
    );
    expect(err.status).toBe(500);
    expect(err.code).toBe("MB-SYS-001");
    expect(err.ref).toBe("a1b2c3d4");
    expect(err.userMessage).toBe("MB-SYS-001 · Unexpected error in ingestion-service (ref a1b2c3d4)");
  });

  it("flattens an older body whose detail is an object (no more [object Object])", async () => {
    const err = await apiErrorFromResponse(
      json({ detail: { type: "t", title: "Stub Not Found", status: 404, detail: "Stub 1 does not exist" } }, 404),
    );
    expect(err.detail).toBe("Stub 1 does not exist");
    expect(err.title).toBe("Stub Not Found");
    expect(err.userMessage).toBe("Stub 1 does not exist");
  });

  it("explains a 5xx with no JSON body instead of showing a bare status", async () => {
    const err = await apiErrorFromResponse(new Response("Internal Server Error", { status: 500 }));
    expect(err.code).toBe(NO_DETAIL_ERROR_CODE);
    expect(err.userMessage).toBe(
      "MB-NET-002 · The server returned HTTP 500 with no details — the service may be down or restarting",
    );
  });

  it("gives a readable line for a 4xx with no body", async () => {
    const err = await apiErrorFromResponse(new Response("", { status: 404 }));
    expect(err.userMessage).toBe("Request failed (HTTP 404)");
  });

  it("uses the caller's fallback only when the body has no detail", async () => {
    const fallback = await apiErrorFromResponse(new Response("", { status: 401 }), "Invalid username or password");
    expect(fallback.detail).toBe("Invalid username or password");
    const fromBody = await apiErrorFromResponse(json({ detail: "Account locked" }, 401), "Invalid username or password");
    expect(fromBody.detail).toBe("Account locked");
  });

  it("userMessage is just the detail when there is no code", () => {
    expect(new ApiError(400, "Bad thing").userMessage).toBe("Bad thing");
  });
});

describe("fetchOrNetworkError", () => {
  it("turns a connection failure into a coded ApiError", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const err = await fetchOrNetworkError("/api/v1/projects").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe(NETWORK_ERROR_CODE);
    expect((err as ApiError).userMessage).toMatch(/^MB-NET-001 · Can't reach the Mockingbird server/);
  });

  it("passes a real response straight through, even an error status", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 503 }));
    const res = await fetchOrNetworkError("/x");
    expect(res.status).toBe(503);
  });
});
