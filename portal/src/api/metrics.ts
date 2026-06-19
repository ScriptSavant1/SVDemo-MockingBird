import { api } from "./client";
import type { MetricHistoryResponse } from "./types";

export const metricsApi = {
  history: (deploymentId: string, minutes: number = 60) =>
    api.get<MetricHistoryResponse>(
      `/api/v1/metrics/${deploymentId}/history?minutes=${minutes}`,
    ),
};
