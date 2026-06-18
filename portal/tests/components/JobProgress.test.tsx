import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { JobProgress, buildJobSteps } from "@/components/JobProgress";

describe("buildJobSteps", () => {
  it("returns 4 steps for a PARSE job", () => {
    const steps = buildJobSteps("QUEUED", "PARSE");
    expect(steps).toHaveLength(4);
  });

  it("first step is always done (file validated on upload)", () => {
    const steps = buildJobSteps("RUNNING", "PARSE");
    expect(steps[0].status).toBe("done");
  });

  it("second step is active when job is RUNNING", () => {
    const steps = buildJobSteps("RUNNING", "PARSE");
    expect(steps[1].status).toBe("active");
  });

  it("second step is done when job is DONE", () => {
    const steps = buildJobSteps("DONE", "PARSE");
    expect(steps[1].status).toBe("done");
  });

  it("third step is active when job is DONE (generating in background)", () => {
    const steps = buildJobSteps("DONE", "PARSE");
    expect(steps[2].status).toBe("active");
  });

  it("third step is error when job is FAILED", () => {
    const steps = buildJobSteps("FAILED", "PARSE");
    expect(steps[2].status).toBe("error");
  });
});

describe("JobProgress component", () => {
  it("renders all step labels", () => {
    const steps = buildJobSteps("RUNNING", "PARSE");
    render(<JobProgress steps={steps} />);
    expect(screen.getByText(/parsing spec/i)).toBeDefined();
    expect(screen.getByText(/file validated/i)).toBeDefined();
  });

  it("shows step description for active step", () => {
    const steps = buildJobSteps("RUNNING", "PARSE");
    render(<JobProgress steps={steps} />);
    expect(screen.getByText(/extracting request/i)).toBeDefined();
  });
});
