import { api } from "./client";
import type {
  DownloadUrlOut,
  Project,
  ProjectPage,
  ReportJob,
  Stub,
  Deployment,
  Protocol,
  TlsCertSource,
} from "./types";

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

// Stub-scoped TLS/protocol config — set at upload time and editable afterward
// per stub (each stub is deployed as its own Docker image + EC2 instance, so
// different stubs in the same project can legitimately want different
// protocols). All fields optional: send only what changed.
export interface UpdateStubTlsConfigBody {
  protocol?: Protocol;
  mtls_enabled?: boolean;
  tls_cert_source?: TlsCertSource;
  tls_cert_s3_key?: string;
  tls_key_s3_key?: string;
  tls_ca_bundle_s3_key?: string;
}

export const projectsApi = {
  list: () => api.get<ProjectPage>("/api/v1/projects").then((page) => page.items),
  get: (id: string) => api.get<Project>(`/api/v1/projects/${id}`),
  create: (body: CreateProjectBody) => api.post<Project>("/api/v1/projects", body),
  update: (id: string, body: UpdateProjectBody) =>
    api.put<Project>(`/api/v1/projects/${id}`, body),
  archive: (id: string) =>
    api.put<Project>(`/api/v1/projects/${id}`, { status: "ARCHIVED" }),
  // Permanent, ADMIN-only, backend cascade-deletes stubs/deployments/jobs.
  // The audit trail survives (see project-service AuditLog.project_id).
  delete: (id: string) => api.delete<void>(`/api/v1/projects/${id}`),

  listStubs: (projectId: string) =>
    api.get<Stub[]>(`/api/v1/projects/${projectId}/stubs`),

  // Permanent, SV_TEAM/ADMIN-only. Callers must ensure the stub isn't
  // LIVE/DEPLOYING first — the backend doesn't auto-suspend an active
  // deployment before deleting.
  deleteStub: (projectId: string, stubId: string) =>
    api.delete<void>(`/api/v1/projects/${projectId}/stubs/${stubId}`),

  updateStubTlsConfig: (projectId: string, stubId: string, body: UpdateStubTlsConfigBody) =>
    api.put<Stub>(`/api/v1/projects/${projectId}/stubs/${stubId}/tls-config`, body),

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
