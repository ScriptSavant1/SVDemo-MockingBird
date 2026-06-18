import { clsx } from "clsx";
import type { DeploymentStatus, StubStatus } from "@/api/types";

type AnyStatus = StubStatus | DeploymentStatus;

const colourMap: Record<AnyStatus, string> = {
  DRAFT: "bg-gray-100 text-gray-700",
  READY: "bg-blue-100 text-blue-700",
  PENDING: "bg-yellow-100 text-yellow-700",
  DEPLOYING: "bg-yellow-100 text-yellow-700",
  BUILDING: "bg-yellow-100 text-yellow-700",
  PROVISIONING: "bg-yellow-100 text-yellow-700",
  LIVE: "bg-green-100 text-green-700",
  SUSPENDED: "bg-orange-100 text-orange-700",
  FAILED: "bg-red-100 text-red-700",
  ARCHIVED: "bg-gray-100 text-gray-500",
};

interface StatusBadgeProps {
  status: AnyStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        colourMap[status] ?? "bg-gray-100 text-gray-700",
        className,
      )}
      data-testid="status-badge"
      data-status={status}
    >
      {status}
    </span>
  );
}
