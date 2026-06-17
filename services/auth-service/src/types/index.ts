/**
 * Shared TypeScript types for auth-service.
 */

export type UserRole = "ADMIN" | "SV_TEAM" | "PROJECT_OWNER" | "VIEWER";

export interface UserRow {
  id: string;
  username: string;
  email: string;
  password_hash: string;
  role: UserRole;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
}

export interface JwtPayload {
  sub: string;        // user UUID
  username: string;
  role: UserRole;
  iat?: number;
  exp?: number;
}

/** Request body for POST /api/v1/auth/login */
export interface LoginBody {
  username: string;
  password: string;
}

/** Request body for POST /api/v1/users */
export interface CreateUserBody {
  username: string;
  email: string;
  password: string;
  role?: UserRole;
}

/** Response body for user endpoints */
export interface UserOut {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

/** RFC 7807 Problem JSON */
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
}
