import { useAuthStore } from "@/store/auth";
import { ApiError } from "@/api/client";
import type { IngestionResult } from "./types";

export async function uploadSpec(
  projectId: string,
  stubName: string,
  file: File,
): Promise<IngestionResult> {
  const token = useAuthStore.getState().token;
  const form = new FormData();
  form.append("stub_name", stubName);
  form.append("file", file);

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

export const ingestionApi = { uploadSpec, downloadWiremockZip };
