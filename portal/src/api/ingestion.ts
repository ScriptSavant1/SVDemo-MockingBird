import { useAuthStore } from "@/store/auth";
import { ApiError } from "@/api/client";
import type { IngestionResult, Protocol, TlsCertUploadResult } from "./types";

// Protocol/TLS is chosen at upload time — each stub is its own deployable
// unit (own Docker image + EC2 instance), so it's set per stub-upload
// request, not inherited from the project. All fields optional; omitting
// protocol defaults to HTTP server-side.
export interface UploadSpecTlsOptions {
  protocol?: Protocol;
  mtls_enabled?: boolean;
  server_cert?: File;
  server_key?: File;
  ca_bundle?: File;
}

export async function uploadSpec(
  projectId: string,
  stubName: string,
  file: File,
  tls?: UploadSpecTlsOptions,
): Promise<IngestionResult> {
  const token = useAuthStore.getState().token;
  const form = new FormData();
  form.append("stub_name", stubName);
  form.append("file", file);
  if (tls?.protocol) form.append("protocol", tls.protocol);
  if (tls?.mtls_enabled !== undefined) form.append("mtls_enabled", String(tls.mtls_enabled));
  if (tls?.server_cert) form.append("server_cert", tls.server_cert);
  if (tls?.server_key) form.append("server_key", tls.server_key);
  if (tls?.ca_bundle) form.append("ca_bundle", tls.ca_bundle);

  const res = await fetch(`/api/v1/projects/${projectId}/stubs/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<IngestionResult>;
}

export async function uploadTlsCert(
  projectId: string,
  stubId: string,
  files: { server_cert: File; server_key: File; ca_bundle?: File },
): Promise<TlsCertUploadResult> {
  const token = useAuthStore.getState().token;
  const form = new FormData();
  form.append("server_cert", files.server_cert);
  form.append("server_key", files.server_key);
  if (files.ca_bundle) {
    form.append("ca_bundle", files.ca_bundle);
  }

  const res = await fetch(`/api/v1/projects/${projectId}/stubs/${stubId}/tls-cert`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<TlsCertUploadResult>;
}

async function downloadWiremockZip(projectId: string, stubId: string): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const res = await fetch(
    `/api/v1/projects/${projectId}/stubs/${stubId}/wiremock.zip`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch { /* non-JSON */ }
    throw new ApiError(res.status, detail);
  }

  return res.blob();
}

async function downloadStubEngineZip(projectId: string, stubId: string): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const res = await fetch(
    `/api/v1/projects/${projectId}/stubs/${stubId}/stub-engine.zip`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch { /* non-JSON */ }
    throw new ApiError(res.status, detail);
  }

  return res.blob();
}

async function downloadJmeterZip(projectId: string, stubId: string): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const res = await fetch(
    `/api/v1/projects/${projectId}/stubs/${stubId}/nft-jmeter.zip`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch { /* non-JSON */ }
    throw new ApiError(res.status, detail);
  }

  return res.blob();
}

async function downloadNftScriptsZip(projectId: string, stubId: string): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const res = await fetch(
    `/api/v1/projects/${projectId}/stubs/${stubId}/nft-scripts.zip`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch { /* non-JSON */ }
    throw new ApiError(res.status, detail);
  }

  return res.blob();
}

export const ingestionApi = {
  uploadSpec,
  uploadTlsCert,
  downloadWiremockZip,
  downloadStubEngineZip,
  downloadJmeterZip,
  downloadNftScriptsZip,
};
