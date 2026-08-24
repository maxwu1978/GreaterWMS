import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Archive,
  Building2,
  CheckCircle2,
  Filter,
  KeyRound,
  Pencil,
  Save,
  Search,
  Trash2,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import {
  createUser as createUserRequest,
  confirmNonAdminUserCleanup,
  fetchTenants,
  fetchUsersPage,
  previewNonAdminUserCleanup,
  resetUserPassword,
  UserCleanupPreview,
  updateUser,
} from "../../shared/api/users";
import { fetchClients } from "../../shared/api/clients";
import { queryKeys } from "../../shared/api/queryKeys";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import { useAuthStore } from "../../shared/hooks/useAuth";
import PasswordInput from "../../shared/components/PasswordInput";

type UserRow = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  job_title: string | null;
  permissions: string[];
  is_active: boolean;
  client_id: string | null;
  tenant_id?: string | null;
  tenant_name?: string | null;
};

type ClientRow = {
  id: string;
  tenant_id?: string | null;
  name: string;
  code: string;
};

type TenantRow = {
  id: string;
  name: string;
  code: string;
};

function isTestUser(user: UserRow) {
  const email = user.email.toLowerCase();
  const tenantName = (user.tenant_name || "").toLowerCase();
  if (email === "not-an-email") return true;
  if (email.endsWith("@example.com")) return true;
  if (email === "platform-admin-test@maxsmartwms.online") return true;
  if (tenantName.includes("mailersend smoke")) return true;
  if (tenantName.startsWith("accept ") || tenantName.startsWith("acceptance ")) return true;
  if (tenantName.startsWith("action first ")) return true;
  return false;
}

