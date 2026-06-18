import { describe, it, expect } from "vitest";
import { formatTps, formatLatency, formatDate, formatErrorRate, formatRequests } from "@/utils/formatters";

describe("formatTps", () => {
  it("formats integer TPS with no decimal places", () => {
    expect(formatTps(1000)).toBe("1,000");
  });

  it("formats fractional TPS to 1 decimal place", () => {
    expect(formatTps(12345.6)).toBe("12,345.6");
  });

  it("formats zero", () => {
    expect(formatTps(0)).toBe("0");
  });
});

describe("formatLatency", () => {
  it("formats latency with ms suffix and 2 decimal places", () => {
    expect(formatLatency(5.25)).toBe("5.25ms");
  });

  it("pads integer latency to 2 decimal places", () => {
    expect(formatLatency(10)).toBe("10.00ms");
  });
});

describe("formatErrorRate", () => {
  it("converts fraction to percentage", () => {
    expect(formatErrorRate(0.001)).toBe("0.10%");
  });

  it("formats zero as 0.00%", () => {
    expect(formatErrorRate(0)).toBe("0.00%");
  });
});

describe("formatRequests", () => {
  it("formats large numbers with commas", () => {
    expect(formatRequests(1234567)).toBe("1,234,567");
  });
});

describe("formatDate", () => {
  it("returns a non-empty string for a valid ISO date", () => {
    const result = formatDate("2026-06-18T12:00:00Z");
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(5);
    expect(result).toContain("2026");
  });
});
