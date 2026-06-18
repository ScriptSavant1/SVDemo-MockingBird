import { api } from "./client";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  username: string;
  role: string;
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return api.post<LoginResponse>("/api/v1/auth/login", { username, password });
}

export function logout(): Promise<void> {
  return api.post<void>("/api/v1/auth/logout");
}
