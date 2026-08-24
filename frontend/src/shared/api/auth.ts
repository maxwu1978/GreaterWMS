/**
 * Typed API module for authentication and password recovery.
 */

import api from "./client";

export type LoginResponse = {
  access_token: string;
  role: string;
  tenant_id: string;
  job_title?: string | null;
  permissions?: string[];
} & Record<string, unknown>;

export function login(email: string, password: string): Promise<LoginResponse> {
  return api.post("/auth/login", { email, password }).then((r) => r.data);
}

export function requestPasswordReset(email: string): Promise<any> {
  return api.post("/auth/forgot-password", { email }).then((r) => r.data);
}

export function validatePasswordResetToken(token: string): Promise<any> {
  return api.get("/auth/reset-password/validate", { params: { token } }).then((r) => r.data);
}

export function resetPassword(token: string, newPassword: string) {
  return api.post("/auth/reset-password", { token, new_password: newPassword });
}
