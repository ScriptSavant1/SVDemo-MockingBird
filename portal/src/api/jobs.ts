import { api } from "./client";
import type { JobOut } from "./types";

export const jobsApi = {
  get: (jobId: string) => api.get<JobOut>(`/api/v1/jobs/${jobId}`),
};
