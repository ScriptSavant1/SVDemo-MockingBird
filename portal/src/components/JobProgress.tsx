import { clsx } from "clsx";
import type { JobStatus } from "@/api/types";

export interface ProgressStep {
  label: string;
  description: string;
  status: "pending" | "active" | "done" | "error";
}

interface JobProgressProps {
  steps: ProgressStep[];
}

export function JobProgress({ steps }: JobProgressProps) {
  return (
    <ol className="space-y-4">
      {steps.map((step, i) => (
        <li key={i} className="flex items-start gap-4">
          <StepIcon status={step.status} index={i + 1} />
          <div className="min-w-0 flex-1 pt-0.5">
            <p
              className={clsx("text-sm font-medium", {
                "text-gray-900": step.status === "active" || step.status === "done",
                "text-gray-400": step.status === "pending",
                "text-red-600": step.status === "error",
              })}
            >
              {step.label}
            </p>
            {(step.status === "active" || step.status === "error") && (
              <p className="mt-0.5 text-xs text-gray-500">{step.description}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function StepIcon({ status, index }: { status: ProgressStep["status"]; index: number }) {
  const base = "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold";
  if (status === "done") {
    return <span className={clsx(base, "bg-green-100 text-green-700")}>✓</span>;
  }
  if (status === "active") {
    return (
      <span className={clsx(base, "bg-[#003875] text-white")}>
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
      </span>
    );
  }
  if (status === "error") {
    return <span className={clsx(base, "bg-red-100 text-red-600")}>✗</span>;
  }
  return <span className={clsx(base, "bg-gray-100 text-gray-400")}>{index}</span>;
}

export function buildJobSteps(jobStatus: JobStatus | undefined, jobType: string | undefined): ProgressStep[] {
  const isRunning = jobStatus === "RUNNING";
  const isDone = jobStatus === "DONE";
  const isFailed = jobStatus === "FAILED";

  if (jobType === "PARSE" || !jobType) {
    return [
      {
        label: "File validated",
        description: "Spec file uploaded and checked",
        status: "done",
      },
      {
        label: "Parsing spec file",
        description: "Extracting request/response pairs…",
        status: isRunning ? "active" : isDone || isFailed ? "done" : "pending",
      },
      {
        label: "Generating WireMock stubs",
        description: "Building Spring Boot stub configurations…",
        status: isDone ? "active" : isFailed ? "error" : "pending",
      },
      {
        label: "Ready to deploy",
        description: "Stub is ready — click Deploy from the project page",
        status: "pending",
      },
    ];
  }

  return [
    {
      label: jobType,
      description: "Processing…",
      status: isRunning ? "active" : isDone ? "done" : isFailed ? "error" : "pending",
    },
  ];
}
