import { api } from "./client";
import type { AuditLogPage, User, UserPage } from "./types";

export interface CreateUserBody {
  username: string;
  email: string;
  password: string;
  role: string;
}

export interface PatchUserBody {
  role?: string;
  is_active?: boolean;
}

export const adminApi = {
  listUsers: (limit = 50, offset = 0) =>
    api.get<UserPage>(`/api/v1/admin/users?limit=${limit}&offset=${offset}`),

  createUser: (body: CreateUserBody) =>
    api.post<User>("/api/v1/admin/users", body),

  patchUser: (userId: string, body: PatchUserBody) =>
    api.patch<User>(`/api/v1/admin/users/${userId}`, body),

  resetPassword: (userId: string, newPassword: string) =>
    api.post<void>(`/api/v1/admin/users/${userId}/reset-password`, {
      new_password: newPassword,
    }),

  listAudit: (limit = 50, offset = 0, projectId?: string) => {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (projectId) qs.set("project_id", projectId);
    return api.get<AuditLogPage>(`/api/v1/admin/audit?${qs.toString()}`);
  },
};
