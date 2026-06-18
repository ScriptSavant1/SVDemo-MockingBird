import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { useJobPoller } from "@/hooks/useJobPoller";
import type { JobOut } from "@/api/types";

function makeJob(status: JobOut["status"]): JobOut {
  return {
    id: "job-1",
    type: "PARSE",
    status,
    project_id: "proj-1",
    stub_id: "stub-1",
    result: null,
    error_message: null,
    created_at: "2026-06-18T12:00:00Z",
    updated_at: "2026-06-18T12:00:00Z",
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: qc }, children),
  };
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("useJobPoller", () => {
  it("returns undefined when jobId is null", () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useJobPoller(null), { wrapper });
    expect(result.current.data).toBeUndefined();
    expect(result.current.isPending).toBe(true);
  });

  it("fetches job and returns data", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(makeJob("RUNNING")), { status: 200 }),
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useJobPoller("job-1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("RUNNING");
    expect(result.current.data?.type).toBe("PARSE");
  });

  it("does not set refetchInterval when status is DONE", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(makeJob("DONE")), { status: 200 }),
    );
    const { wrapper, qc } = makeWrapper();
    const { result } = renderHook(() => useJobPoller("job-1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const query = qc.getQueryState(["job", "job-1"]);
    expect(query?.data?.status).toBe("DONE");
  });

  it("does not set refetchInterval when status is FAILED", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(makeJob("FAILED")), { status: 200 }),
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useJobPoller("job-1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("FAILED");
  });
});
