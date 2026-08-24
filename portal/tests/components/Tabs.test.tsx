import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { Tabs } from "@/components/ui/Tabs";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "history", label: "History" },
  { id: "reports", label: "Reports" },
];

describe("Tabs", () => {
  it("renders all tab labels", () => {
    render(createElement(Tabs, { tabs: TABS, active: "overview", onChange: vi.fn() }));
    expect(screen.getByRole("tab", { name: "Overview" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "History" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "Reports" })).toBeDefined();
  });

  it("marks the active tab with aria-selected=true", () => {
    render(createElement(Tabs, { tabs: TABS, active: "history", onChange: vi.fn() }));
    const historyTab = screen.getByRole("tab", { name: "History" });
    expect(historyTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected")).toBe("false");
  });

  it("calls onChange with the tab id when clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(createElement(Tabs, { tabs: TABS, active: "overview", onChange }));
    await user.click(screen.getByRole("tab", { name: "Reports" }));
    expect(onChange).toHaveBeenCalledWith("reports");
  });

  it("does not call onChange when the already-active tab is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(createElement(Tabs, { tabs: TABS, active: "overview", onChange }));
    await user.click(screen.getByRole("tab", { name: "Overview" }));
    // Radix Tabs only fires onValueChange on an actual value change — clicking
    // the tab that's already active is a no-op, matching <select>-style
    // onChange semantics elsewhere in the app.
    expect(onChange).not.toHaveBeenCalled();
  });
});
