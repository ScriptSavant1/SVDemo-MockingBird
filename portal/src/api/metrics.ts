import { api } from "./client";
import type { MetricSnapshot } from "./types";

export interface MetricHistory {
  deployment_id: string;
  points: MetricSnapshot[];
}

export const metricsApi = {
  current: (deploymentId: string) =>
    api.get<MetricSnapshot>(`/api/v1/metrics/${deploymentId}/current`),
  history: (deploymentId: string) =>
    api.get<MetricHistory>(`/api/v1/metrics/${deploymentId}/history`),
};
