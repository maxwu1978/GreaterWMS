import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, ShieldCheck, Users, Wand2 } from "lucide-react";
import {
  decideTenantApproval,
  fetchTenantApprovals,
  fetchTenants,
  fetchUsersPage,
  type TenantApprovalItem,
} from "../../shared/api/users";
import { queryKeys } from "../../shared/api/queryKeys";
import { useI18n } from "../../shared/i18n";

type TenantRow = {
  id: string;
  name: string;
  code: string;
  contact_email: string;
  contact_phone: string | null;
  plan_tier: string;
  is_active: boolean;
};

type UserRow = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  tenant_id?: string | null;
};

function isTestWorkspace(tenant: TenantRow) {
  const name = tenant.name.toLowerCase();
  const code = tenant.code.toLowerCase();
  const email = tenant.contact_email.toLowerCase();
  if (name.startsWith("accept ") || name.startsWith("acceptance ")) return true;
  if (name.startsWith("action first ")) return true;
  if (name.includes("mailersend smoke")) return true;
  if (name === "bad email co") return true;
  if (name === "platform admin workspace") return true;
  if (email.endsWith("@example.com") || email === "not-an-email") return true;
  if (code.startsWith("accept") || code.startsWith("act")) return true;
  return false;
}

export default function PlatformWorkspacesPage() {
  const { t } = useI18n();
  const [showTestWorkspaces, setShowTestWorkspaces] = useState(false);

  const { data: tenants = [] } = useQuery({
    queryKey: queryKeys.platform.workspaces(),
    queryFn: () => fetchTenants().then((data) => data as TenantRow[]),
  });

  const { data: userPage } = useQuery({
    queryKey: queryKeys.platform.workspaceUsers(),
    queryFn: fetchUsersPage,
  });

  const queryClient = useQueryClient();
  const { data: pendingApprovals = [] } = useQuery({
    queryKey: queryKeys.platform.tenantApprovals(),
    queryFn: () => fetchTenantApprovals("pending"),
    refetchInterval: 60_000,
  });
  const approvalMutation = useMutation({
    mutationFn: ({ tenantId, action }: { tenantId: string; action: "approve" | "reject" }) =>
      decideTenantApproval(tenantId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.platform.tenantApprovals() });
      queryClient.invalidateQueries({ queryKey: queryKeys.platform.workspaces() });
    },
  });

  const users: UserRow[] = userPage?.items || [];
  const tenantStats = useMemo(() => {
    const stats = new Map<string, { activeUsers: number; totalUsers: number; admins: number }>();
    users.forEach((user) => {
      if (!user.tenant_id) return;
      const current = stats.get(user.tenant_id) || { activeUsers: 0, totalUsers: 0, admins: 0 };
      current.totalUsers += 1;
      if (user.is_active) current.activeUsers += 1;
      if (user.is_active && user.role === "tenant_admin") current.admins += 1;
      stats.set(user.tenant_id, current);
    });
    return stats;
  }, [users]);

  const visibleTenants = useMemo(
    () => tenants.filter((tenant) => showTestWorkspaces || !isTestWorkspace(tenant)),
    [showTestWorkspaces, tenants],
  );
  const hiddenTenants = tenants.length - visibleTenants.length;
  const activeWorkspaceCount = visibleTenants.filter((tenant) => tenant.is_active).length;
  const activeUserCount = visibleTenants.reduce(
    (total, tenant) => total + (tenantStats.get(tenant.id)?.activeUsers || 0),
    0,
  );
  const adminCount = visibleTenants.reduce(
    (total, tenant) => total + (tenantStats.get(tenant.id)?.admins || 0),
    0,
  );

  return (
    <div className="space-y-6">
      {pendingApprovals.length > 0 && (
        <section className="rounded-[2rem] border border-[#e8c15a]/50 bg-[#fdf6e3] p-6 shadow-[0_18px_42px_rgba(19,33,44,0.06)]">
          <h2 className="text-lg font-semibold text-[#13212c]">
            {t("workspaces.pendingApprovalsTitle", "Pending registrations")}
            <span className="ml-2 rounded-full bg-[#13212c] px-2.5 py-0.5 text-xs font-semibold text-[#f6f2ea]">
              {pendingApprovals.length}
            </span>
          </h2>
          <p className="mt-1 text-sm text-[#6a6046]">
            {t(
              "workspaces.pendingApprovalsBody",
              "New workspaces cannot sign in until you approve them.",
            )}
          </p>
          <div className="mt-4 space-y-3">
            {pendingApprovals.map((item: TenantApprovalItem) => (
              <div
                key={item.id}
                className="flex flex-col gap-3 rounded-2xl border border-[#13212c]/10 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="truncate font-semibold text-[#13212c]">
                    {item.name} <span className="font-normal text-[#7a8894]">({item.code})</span>
                  </p>
                  <p className="truncate text-sm text-[#5b6a77]">
                    {item.contact_email} · {item.plan_tier} ·{" "}
                    {item.created_at ? new Date(item.created_at).toLocaleString() : ""}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    disabled={approvalMutation.isPending}
                    onClick={() => approvalMutation.mutate({ tenantId: item.id, action: "approve" })}
                    className="rounded-full bg-[#28543b] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#1f4530] disabled:opacity-50"
                  >
                    {t("workspaces.approve", "Approve")}
                  </button>
                  <button
                    type="button"
                    disabled={approvalMutation.isPending}
                    onClick={() => approvalMutation.mutate({ tenantId: item.id, action: "reject" })}
                    className="rounded-full border border-[#a33a2e]/40 bg-white px-4 py-2 text-sm font-semibold text-[#a33a2e] transition hover:bg-[#fbeae7] disabled:opacity-50"
                  >
                    {t("workspaces.reject", "Reject")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_60%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">
              {t("workspaces.eyebrow", "Platform controls")}
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#f5efe5]">
              {t("workspaces.title", "Workspaces")}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#c7d4dc]">
              {t(
                "workspaces.heroBody",
                "Review tenant workspaces, active access, and support boundaries before stepping into company operations.",
              )}
            </p>
          </div>
          <div className="rounded-[1.4rem] border border-white/10 bg-white/5 p-4 lg:max-w-sm">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#9db1bf]">
              {t("workspaces.supportMode", "Support mode")}
            </p>
            <p className="mt-2 text-sm leading-6 text-[#d2dde4]">
              {t(
                "workspaces.supportModeBody",
                "Tenant entry should require a selected workspace, a reason, and an audit trail. Direct operations access stays closed until that flow is enabled.",
              )}
            </p>
          </div>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-4">
        <SignalCard
          icon={Building2}
          label={t("workspaces.visibleWorkspaces", "Visible workspaces")}
          value={String(visibleTenants.length)}
          note={t("workspaces.visibleWorkspacesNote", "Shown after platform filters")}
        />
        <SignalCard
          icon={ShieldCheck}
          label={t("workspaces.activeWorkspaces", "Active workspaces")}
          value={String(activeWorkspaceCount)}
          note={t("workspaces.activeWorkspacesNote", "Enabled tenant records")}
        />
        <SignalCard
          icon={Users}
          label={t("workspaces.activeUsers", "Active users")}
          value={String(activeUserCount)}
          note={t("workspaces.activeUsersNote", "Across visible workspaces")}
        />
        <SignalCard
          icon={Wand2}
          label={t("workspaces.tenantAdmins", "Tenant admins")}
          value={String(adminCount)}
          note={t("workspaces.tenantAdminsNote", "Active company administrators")}
        />
      </div>

      <section className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
              <Building2 size={18} />
            </div>
            <div>
              <p className="text-sm font-semibold text-[#13212c]">
                {t("workspaces.workspaceList", "Workspace list")}
              </p>
              <p className="text-sm text-[#61717d]">
                {t("workspaces.workspaceListBody", "Keep tenant review separate from day-to-day warehouse work.")}
              </p>
            </div>
          </div>

          <label className="inline-flex w-fit items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#334351]">
            <input
              type="checkbox"
              checked={showTestWorkspaces}
              onChange={(event) => setShowTestWorkspaces(event.target.checked)}
              className="h-4 w-4 accent-[#13212c]"
            />
            {t("workspaces.showTestWorkspaces", "Show test workspaces")}
          </label>
        </div>

        <p className="mt-4 text-xs uppercase tracking-[0.14em] text-[#7c8a96]">
          {hiddenTenants > 0
            ? t("workspaces.hiddenByFilters", "{hidden} hidden by filters", { hidden: hiddenTenants })
            : t("workspaces.noHiddenWorkspaces", "No workspaces hidden by filters")}
        </p>

        <div className="mt-5 space-y-3">
          {visibleTenants.map((tenant) => {
            const stats = tenantStats.get(tenant.id) || { activeUsers: 0, totalUsers: 0, admins: 0 };
            return (
              <div key={tenant.id} className="rounded-[1.35rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-4">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-base font-semibold text-[#13212c]">{tenant.name}</p>
                      <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#677581]">
                        {tenant.code}
                      </span>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                          tenant.is_active
                            ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                            : "border border-amber-200 bg-amber-50 text-amber-700"
                        }`}
                      >
                        {tenant.is_active ? t("common.active", "Active") : t("common.disabled", "Disabled")}
                      </span>
                      {isTestWorkspace(tenant) ? (
                        <span className="rounded-full border border-[#c8d2dc] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                          {t("workspaces.testWorkspace", "Test")}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-2 text-sm text-[#61717d]">{tenant.contact_email}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7c8a96]">
                      {t("workspaces.planTier", "Plan")}: {tenant.plan_tier}
                    </p>
                  </div>

                  <div className="grid gap-2 text-sm text-[#334351] sm:grid-cols-3 lg:min-w-[360px]">
                    <MiniStat label={t("workspaces.users", "Users")} value={String(stats.totalUsers)} />
                    <MiniStat label={t("workspaces.active", "Active")} value={String(stats.activeUsers)} />
                    <MiniStat label={t("workspaces.admins", "Admins")} value={String(stats.admins)} />
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled
                    className="inline-flex items-center justify-center rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#7c8a96] disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {t("workspaces.supportModeLocked", "Support mode locked")}
                  </button>
                </div>
              </div>
            );
          })}

          {visibleTenants.length === 0 ? (
            <div className="rounded-[1.35rem] border border-dashed border-[#13212c]/16 bg-[#f7f4ee] px-4 py-8 text-center text-sm text-[#61717d]">
              {t("workspaces.noVisibleWorkspaces", "No workspaces match the current filters.")}
            </div>
          ) : null}
        </div>
      </section>
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

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-3 py-2">
      <p className="text-[10px] uppercase tracking-[0.16em] text-[#7c8a96]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}
