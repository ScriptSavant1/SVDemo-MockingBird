import { api } from "./client";
import type { Project, Stub, Deployment } from "./types";

export interface CreateProjectBody {
  name: string;
  description: string;
}

export const projectsApi = {
  list: () => api.get<Project[]>("/api/v1/projects"),
  get: (id: string) => api.get<Project>(`/api/v1/projects/${id}`),
  create: (body: CreateProjectBody) => api.post<Project>("/api/v1/projects", body),

  listStubs: (projectId: string) =>
    api.get<Stub[]>(`/api/v1/projects/${projectId}/stubs`),

  listDeployments: (projectId: string) =>
    api.get<Deployment[]>(`/api/v1/projects/${projectId}/deployments`),

  generate: (projectId: string, stubId: string) =>
    api.post<{ job_id: string; status: string; type: string }>(
      `/api/v1/projects/${projectId}/stubs/${stubId}/generate`,
    ),

  deploy: (projectId: string, stubId: string) =>
    api.post<{ deployment_id: string; job_id: string }>(
      `/api/v1/projects/${projectId}/stubs/${stubId}/deploy`,
    ),

  suspend: (projectId: string, deploymentId: string) =>
    api.post<void>(`/api/v1/projects/${projectId}/deployments/${deploymentId}/suspend`),

  redeploy: (projectId: string, deploymentId: string) =>
    api.post<{ deployment_id: string; job_id: string }>(
      `/api/v1/projects/${projectId}/deployments/${deploymentId}/redeploy`,
    ),

  requestReport: (projectId: string, deploymentId: string) =>
    api.post<{ deployment_id: string; job_id: string; status: string }>(
      `/api/v1/projects/${projectId}/deployments/${deploymentId}/report`,
    ),
};
