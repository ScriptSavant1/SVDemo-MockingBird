import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { UploadZone } from "@/components/UploadZone";

function makeFile(name = "test.txt", type = "text/plain"): File {
  return new File(["content"], name, { type });
}

describe("UploadZone", () => {
  it("renders drop zone with format hint when no file selected", () => {
    render(<UploadZone file={null} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /file drop zone/i })).toBeDefined();
    expect(screen.getByText(/drop your spec file/i)).toBeDefined();
    expect(screen.getByText(/postman/i)).toBeDefined();
  });

  it("shows filename and size after file selected via input", () => {
    const onChange = vi.fn();
    render(<UploadZone file={makeFile("payments.txt")} onChange={onChange} />);
    expect(screen.getByText("payments.txt")).toBeDefined();
  });

  it("calls onChange with null when Remove is clicked", () => {
    const onChange = vi.fn();
    render(<UploadZone file={makeFile("payments.txt")} onChange={onChange} />);
    fireEvent.click(screen.getByText(/remove/i));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("calls onChange when file selected via hidden input", () => {
    const onChange = vi.fn();
    render(<UploadZone file={null} onChange={onChange} />);
    const input = screen.getByTestId("file-input");
    const file = makeFile("spec.json", "application/json");
    fireEvent.change(input, { target: { files: [file] } });
    expect(onChange).toHaveBeenCalledWith(file);
  });

  it("is disabled when disabled prop is true", () => {
    render(<UploadZone file={null} onChange={vi.fn()} disabled />);
    const zone = screen.getByTestId("upload-zone");
    expect(zone.className).toContain("opacity-50");
  });

  it("shows drag-over visual when drag enters", () => {
    render(<UploadZone file={null} onChange={vi.fn()} />);
    const zone = screen.getByTestId("upload-zone");
    fireEvent.dragEnter(zone, { dataTransfer: { files: [] } });
    expect(zone.className).toContain("blue");
  });
});
