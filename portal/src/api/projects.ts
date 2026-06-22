import { api } from "./client";
import type { DownloadUrlOut, Project, ProjectPage, ReportJob, Stub, Deployment } from "./types";

export interface CreateProjectBody {
  name: string;
  team: string;
  environment: string;
  expected_tps: number;
  description?: string;
}

export interface UpdateProjectBody {
  name?: string;
  team?: string;
  environment?: string;
  expected_tps?: number;
  description?: string;
  status?: string;
}

export const projectsApi = {
  list: () => api.get<ProjectPage>("/api/v1/projects").then((page) => page.items),
  get: (id: string) => api.get<Project>(`/api/v1/projects/${id}`),
  create: (body: CreateProjectBody) => api.post<Project>("/api/v1/projects", body),
  update: (id: string, body: UpdateProjectBody) =>
    api.put<Project>(`/api/v1/projects/${id}`, body),
  archive: (id: string) =>
    api.put<Project>(`/api/v1/projects/${id}`, { status: "ARCHIVED" }),

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

  listReports: (projectId: string, deploymentId: string) =>
    api.get<ReportJob[]>(
      `/api/v1/projects/${projectId}/deployments/${deploymentId}/reports`,
    ),

  downloadReport: (jobId: string, format: "pdf" | "excel" | "ppt") =>
    api.get<DownloadUrlOut>(`/api/v1/jobs/${jobId}/download?format=${format}`),
};
