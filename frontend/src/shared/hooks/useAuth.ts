import { create } from "zustand";

function defaultPermissionsForRole(role: string | null) {
  if (role === "platform_admin") return ["*"];
  if (role === "tenant_admin") {
    return [
      "inbound_orders.manage",
      "inbound_orders.import",
      "receiving.execute",
      "outbound_orders.manage",
      "picking.execute",
      "shipping.execute",
      "master_data.manage",
      "users.manage",
      "billing.manage",
      "planner.manage",
    ];
  }
  if (role === "operator") return ["receiving.execute", "picking.execute", "shipping.execute"];
  if (role === "client_viewer") return ["portal.view"];
  return [];
}

type TokenAuthPayload = {
  role?: string | null;
  tenant_id?: string | null;
  permissions?: string[];
};

function decodeTokenAuth(token: string | null): TokenAuthPayload | null {
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}

function readStoredPermissions() {
  try {
    const value = JSON.parse(localStorage.getItem("wms_permissions") || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function readInitialAuth() {
  const token = localStorage.getItem("wms_token");
  const tokenAuth = decodeTokenAuth(token);
  const role = tokenAuth?.role || localStorage.getItem("wms_role");
  const tenantId =
    tokenAuth && "tenant_id" in tokenAuth ? tokenAuth.tenant_id || null : localStorage.getItem("wms_tenant_id");
  const permissions =
    Array.isArray(tokenAuth?.permissions) && tokenAuth.permissions.length
      ? tokenAuth.permissions
      : readStoredPermissions();

  if (tokenAuth?.role) {
    localStorage.setItem("wms_role", tokenAuth.role);
    if (tokenAuth.tenant_id) localStorage.setItem("wms_tenant_id", tokenAuth.tenant_id);
    localStorage.setItem(
      "wms_permissions",
      JSON.stringify(permissions.length ? permissions : defaultPermissionsForRole(tokenAuth.role)),
    );
  }

  return {
    token,
    role,
    tenantId,
    jobTitle: localStorage.getItem("wms_job_title"),
    permissions: permissions.length ? permissions : defaultPermissionsForRole(role),
  };
}

interface AuthState {
  token: string | null;
  role: string | null;
  tenantId: string | null;
  jobTitle: string | null;
  permissions: string[];
  setAuth: (
    token: string,
    role: string,
    tenantId: string | null,
    jobTitle?: string | null,
    permissions?: string[],
  ) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  ...readInitialAuth(),
  setAuth: (token, role, tenantId, jobTitle = null, permissions = defaultPermissionsForRole(role)) => {
    localStorage.setItem("wms_token", token);
    localStorage.setItem("wms_role", role);
    if (tenantId) localStorage.setItem("wms_tenant_id", tenantId);
    if (jobTitle) localStorage.setItem("wms_job_title", jobTitle);
    else localStorage.removeItem("wms_job_title");
    localStorage.setItem("wms_permissions", JSON.stringify(permissions));
    set({ token, role, tenantId, jobTitle, permissions });
  },
  logout: () => {
    localStorage.removeItem("wms_token");
    localStorage.removeItem("wms_role");
    localStorage.removeItem("wms_tenant_id");
    localStorage.removeItem("wms_job_title");
    localStorage.removeItem("wms_permissions");
    set({ token: null, role: null, tenantId: null, jobTitle: null, permissions: [] });
  },
}));

export function defaultRouteForRole(role: string | null) {
  if (role === "platform_admin") return "/users";
  if (role === "client_viewer") return "/portal/dashboard";
  return "/dashboard";
}
