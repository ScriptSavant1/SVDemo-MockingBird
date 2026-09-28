import { useAuthStore } from "@/store/auth";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly title: string = "Request failed",
    /** Mockingbird error code, e.g. "MB-UPL-002" — see docs/ERROR_CODES.md. */
    public readonly code?: string,
    /** Server-log reference, only on unexpected (5xx) errors. */
    public readonly ref?: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }

  /** The one line to show the user: "MB-UPL-002 · Upload is 60 MB — the limit is 50 MB". */
  get userMessage(): string {
    return this.code ? `${this.code} · ${this.detail}` : this.detail;
  }
}

export const NETWORK_ERROR_CODE = "MB-NET-001";
export const NO_DETAIL_ERROR_CODE = "MB-NET-002";

interface ProblemBody {
  detail?: unknown;
  title?: unknown;
  code?: unknown;
  ref?: unknown;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

/**
 * Turn any non-2xx response into an ApiError with one readable line.
 * Handles the backend's Problem JSON ({code, detail, ref}), older bodies
 * whose `detail` is itself an object (would otherwise show as
 * "[object Object]"), and bodies with no JSON at all (e.g. a bare
 * "Internal Server Error" from a crashed or restarting service).
 */
export async function apiErrorFromResponse(res: Response, fallbackDetail?: string): Promise<ApiError> {
  let body: ProblemBody | undefined;
  try {
    body = (await res.json()) as ProblemBody;
  } catch {
    body = undefined;
  }

  const nested = body && typeof body.detail === "object" && body.detail !== null ? (body.detail as ProblemBody) : undefined;
  const detail = asString(body?.detail) ?? asString(nested?.detail) ?? asString(nested?.title);
  const title = asString(body?.title) ?? asString(nested?.title) ?? "Request failed";
  const code = asString(body?.code) ?? asString(nested?.code);
  const ref = asString(body?.ref);

  if (detail) return new ApiError(res.status, detail, title, code, ref);
  if (fallbackDetail) return new ApiError(res.status, fallbackDetail, title, code, ref);
  if (res.status >= 500) {
    return new ApiError(
      res.status,
      `The server returned HTTP ${res.status} with no details — the service may be down or restarting`,
      "Server error",
      NO_DETAIL_ERROR_CODE,
    );
  }
  return new ApiError(res.status, `Request failed (HTTP ${res.status})`, title, code);
}

/** fetch(), but a connection failure becomes an ApiError instead of a bare "Failed to fetch". */
export async function fetchOrNetworkError(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw new ApiError(
      0,
      "Can't reach the Mockingbird server — check your connection and that the services are running",
      "Network error",
      NETWORK_ERROR_CODE,
    );
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetchOrNetworkError(path, { ...init, headers });

  if (res.status === 401) {
    // Only treat as "session expired" if a token was already present (i.e., we were
    // authenticated). On the login endpoint there is no token yet, so read the body.
    const hasToken = !!useAuthStore.getState().token;
    if (hasToken) {
      useAuthStore.getState().logout();
      throw new ApiError(401, "Session expired — please log in again", "Unauthorised");
    }
    throw await apiErrorFromResponse(res, "Invalid username or password");
  }

  if (!res.ok) {
    throw await apiErrorFromResponse(res);
  }

  const text = await res.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
