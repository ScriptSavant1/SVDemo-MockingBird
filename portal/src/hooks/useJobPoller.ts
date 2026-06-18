import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "@/api/jobs";
import type { JobOut } from "@/api/types";

const TERMINAL: Set<string> = new Set(["DONE", "FAILED"]);

export function useJobPoller(jobId: string | null) {
  return useQuery<JobOut>({
    queryKey: ["job", jobId],
    queryFn: () => jobsApi.get(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL.has(status) ? false : 2000;
    },
  });
}
