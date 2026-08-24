/**
 * Typed API module for user and tenant administration.
 */

import api from "./client";

/** GET /users/?limit=500 — page object with `items`. */
export function fetchUsersPage(): Promise<any> {
  return api.get("/users/?limit=500").then((r) => r.data);
}

/** GET /tenants/ — raw body. */
export function fetchTenants(): Promise<any> {
  return api.get("/tenants/").then((r) => r.data);
}

export function createUser(payload: Record<string, unknown>) {
  return api.post("/users/", payload);
}

export function updateUser(userId: string, payload: Record<string, unknown>) {
  return api.put(`/users/${userId}`, payload);
}

export function resetUserPassword(userId: string, newPassword: string) {
  return api.post(`/users/${userId}/reset-password`, { new_password: newPassword });
}

export type UserCleanupPreview = {
  confirmation_required_for_write: boolean;
  confirmation_payload?: {
    confirmation_token: string;
    evidence_id: string;
  };
  summary: {
    delete_count: number;
    preserve_count: number;
    delete_by_role: Record<string, number>;
  };
  preserved: {
    count: number;
    roles: string[];
  };
  delete_candidates: {
    count: number;
    roles: string[];
  };
  blocking_errors: Array<{ code: string; message: string; count?: number }>;
  next_action: string;
};

export function previewNonAdminUserCleanup(): Promise<UserCleanupPreview> {
  return api.post("/users/cleanup/preview", { scope: "non_admin_users" }).then((r) => r.data);
}

export function confirmNonAdminUserCleanup(
  preview: UserCleanupPreview,
  idempotencyKey: string,
) {
  return api.post(
    "/users/cleanup/agent",
    {
      scope: "non_admin_users",
      confirmation_token: preview.confirmation_payload?.confirmation_token,
    },
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export type TenantApprovalItem = {
  id: string;
  name: string;
  code: string;
  contact_email: string;
  plan_tier: string;
  approval_status: string;
  created_at: string;
};

export function fetchTenantApprovals(status = "pending"): Promise<TenantApprovalItem[]> {
  return api
    .get("/tenants/approvals", { params: { approval_status: status } })
    .then((r) => r.data);
}

export function decideTenantApproval(tenantId: string, action: "approve" | "reject") {
  return api.post(`/tenants/${tenantId}/approval`, { action });
}
