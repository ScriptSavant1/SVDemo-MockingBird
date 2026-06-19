export type ProjectStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";
export type StubStatus = "DRAFT" | "READY" | "DEPLOYING" | "LIVE" | "SUSPENDED" | "FAILED";
export type DeploymentStatus = "PENDING" | "BUILDING" | "PROVISIONING" | "LIVE" | "SUSPENDED" | "FAILED";
export type JobStatus = "QUEUED" | "RUNNING" | "DONE" | "FAILED";

export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

export interface Stub {
  id: string;
  project_id: string;
  name: string;
  description: string;
  status: StubStatus;
  stub_type: string;
  created_at: string;
  updated_at: string;
}

export interface Deployment {
  id: string;
  stub_id: string;
  project_id: string;
  status: DeploymentStatus;
  ec2_ip: string | null;
  stub_url: string | null;
  ec2_instance_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MetricSnapshot {
  deployment_id: string;
  tps: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  error_rate: number;
  total_requests: number;
  timestamp: string;
}

export interface ApiError {
  type: string;
  title: string;
  status: number;
  detail: string;
}

export interface IngestionResult {
  valid: boolean;
  format_detected: string | null;
  stub_id: string | null;
  errors: string[];
  warnings: string[];
  stub_count: number;
  scenario_count: number;
}

export interface JobOut {
  id: string;
  type: string;
  status: JobStatus;
  project_id: string | null;
  stub_id: string | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface MetricHistoryPoint {
  time: string;
  tps: number;
  latency_avg_ms: number;
  error_rate: number;
}

export interface MetricHistoryResponse {
  deployment_id: string;
  points: MetricHistoryPoint[];
  query_minutes: number;
}

export interface ReportJob {
  id: string;
  status: JobStatus;
  result: Record<string, string | null> | null;
  error_message: string | null;
  created_at: string;
}

export interface DownloadUrlOut {
  url: string;
  format: string;
  expires_in_seconds: number;
}
