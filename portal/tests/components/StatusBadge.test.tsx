import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "@/components/StatusBadge";

describe("StatusBadge", () => {
  it("renders LIVE with green classes", () => {
    render(<StatusBadge status="LIVE" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("LIVE");
    expect(badge.className).toContain("green");
    expect(badge).toHaveAttribute("data-status", "LIVE");
  });

  it("renders FAILED with red classes", () => {
    render(<StatusBadge status="FAILED" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("FAILED");
    expect(badge.className).toContain("red");
  });

  it("renders DEPLOYING with yellow classes", () => {
    render(<StatusBadge status="DEPLOYING" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("DEPLOYING");
    expect(badge.className).toContain("yellow");
  });

  it("renders SUSPENDED with orange classes", () => {
    render(<StatusBadge status="SUSPENDED" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("SUSPENDED");
    expect(badge.className).toContain("orange");
  });

  it("renders DRAFT with gray classes", () => {
    render(<StatusBadge status="DRAFT" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("DRAFT");
    expect(badge.className).toContain("gray");
  });
});