function createCleanupIdempotencyKey() {
  return `users-cleanup-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const TENANT_ADMIN_PERMISSION_KEYS = [
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

export default function UsersPage() {
  const { t } = useI18n();
  const role = useAuthStore((s) => s.role);
  const isPlatformAdmin = role === "platform_admin";
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [showDisabledUsers, setShowDisabledUsers] = useState(false);
  const [showTestUsers, setShowTestUsers] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    password: "",
    role: isPlatformAdmin ? "tenant_admin" : "operator",
    job_title: "",
    permissions: isPlatformAdmin ? TENANT_ADMIN_PERMISSION_KEYS : ["receiving.execute", "picking.execute", "shipping.execute"],
    client_id: "",
    tenant_id: "",
  });
  const [resetPasswordFor, setResetPasswordFor] = useState<string>("");
  const [newPassword, setNewPassword] = useState("");
  const [editingUserId, setEditingUserId] = useState("");
  const [editForm, setEditForm] = useState({
    full_name: "",
    job_title: "",
    role: "operator",
    permissions: [] as string[],
    client_id: "",
  });
  const [cleanupPreview, setCleanupPreview] = useState<UserCleanupPreview | null>(null);
  const [cleanupConfirmationText, setCleanupConfirmationText] = useState("");
  const [cleanupIdempotencyKey, setCleanupIdempotencyKey] = useState(createCleanupIdempotencyKey);
  const cleanupConfirmationPhrase = "DELETE NON-ADMIN USERS";

  const roleLabels: Record<string, string> = {
    platform_admin: t("users.rolePlatformAdmin", "Super Admin"),
    tenant_admin: t("users.roleTenantAdmin", "Tenant Admin"),
    operator: t("users.roleOperator", "Operator"),
    client_viewer: t("users.roleClientViewer", "Client Viewer"),
  };
  const roleOptions = isPlatformAdmin
    ? [{ value: "tenant_admin", label: t("users.roleTenantAdmin", "Tenant Admin") }]
    : [
        { value: "operator", label: t("users.roleOperator", "Operator") },
        { value: "client_viewer", label: t("users.roleClientViewer", "Client Viewer") },
      ];
  const filterRoleOptions = isPlatformAdmin
    ? ["platform_admin", "tenant_admin"]
    : ["operator", "client_viewer"];
  const editRoleOptions = roleOptions;
  const permissionOptions = [
    { key: "inbound_orders.manage", label: t("users.permissionInboundManage", "Manage inbound orders") },
    { key: "inbound_orders.import", label: t("users.permissionInboundImport", "Import inbound orders") },
    { key: "receiving.execute", label: t("users.permissionReceiving", "Receive freight") },
    { key: "outbound_orders.manage", label: t("users.permissionOutboundManage", "Create outbound orders") },
    { key: "picking.execute", label: t("users.permissionPicking", "Run picking") },
    { key: "shipping.execute", label: t("users.permissionShipping", "Run shipping") },
    { key: "master_data.manage", label: t("users.permissionMasterData", "Maintain master data") },
    { key: "users.manage", label: t("users.permissionUsers", "Manage users") },
    { key: "billing.manage", label: t("users.permissionBilling", "Manage billing") },
    { key: "planner.manage", label: t("users.permissionPlanner", "Maintain planner & AGV rules") },
  ];
  const permissionOptionsForRole = useMemo(() => {
    if (form.role === "tenant_admin") return permissionOptions;
    if (form.role === "operator") {
      return permissionOptions.filter((permission) =>
        ["receiving.execute", "picking.execute", "shipping.execute"].includes(permission.key)
      );
    }
    return [];
  }, [form.role, permissionOptions]);
  const editPermissionOptionsForRole = useMemo(() => {
    if (editForm.role === "tenant_admin") return permissionOptions;
    if (editForm.role === "operator") {
      return permissionOptions.filter((permission) =>
        ["receiving.execute", "picking.execute", "shipping.execute"].includes(permission.key),
      );
    }
    return [];
  }, [editForm.role, permissionOptions]);
  const permissionLabelMap = Object.fromEntries(permissionOptions.map((permission) => [permission.key, permission.label]));
  const defaultPermissionsForRole = (value: string) => {
    if (value === "tenant_admin") {
      return permissionOptions.map((permission) => permission.key);
    }
    if (value === "operator") {
      return ["receiving.execute", "picking.execute", "shipping.execute"];
    }
    if (value === "client_viewer") {
      return [];
    }
    return [];
  };

  const { data: userPage } = useQuery({
    queryKey: queryKeys.adminUsers.list(),
    queryFn: fetchUsersPage,
  });

  const { data: clientPage } = useQuery({
    queryKey: queryKeys.adminUsers.clients(),
    queryFn: () => fetchClients({ limit: 500 }),
  });

  const { data: tenantPage } = useQuery({
    queryKey: queryKeys.adminUsers.tenants(),
    queryFn: fetchTenants,
    enabled: isPlatformAdmin,
  });

  const users: UserRow[] = userPage?.items || [];
  const clients: ClientRow[] = clientPage?.items || [];
  const tenants: TenantRow[] = tenantPage || [];
  const editingUser = users.find((user) => user.id === editingUserId) || null;
  const visibleUsers = useMemo(
    () =>
      users.filter((user) => {
        if (!showDisabledUsers && !user.is_active) return false;
        if (!showTestUsers && isTestUser(user)) return false;
        if (roleFilter !== "all" && user.role !== roleFilter) return false;
        const normalizedSearch = searchQuery.trim().toLowerCase();
        if (
          normalizedSearch &&
          ![user.full_name, user.email, user.job_title, user.tenant_name]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(normalizedSearch))
        ) {
          return false;
        }
        return true;
      }),
    [roleFilter, searchQuery, showDisabledUsers, showTestUsers, users],
  );
  const hiddenUsers = users.length - visibleUsers.length;
  const availableClients = useMemo(
    () =>
      isPlatformAdmin && form.tenant_id
        ? clients.filter((client) => client.tenant_id === form.tenant_id)
        : clients,
    [clients, form.tenant_id, isPlatformAdmin],
  );
  const editAvailableClients = useMemo(
    () =>
      editingUser?.tenant_id
        ? clients.filter((client) => client.tenant_id === editingUser.tenant_id)
        : clients,
    [clients, editingUser?.tenant_id],
  );
  const activeUsers = useMemo(() => users.filter((user) => user.is_active).length, [users]);
  const inactiveUsers = useMemo(() => users.filter((user) => !user.is_active).length, [users]);
  const clientViewers = useMemo(() => users.filter((user) => user.role === "client_viewer").length, [users]);
  const visibleTenants = useMemo(() => new Set(users.map((user) => user.tenant_id).filter(Boolean)).size, [users]);
  const canManageUser = (user: UserRow) =>
    isPlatformAdmin ? user.role === "tenant_admin" : ["operator", "client_viewer"].includes(user.role);

  const beginEditingUser = (user: UserRow) => {
    setEditingUserId(user.id);
    setSelectedUserId(user.id);
    setEditForm({
      full_name: user.full_name,
      job_title: user.job_title || "",
      role: user.role,
      permissions: user.permissions || [],
      client_id: user.client_id || "",
    });
    setError("");
    setSuccess("");
  };

  const cancelEditingUser = () => {
    setEditingUserId("");
    setSelectedUserId("");
  };

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers.list() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers.clients() }),
    ]);
  };

  const createUser = useMutation({
    mutationFn: async () =>
      createUserRequest({
        ...form,
        job_title: form.job_title || null,
        permissions: form.role === "client_viewer" ? [] : form.permissions,
        client_id: form.role === "client_viewer" ? form.client_id || null : null,
        tenant_id: isPlatformAdmin ? form.tenant_id || null : null,
      }),
    onSuccess: async () => {
      setError("");
      setSuccess(t("users.successCreated", "User created successfully."));
      setForm({
        email: "",
        full_name: "",
        password: "",
        role: isPlatformAdmin ? "tenant_admin" : "operator",
        job_title: "",
        permissions: defaultPermissionsForRole(isPlatformAdmin ? "tenant_admin" : "operator"),
        client_id: "",
        tenant_id: "",
      });
      await refresh();
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("users.errorCreate", "Could not create the user.")));
    },
  });

  const toggleUser = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      updateUser(userId, { is_active: isActive }),
    onSuccess: async () => {
      setError("");
      setSuccess(t("users.successUpdated", "User updated successfully."));
      await refresh();
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("users.errorUpdate", "Could not update the user.")));
    },
  });

  const editUser = useMutation({
    mutationFn: async () => {
      if (!editingUserId) throw new Error("Select a user to edit first.");
      return updateUser(editingUserId, {
        full_name: editForm.full_name,
        job_title: editForm.job_title || null,
        role: editForm.role,
        permissions: editForm.role === "client_viewer" ? [] : editForm.permissions,
        client_id: editForm.role === "client_viewer" ? editForm.client_id || null : null,
      });
    },
    onSuccess: async () => {
      setError("");
      setSuccess(t("users.successEdited", "User changes saved successfully."));
      cancelEditingUser();
      await refresh();
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("users.errorEdit", "Could not save user changes.")));
    },
  });

  const resetPassword = useMutation({
    mutationFn: async () => resetUserPassword(resetPasswordFor, newPassword),
    onSuccess: async () => {
      setError("");
      setSuccess(t("users.successReset", "Password reset successfully."));
      setResetPasswordFor("");
      setNewPassword("");
      await refresh();
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("users.errorReset", "Could not reset password.")));
    },
  });

  const previewCleanup = useMutation({
    mutationFn: previewNonAdminUserCleanup,
    onSuccess: (preview) => {
      setCleanupPreview(preview);
      setCleanupConfirmationText("");
      setError("");
      setSuccess("");
    },
    onError: (err: any) => {
      setCleanupPreview(null);
      setSuccess("");
      setError(getApiErrorMessage(err, t("users.cleanupPreviewError", "Could not preview user cleanup.")));
    },
  });

  const executeCleanup = useMutation({
    mutationFn: async () => {
      if (!cleanupPreview?.confirmation_payload?.confirmation_token) {
        throw new Error("Run a fresh cleanup preview first.");
      }
      return confirmNonAdminUserCleanup(cleanupPreview, cleanupIdempotencyKey);
    },
    onSuccess: async (response) => {
      const deletedCount = response.data?.deleted_count ?? cleanupPreview?.summary.delete_count ?? 0;
      setCleanupPreview(null);
      setCleanupConfirmationText("");
      setCleanupIdempotencyKey(createCleanupIdempotencyKey());
      setError("");
      setSuccess(t("users.cleanupSuccess", `${deletedCount} non-admin users deleted.`));
      await refresh();
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("users.cleanupError", "Could not complete user cleanup.")));
    },
  });

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[1.35rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_58%,#2e4852_100%)] p-5 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)] md:rounded-[2rem] md:p-7">
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full border-[26px] border-[#f7bf45]/15" />
        <div className="relative flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#f7bf45]">
              {t("users.eyebrow", "Access directory")}
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#f5efe5] md:text-4xl">
              {isPlatformAdmin ? t("users.platformTitle", "Tenant administration") : t("users.teamTitle", "Team users")}
            </h1>
            <p className="mt-3 text-sm text-[#c7d4dc]">
              {isPlatformAdmin
                ? t("users.platformScopeLabel", "Create tenants and assign tenant administrators")
                : t("users.teamScopeLabel", "Create and manage operators and client viewers")}
            </p>
          </div>
          <div className="flex shrink-0 flex-col gap-3 sm:flex-row lg:items-stretch">
            {isPlatformAdmin ? (
              <Link
                to="/workspaces"
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-xs font-bold uppercase tracking-[0.14em] text-[#f5efe5] transition hover:bg-white/16"
              >
                <Building2 size={15} />
                {t("users.manageTenants", "Manage tenants")}
              </Link>
            ) : null}
            <button
              type="button"
              onClick={() => document.getElementById("add-user")?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full bg-[#f7bf45] px-5 py-3 text-xs font-bold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#ffd16e]"
            >
              <UserPlus size={15} />
              {isPlatformAdmin ? t("users.createTenantAdmin", "Create tenant admin") : t("users.createTeamUser", "Create user")}
            </button>
            <div className="rounded-2xl border border-white/12 bg-white/8 px-4 py-3 text-left">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#9db1bf]">
                {t("users.scopeLabel", "Scope")}
              </p>
              <p className="mt-1 text-sm font-medium text-[#f5efe5]">
                {isPlatformAdmin ? t("users.platformGovernanceShort", "Tenant level") : t("users.governanceShort", "Workspace level")}
              </p>
            </div>
          </div>
        </div>
      </section>

      {isPlatformAdmin ? (
        <details open={Boolean(cleanupPreview)} className="rounded-[1.35rem] border border-[#b84a35]/20 bg-[#fffaf6] shadow-[0_18px_44px_rgba(184,74,53,0.06)] md:rounded-[1.8rem]">
          <summary className="cursor-pointer list-none px-4 py-4 md:px-6 md:py-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl border border-[#b84a35]/20 bg-[#b84a35]/10 p-2.5 text-[#b84a35]">
                  <AlertTriangle size={18} />
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#b84a35]">
                    {t("users.cleanupEyebrow", "Danger zone")}
                  </p>
                  <h2 className="mt-1 text-lg font-semibold tracking-[-0.02em] text-[#13212c]">
                    {t("users.cleanupTitle", "Clear non-admin accounts")}
                  </h2>
                  <p className="mt-1 text-sm leading-6 text-[#61717d]">
                    {t("users.cleanupBody", "Operator and client-viewer records only. Tenant admins are retained.")}
                  </p>
                </div>
              </div>
              <div className="ml-12 flex flex-wrap items-center gap-2 sm:ml-0 sm:justify-end">
                <span className="inline-flex rounded-full border border-[#b84a35]/20 bg-white px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-[#9b452a]">
                  {t("users.cleanupHighRisk", "High risk")}
                </span>
                <button
                  type="button"
                  onClick={(event) => {
                    event.preventDefault();
                    previewCleanup.mutate();
                  }}
                  disabled={previewCleanup.isPending || executeCleanup.isPending}
                  className="inline-flex min-h-[38px] items-center gap-2 rounded-full bg-[#b84a35] px-4 py-2 text-[10px] font-bold uppercase tracking-[0.14em] text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Trash2 size={13} />
                  {t("users.clearRecords", "Clear non-admin records")}
                </button>
              </div>
            </div>
          </summary>

          <div className="border-t border-[#b84a35]/12 px-4 pb-4 pt-4 md:px-6 md:pb-6">
            <div className="flex flex-col gap-3 rounded-2xl border border-[#b84a35]/12 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm leading-6 text-[#61717d]">
                {t("users.cleanupReviewHint", "Always preview the exact records before confirming a deletion.")}
              </p>
              <button
                type="button"
                onClick={() => previewCleanup.mutate()}
                disabled={previewCleanup.isPending || executeCleanup.isPending}
                className="inline-flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-full border border-[#b84a35]/30 bg-white px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#b84a35] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={14} />
                {previewCleanup.isPending
                  ? t("users.cleanupPreviewing", "Preparing preview...")
                  : t("users.cleanupPreview", "Refresh preview")}
              </button>
            </div>

          {cleanupPreview ? (
            <div className="mt-5 rounded-[1.15rem] border border-[#b84a35]/18 bg-white px-4 py-4 md:px-5">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl bg-[#fff3ed] px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8d5a4e]">
                    {t("users.cleanupDeleteCount", "Accounts to delete")}
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-[#b84a35]">{cleanupPreview.summary.delete_count}</p>
                </div>
                <div className="rounded-2xl bg-[#f2f7f3] px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#52715d]">
                    {t("users.cleanupPreserveCount", "Admins retained")}
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-[#2f6545]">{cleanupPreview.preserved.count}</p>
                </div>
                <div className="rounded-2xl bg-[#f7f4ee] px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c6a55]">
                    {t("users.cleanupPreserveRoles", "Protected roles")}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[#13212c]">
                    {cleanupPreview.preserved.roles.map((value) => roleLabels[value] || value).join(" · ")}
                  </p>
                </div>
              </div>

              {cleanupPreview.blocking_errors.length ? (
                <p className="mt-4 rounded-2xl border border-[#b84a35]/20 bg-[#fff3ed] px-4 py-3 text-sm leading-6 text-[#8d3c2b]">
                  {cleanupPreview.blocking_errors.map((item) => item.message).join(" ")}
                </p>
              ) : cleanupPreview.summary.delete_count > 0 ? (
                <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-end">
                  <label className="min-w-0 flex-1">
                    <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c6a55]">
                      {t("users.cleanupConfirmLabel", "Type the confirmation phrase")}
                    </span>
                    <input
                      value={cleanupConfirmationText}
                      onChange={(event) => setCleanupConfirmationText(event.target.value)}
                      placeholder={cleanupConfirmationPhrase}
                      className="w-full rounded-2xl border border-[#b84a35]/20 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#b84a35]/45 focus:ring-4 focus:ring-[#b84a35]/10"
                    />
                  </label>
                  <button
                    type="button"
                    disabled={cleanupConfirmationText !== cleanupConfirmationPhrase || executeCleanup.isPending}
                    onClick={() => executeCleanup.mutate()}
                    className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full bg-[#b84a35] px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-white disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    <Trash2 size={14} />
                    {executeCleanup.isPending
                      ? t("users.cleanupExecuting", "Deleting...")
                      : t("users.cleanupExecute", "Delete listed users")}
                  </button>
                </div>
              ) : (
                <p className="mt-4 rounded-2xl border border-[#2f6545]/15 bg-[#f2f7f3] px-4 py-3 text-sm leading-6 text-[#2f6545]">
                  {t("users.cleanupNone", "No non-admin user accounts are currently eligible for cleanup.")}
                </p>
              )}
            </div>
          ) : null}
          </div>
        </details>
      ) : null}

      <section
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="users-mobile-governance"
        data-admin-mobile-contract="desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("users.mobileGovernanceTitle", "User management is desktop-first")}
        </p>
        <p className="mt-1">
          {t(
            "users.mobileGovernanceBody",
            "Review users on phone; use a larger screen for role and password changes.",
          )}
        </p>
      </section>

      <details className="rounded-[1.1rem] border border-[#13212c]/8 bg-white/84 px-4 py-3 md:hidden">
        <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
          {t("users.viewAccessCounts", "View access counts")}
        </summary>
        <div className="mt-3 grid gap-3">
          <SignalCard
            icon={Users}
            label={t(isPlatformAdmin ? "users.totalUsersPlatform" : "users.totalUsers", isPlatformAdmin ? "Platform users" : "Total users")}
            value={String(users.length)}
            note={t("users.totalUsersNote", "All accounts, including disabled records")}
          />
          <SignalCard
            icon={CheckCircle2}
            label={t("users.activeUsers", "Active users")}
            value={String(activeUsers)}
            note={t("users.activeUsersNote", "Currently able to sign in")}
          />
        </div>
      </details>

      <div className="hidden gap-4 md:grid lg:grid-cols-4">
        <SignalCard
          icon={Users}
          label={t(isPlatformAdmin ? "users.totalUsersPlatform" : "users.totalUsers", isPlatformAdmin ? "Platform users" : "Total users")}
          value={String(users.length)}
          note={t("users.totalUsersNote", "All accounts, including disabled records")}
        />
        <SignalCard
          icon={CheckCircle2}
          label={t("users.activeUsers", "Active users")}
          value={String(activeUsers)}
          note={t("users.activeUsersNote", "Currently able to sign in")}
        />
        <SignalCard
          icon={Archive}
          label={t("users.inactiveUsers", "Archived users")}
          value={String(inactiveUsers)}
          note={t("users.inactiveUsersNote", "Cannot sign in; kept for audit")}
        />
        <SignalCard
          icon={Building2}
          label={t(isPlatformAdmin ? "users.visibleTenants" : "users.clientViewers", isPlatformAdmin ? "Companies" : "Client viewers")}
          value={String(isPlatformAdmin ? visibleTenants : clientViewers)}
          note={t(
            isPlatformAdmin ? "users.visibleTenantsNote" : "users.clientViewersNote",
            isPlatformAdmin ? "Tenant workspaces represented in this directory" : "Portal-only users linked to customer accounts",
          )}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_380px]">
        <details
          className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/85 px-4 py-3 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:hidden"
          data-testid="users-mobile-add-user-collapsed"
        >
          <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
            {t("users.mobileAddUserSummary", "Add user is desktop-preferred")}
          </summary>
          <p className="mt-2 text-sm leading-6 text-[#61717d]">
            {t(
              "users.mobileAddUserBody",
              "Create accounts on a larger screen where the full access form is visible.",
            )}
          </p>
        </details>

        <section id="user-directory" className="hidden rounded-[1.35rem] border border-[#13212c]/10 bg-white/90 p-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block md:rounded-[1.8rem] md:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#24507a]/15 bg-[#eef3f8] p-2.5 text-[#24507a]">
                <Users size={18} />
              </div>
              <div>
                <p className="text-lg font-semibold tracking-[-0.02em] text-[#13212c]">
                  {isPlatformAdmin ? t("users.tenantAccessDirectory", "Tenant access") : t("users.teamDirectory", "Team users")}
                </p>
                <p className="mt-1 hidden text-sm text-[#61717d] md:block">
                  {isPlatformAdmin
                    ? t("users.platformDirectoryHint", "Other roles are managed inside their tenant.")
                    : t("users.teamDirectoryHint", "Operators and client viewers in this workspace.")}
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => document.getElementById("add-user")?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className="inline-flex min-h-[42px] items-center justify-center gap-2 rounded-full border border-[#13212c]/12 bg-[#f7f4ee] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:border-[#13212c]/25 hover:bg-white"
            >
              <UserPlus size={14} />
              {isPlatformAdmin ? t("users.createTenantAdmin", "Create tenant admin") : t("users.createTeamUser", "Create user")}
            </button>
          </div>

          <div className="mt-5 grid gap-3 rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] p-3 lg:grid-cols-[minmax(0,1fr)_180px_auto_auto] lg:items-center">
            <label className="relative block">
              <span className="sr-only">{t("users.searchUsers", "Search users")}</span>
              <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[#7f8d98]" />
              <input
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder={t("users.searchUsersPlaceholder", "Search by name, email, job title, or company")}
                className="min-h-[44px] w-full rounded-xl border border-[#13212c]/10 bg-white py-2.5 pl-10 pr-3 text-sm text-[#13212c] outline-none transition placeholder:text-[#9aa5ad] focus:border-[#24507a]/40 focus:ring-4 focus:ring-[#24507a]/8"
              />
            </label>
            <label>
              <span className="sr-only">{t("users.filterRole", "Filter by role")}</span>
              <select
                value={roleFilter}
                onChange={(event) => setRoleFilter(event.target.value)}
                className="min-h-[44px] w-full rounded-xl border border-[#13212c]/10 bg-white px-3 py-2.5 text-sm text-[#13212c] outline-none focus:border-[#24507a]/40 focus:ring-4 focus:ring-[#24507a]/8"
              >
                <option value="all">{t("users.allRoles", "All roles")}</option>
                {filterRoleOptions.map((value) => (
                  <option key={value} value={value}>{roleLabels[value]}</option>
                ))}
              </select>
            </label>
            <label className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border border-[#13212c]/10 bg-white px-3 py-2 text-xs font-semibold text-[#334351]">
              <input
                type="checkbox"
                checked={showDisabledUsers}
                onChange={(event) => setShowDisabledUsers(event.target.checked)}
                className="h-4 w-4 accent-[#13212c]"
              />
              {t("users.showDisabled", "Include archived")}
            </label>
            <label className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border border-[#13212c]/10 bg-white px-3 py-2 text-xs font-semibold text-[#334351]">
              <input
                type="checkbox"
                checked={showTestUsers}
                onChange={(event) => setShowTestUsers(event.target.checked)}
                className="h-4 w-4 accent-[#13212c]"
              />
              {t("users.showTestUsers", "Include test records")}
            </label>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[#7c8a96]">
            <span className="inline-flex items-center gap-1.5 font-semibold text-[#334351]"><Filter size={13} /> {t("users.directoryResults", "Directory view")}</span>
            <span>{t("users.showingUsers", "Showing {visible} of {total} accounts", { visible: visibleUsers.length, total: users.length })}</span>
            {hiddenUsers > 0 ? <span>{t("users.hiddenByFilters", "{hidden} excluded by current filters", { hidden: hiddenUsers })}</span> : null}
          </div>

          {error ? (
            <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
          ) : null}
          {success ? (
            <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{success}</p>
          ) : null}

          <div className="mt-5 space-y-3">
            {visibleUsers.map((user) => {
              const isSelected = selectedUserId === user.id;
              return (
              <div key={user.id} className={`rounded-[1.1rem] border px-4 py-4 md:rounded-[1.35rem] ${
                isSelected
                  ? "border-[#285f93]/30 bg-[#eef6ff] shadow-[inset_4px_0_0_#285f93]"
                  : "border-[#13212c]/10 bg-[#f7f4ee]"
              }`}>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-base font-semibold text-[#13212c]">{user.full_name}</p>
                      <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#677581]">
                        {roleLabels[user.role] || user.role}
                      </span>
                      {user.job_title ? (
                        <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7a6440]">
                          {user.job_title}
                        </span>
                      ) : null}
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                          user.is_active
                            ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                            : "border border-amber-200 bg-amber-50 text-amber-700"
                        }`}
                      >
                        {user.is_active ? t("users.active", "Active") : t("users.disabled", "Disabled")}
                      </span>
                      {isTestUser(user) ? (
                        <span className="rounded-full border border-[#c8d2dc] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                          {t("users.testRecord", "Test")}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-2 text-sm text-[#61717d]">{user.email}</p>
                    {isPlatformAdmin && user.tenant_name ? (
                      <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7c8a96]">
                        {t("users.tenantLabel", "Tenant")}: {user.tenant_name}
                      </p>
                    ) : null}
                    <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7c8a96]">
                      {user.client_id
                        ? t("users.clientLinked", "Client-linked portal access")
                        : t("users.tenantScope", "Tenant workspace access")}
                    </p>
                    {user.permissions?.length ? (
                      <p className="mt-2 hidden text-xs leading-5 text-[#7c8a96] md:block">
                        {user.permissions.map((permission) => permissionLabelMap[permission] || permission).join(" · ")}
                      </p>
                    ) : null}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedUserId(isSelected ? "" : user.id)}
                      className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] md:hidden"
                    >
                      {isSelected ? t("common.close", "Close") : t("common.manage", "Manage")}
                    </button>
                    {canManageUser(user) ? (
                      <div className={`${isSelected ? "flex" : "hidden"} w-full flex-col gap-2 md:flex md:w-auto md:flex-row md:flex-wrap`}>
                        <button
                          type="button"
                          onClick={() => beginEditingUser(user)}
                          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full border border-[#285f93]/25 bg-[#eef6ff] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#285f93]"
                        >
                          <Pencil size={13} />
                          {t("users.editUser", "Edit user")}
                        </button>
                        <button
                          type="button"
                          onClick={() => toggleUser.mutate({ userId: user.id, isActive: !user.is_active })}
                          className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                        >
                          {user.is_active ? t("users.disableUser", "Disable user") : t("users.activateUser", "Activate user")}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedUserId(user.id);
                            setResetPasswordFor(resetPasswordFor === user.id ? "" : user.id);
                          }}
                          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8]"
                        >
                          <KeyRound size={13} />
                          {t("users.resetPassword", "Reset password")}
                        </button>
                      </div>
                    ) : (
                      <span className={`${isSelected ? "inline-flex" : "hidden"} min-h-[44px] items-center rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c8a96] md:inline-flex`}>
                        {isPlatformAdmin
                          ? user.role === "platform_admin"
                            ? t("users.platformAccount", "Platform account")
                            : t("users.tenantAdminScope", "Managed by tenant admin")
                          : t("users.superAdminOnly", "Super admin only")}
                      </span>
                    )}
                  </div>
                </div>

                {user.permissions?.length ? (
                  <details className="mt-3 rounded-[1rem] border border-[#13212c]/8 bg-white/70 px-3 py-2 md:hidden">
                    <summary className="cursor-pointer list-none text-xs font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                      {t("users.permissions", "Operational permissions")}
                    </summary>
                    <p className="mt-2 text-xs leading-5 text-[#7c8a96]">
                      {user.permissions.map((permission) => permissionLabelMap[permission] || permission).join(" · ")}
                    </p>
                  </details>
                ) : null}

                {resetPasswordFor === user.id ? (
                  <div className="mt-4 flex flex-col gap-3 rounded-[1.2rem] border border-[#13212c]/10 bg-white px-4 py-4 md:flex-row md:items-center">
                    <PasswordInput
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder={t("users.newPassword", "New password")}
                      wrapperClassName="min-w-0 flex-1"
                      className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                    />
                    <button
                      type="button"
                      disabled={!newPassword || resetPassword.isPending}
                      onClick={() => resetPassword.mutate()}
                      className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:opacity-50"
                    >
                      {t("users.applyReset", "Apply reset")}
                      <ArrowRight size={14} />
                    </button>
                  </div>
                ) : null}
              </div>
              );
            })}
            {visibleUsers.length === 0 ? (
              <div className="rounded-[1.35rem] border border-dashed border-[#13212c]/16 bg-[#f7f4ee] px-4 py-8 text-center text-sm text-[#61717d]">
                {t("users.noVisibleUsers", "No users match the current filters.")}
              </div>
            ) : null}
          </div>
        </section>

        <div className="space-y-6">
          {editingUser ? (
            <section className="rounded-[1.35rem] border border-[#285f93]/20 bg-[#eef6ff]/70 p-4 shadow-[0_18px_44px_rgba(40,95,147,0.08)] md:rounded-[1.8rem] md:p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#285f93]">
                    {t("users.editEyebrow", "Account controls")}
                  </p>
                  <p className="mt-1 text-lg font-semibold text-[#13212c]">
                    {t("users.editTitle", "Edit access")}
                  </p>
                  <p className="mt-1 text-sm text-[#61717d]">{editingUser.email}</p>
                  {isPlatformAdmin && editingUser.tenant_name ? (
                    <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7c8a96]">
                      {t("users.tenantLabel", "Tenant")}: {editingUser.tenant_name}
                    </p>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={cancelEditingUser}
                  className="inline-flex min-h-[40px] items-center justify-center rounded-full border border-[#13212c]/12 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#61717d]"
                >
                  <X size={14} />
                  <span className="sr-only">{t("common.close", "Close")}</span>
                </button>
              </div>

              <div className="mt-5 space-y-4">
                <Field label={t("users.fullName", "Full name")}>
                  <input
                    type="text"
                    value={editForm.full_name}
                    onChange={(event) => setEditForm({ ...editForm, full_name: event.target.value })}
                    className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#285f93]/40 focus:ring-4 focus:ring-[#285f93]/10"
                  />
                </Field>
                <Field label={t("users.jobTitle", "Job title")}>
                  <input
                    type="text"
                    value={editForm.job_title}
                    onChange={(event) => setEditForm({ ...editForm, job_title: event.target.value })}
                    placeholder={t("users.jobTitlePlaceholder", "Inbound coordinator, warehouse lead, sales desk...")}
                    className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#285f93]/40 focus:ring-4 focus:ring-[#285f93]/10"
                  />
                </Field>
                {isPlatformAdmin ? (
                  <div className="rounded-2xl border border-[#13212c]/8 bg-white px-4 py-3">
                    <p className="text-sm font-medium text-[#334351]">{t("users.role", "Role")}</p>
                    <p className="mt-1 text-sm font-semibold text-[#13212c]">{roleLabels.tenant_admin}</p>
                  </div>
                ) : (
                  <Field label={t("users.role", "Role")}>
                    <select
                      value={editForm.role}
                      onChange={(event) =>
                        setEditForm({
                          ...editForm,
                          role: event.target.value,
                          permissions: defaultPermissionsForRole(event.target.value),
                          client_id: "",
                        })
                      }
                      className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#285f93]/40 focus:ring-4 focus:ring-[#285f93]/10"
                    >
                      {editRoleOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                {editForm.role !== "client_viewer" && editForm.role !== "platform_admin" ? (
                  <Field label={t("users.permissions", "Operational permissions")}>
                    <div className="grid gap-2 rounded-[1.25rem] border border-[#13212c]/8 bg-white p-4">
                      {editPermissionOptionsForRole.map((permission) => (
                        <label key={permission.key} className="flex items-center gap-3 text-sm text-[#334351]">
                          <input
                            type="checkbox"
                            checked={editForm.permissions.includes(permission.key)}
                            onChange={(event) =>
                              setEditForm((previous) => ({
                                ...previous,
                                permissions: event.target.checked
                                  ? [...previous.permissions, permission.key]
                                  : previous.permissions.filter((value) => value !== permission.key),
                              }))
                            }
                          />
                          <span>{permission.label}</span>
                        </label>
                      ))}
                    </div>
                  </Field>
                ) : null}
                {editForm.role === "client_viewer" ? (
                  <Field label={t("users.linkedClient", "Linked client")}>
                    <select
                      value={editForm.client_id}
                      onChange={(event) => setEditForm({ ...editForm, client_id: event.target.value })}
                      className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#285f93]/40 focus:ring-4 focus:ring-[#285f93]/10"
                    >
                      <option value="">{t("users.selectClient", "Select a client")}</option>
                      {editAvailableClients.map((client) => (
                        <option key={client.id} value={client.id}>
                          {client.name} ({client.code})
                        </option>
                      ))}
                    </select>
                  </Field>
                ) : null}
                <div className="flex flex-col gap-2 sm:flex-row">
                  <button
                    type="button"
                    disabled={editUser.isPending || !editForm.full_name.trim() || (editForm.role === "client_viewer" && !editForm.client_id)}
                    onClick={() => editUser.mutate()}
                    className="inline-flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-full bg-[#285f93] px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Save size={14} />
                    {editUser.isPending ? t("users.savingUser", "Saving...") : t("users.saveUser", "Save changes")}
                  </button>
                  <button
                    type="button"
                    onClick={cancelEditingUser}
                    className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-[#13212c]/12 bg-white px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#61717d]"
                  >
                    {t("common.cancel", "Cancel")}
                  </button>
                </div>
              </div>
            </section>
          ) : null}

          <section id="add-user" className="scroll-mt-6 rounded-[1.35rem] border border-[#f7bf45]/30 bg-white/90 p-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:rounded-[1.8rem] md:p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[#f7bf45]/28 bg-[#f7bf45]/12 p-2.5 text-[#d19009]">
              <UserPlus size={18} />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#a16b08]">{t("users.provisionEyebrow", "Provision access")}</p>
              <p className="mt-1 text-lg font-semibold tracking-[-0.02em] text-[#13212c]">
                {isPlatformAdmin ? t("users.createTenantAdmin", "Create tenant admin") : t("users.createTeamUser", "Create user")}
              </p>
            </div>
          </div>

          <div className="mt-5 space-y-4">
            {isPlatformAdmin ? (
              <Field label={t("users.targetTenant", "Target tenant")}>
                <select
                  value={form.tenant_id}
                  onChange={(e) => setForm({ ...form, tenant_id: e.target.value, client_id: "" })}
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                >
                  <option value="">{t("users.selectTenant", "Select a tenant")}</option>
                  {tenants.map((tenant) => (
                    <option key={tenant.id} value={tenant.id}>
                      {tenant.name} ({tenant.code})
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
            <Field label={t("users.fullName", "Full name")}>
              <input
                type="text"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            <Field label={t("users.email", "Email")}>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            <Field label={t("users.tempPassword", "Temporary password")}>
              <PasswordInput
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            <Field label={t("users.jobTitle", "Job title")}>
              <input
                type="text"
                value={form.job_title}
                onChange={(e) => setForm({ ...form, job_title: e.target.value })}
                placeholder={t("users.jobTitlePlaceholder", "Inbound coordinator, warehouse lead, sales desk...")}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            {isPlatformAdmin ? (
              <div className="rounded-2xl border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3">
                <p className="text-sm font-medium text-[#334351]">{t("users.role", "Role")}</p>
                <p className="mt-1 text-sm font-semibold text-[#13212c]">{roleLabels.tenant_admin}</p>
              </div>
            ) : (
              <Field label={t("users.role", "Role")}>
                <select
                  value={form.role}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      role: e.target.value,
                      permissions: defaultPermissionsForRole(e.target.value),
                      client_id: "",
                    })
                  }
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                >
                  {roleOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {!isPlatformAdmin && form.role !== "client_viewer" ? (
              <Field label={t("users.permissions", "Operational permissions")}>
                <div className="grid gap-2 rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                  {permissionOptionsForRole.map((permission) => (
                    <label key={permission.key} className="flex items-center gap-3 text-sm text-[#334351]">
                      <input
                        type="checkbox"
                        checked={form.permissions.includes(permission.key)}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            permissions: e.target.checked
                              ? [...prev.permissions, permission.key]
                              : prev.permissions.filter((value) => value !== permission.key),
                          }))
                        }
                      />
                      <span>{permission.label}</span>
                    </label>
                  ))}
                </div>
              </Field>
            ) : null}
            {form.role === "client_viewer" ? (
              <Field label={t("users.linkedClient", "Linked client")}>
                <select
                  value={form.client_id}
                  onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                >
                  <option value="">{t("users.selectClient", "Select a client")}</option>
                  {availableClients.map((client) => (
                    <option key={client.id} value={client.id}>
                      {client.name} ({client.code})
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}

            <button
              type="button"
              disabled={
                createUser.isPending ||
                !form.full_name ||
                !form.email ||
                !form.password ||
                (isPlatformAdmin && !form.tenant_id) ||
                (form.role === "client_viewer" && !form.client_id)
              }
              onClick={() => createUser.mutate()}
              className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040] disabled:opacity-50"
            >
              {createUser.isPending
                ? t("users.creatingUser", "Creating user...")
                : isPlatformAdmin
                  ? t("users.createTenantAdmin", "Create tenant admin")
                  : t("users.createUser", "Create user")}
              <ArrowRight size={15} />
            </button>
          </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function SignalCard({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: any;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/84 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.05)]">
      <div className="inline-flex rounded-2xl border border-[#13212c]/10 bg-[#f7f4ee] p-2.5 text-[#13212c]">
        <Icon size={18} />
      </div>
      <p className="mt-4 text-xs uppercase tracking-[0.18em] text-[#7b8893]">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{value}</p>
      <p className="mt-2 text-sm text-[#61717d]">{note}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="block">
      <span className="mb-1.5 block text-sm font-medium text-[#334351]">{label}</span>
      {children}
    </div>
  );
}
