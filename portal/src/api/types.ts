export type ProjectStatus =
  | "DRAFT"
  | "READY"
  | "DEPLOYING"
  | "LIVE"
  | "SUSPENDED"
  | "ARCHIVED";
export type StubStatus = "DRAFT" | "READY" | "DEPLOYING" | "LIVE" | "SUSPENDED" | "FAILED";
export type DeploymentStatus = "PENDING" | "BUILDING" | "PROVISIONING" | "LIVE" | "SUSPENDED" | "FAILED";
export type JobStatus = "QUEUED" | "RUNNING" | "DONE" | "FAILED";
export type UserRole = "ADMIN" | "SV_TEAM" | "PROJECT_OWNER" | "VIEWER";

export interface Project {
  id: string;
  name: string;
  team: string;
  environment: string;
  expected_tps: number;
  description: string | null;
  status: ProjectStatus;
  stub_url: string | null;
  api_key: string | null;
  created_by: string;
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

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface UserPage {
  items: User[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditLogEntry {
  id: string;
  project_id: string | null;
  user_id: string | null;
  username: string | null;
  action: string;
  detail: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}
