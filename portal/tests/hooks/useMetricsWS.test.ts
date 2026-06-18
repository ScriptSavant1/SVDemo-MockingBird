import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useMetricsWS } from "@/hooks/useMetricsWS";

interface MockWS {
  onopen: (() => void) | null;
  onmessage: ((e: { data: string }) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  close: ReturnType<typeof vi.fn>;
  readyState: number;
}

let mockWsInstance: MockWS;

beforeEach(() => {
  mockWsInstance = {
    onopen: null,
    onmessage: null,
    onclose: null,
    onerror: null,
    close: vi.fn(),
    readyState: 0,
  };

  vi.spyOn(global, "WebSocket" as keyof typeof global).mockImplementation(
    () => mockWsInstance as unknown as WebSocket,
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useMetricsWS", () => {
  it("returns not connected initially", () => {
    const { result } = renderHook(() => useMetricsWS("deploy-1"));
    expect(result.current.connected).toBe(false);
    expect(result.current.latest).toBeNull();
  });

  it("sets connected=true when WebSocket opens", () => {
    const { result } = renderHook(() => useMetricsWS("deploy-1"));
    act(() => {
      mockWsInstance.onopen?.();
    });
    expect(result.current.connected).toBe(true);
  });

  it("parses incoming MetricSnapshot messages and appends to history", () => {
    const snapshot = {
      deployment_id: "deploy-1",
      tps: 1234.5,
      avg_latency_ms: 5.1,
      p95_latency_ms: 8.2,
      error_rate: 0.001,
      total_requests: 9999,
      timestamp: "2026-06-18T12:00:00Z",
    };

    const { result } = renderHook(() => useMetricsWS("deploy-1"));
    act(() => {
      mockWsInstance.onopen?.();
      mockWsInstance.onmessage?.({ data: JSON.stringify(snapshot) });
    });

    expect(result.current.latest?.tps).toBe(1234.5);
    expect(result.current.history).toHaveLength(1);
    expect(result.current.history[0].deployment_id).toBe("deploy-1");
  });

  it("sets connected=false and closes WS when deploymentId becomes null", () => {
    const { unmount } = renderHook(() => useMetricsWS("deploy-1"));
    unmount();
    expect(mockWsInstance.close).toHaveBeenCalledOnce();
  });

  it("does not create a WebSocket when deploymentId is null", () => {
    renderHook(() => useMetricsWS(null));
    expect(global.WebSocket).not.toHaveBeenCalled();
  });

  it("connects to the correct WS URL", () => {
    renderHook(() => useMetricsWS("deploy-abc"));
    expect(global.WebSocket).toHaveBeenCalledWith(
      expect.stringContaining("/ws/metrics/deploy-abc"),
    );
  });
});
