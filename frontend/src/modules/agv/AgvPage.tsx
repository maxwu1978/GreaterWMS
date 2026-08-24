import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Boxes,
  CheckCircle2,
  MapPinned,
  Route,
  ScanSearch,
} from "lucide-react";
import {
  fetchAgvLocationValidation,
  fetchAgvPendingTasks,
  fetchWcsBindings,
} from "../../shared/api/agv";
import { fetchWarehouses } from "../../shared/api/planner";
import { queryKeys } from "../../shared/api/queryKeys";
import MetricTile from "../../shared/components/MetricTile";
import { useI18n } from "../../shared/i18n";

type WarehouseSummary = {
  id: string;
  name: string;
  code: string;
  timezone: string;
  is_active: boolean;
};

type ValidationResult = {
  warehouse_id: string;
  warehouse_found?: boolean;
  total_agv_locations: number;
  valid: number;
  issues: Array<{ location_id?: string; barcode?: string; issue: string }>;
  planner_profile?: {
    aisle_width_m: number;
    agv_turning_radius_m: number;
    rack_height_m: number;
    beam_capacity_kg: number;
  } | null;
  ready: boolean;
};

type WcsBinding = {
  id: string;
  task_id: string;
  warehouse_id: string;
  wcs_task_id?: string | null;
  wcs_step_id?: string | null;
  task_psn?: string | null;
  agv_unit_id?: string | null;
  status?: string | null;
  start_pos?: string | null;
  end_pos?: string | null;
  last_step_status?: number | null;
  last_step_status_name?: string | null;
  failure_reason?: string | null;
  last_callback_at?: string | null;
};

export default function AgvPage() {
  const { t } = useI18n();
  const { data: warehousePage } = useQuery({
    queryKey: queryKeys.agv.warehouses(),
    queryFn: () => fetchWarehouses(),
  });

  const warehouses: WarehouseSummary[] = warehousePage?.items || [];
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string>("");

  const activeWarehouseId = selectedWarehouseId || warehouses[0]?.id || "";
  const activeWarehouse = warehouses.find((w) => w.id === activeWarehouseId) || null;

  const { data: tasks = [] } = useQuery({
    queryKey: queryKeys.agv.pendingTasksPreview(activeWarehouseId),
    enabled: !!activeWarehouseId,
    queryFn: () => fetchAgvPendingTasks({ warehouse_id: activeWarehouseId, limit: 10 }),
  });

  const { data: validation } = useQuery<ValidationResult>({
    queryKey: queryKeys.agv.validation(activeWarehouseId),
    enabled: !!activeWarehouseId,
    queryFn: () => fetchAgvLocationValidation(activeWarehouseId),
  });

  const { data: wcsBindingPage } = useQuery<{ count: number; items: WcsBinding[] }>({
    queryKey: queryKeys.agv.wcsBindings(activeWarehouseId),
    enabled: !!activeWarehouseId,
    queryFn: () => fetchWcsBindings({ warehouse_id: activeWarehouseId, limit: 8 }),
  });

  const hasWarehouses = warehouses.length > 0;
  const hasAgvMap = !!validation && validation.total_agv_locations > 0;
  const isReady = !!validation?.ready;
  const wcsBindings = wcsBindingPage?.items || [];
  const latestWcsBinding = wcsBindings[0] || null;
  const wcsActiveCount = wcsBindings.filter((binding) => ["assigned", "in_progress", "paused"].includes(String(binding.status || ""))).length;
  const wcsExceptionCount = wcsBindings.filter((binding) => ["failed", "error", "cancelled"].includes(String(binding.status || ""))).length;
  const statusTone = !hasWarehouses
    ? "warn"
    : !validation
      ? "idle"
      : isReady
        ? "ready"
        : hasAgvMap
          ? "warn"
          : "not_configured";

  const readinessLabel = !hasWarehouses
    ? t("agv.noWarehouse", "No warehouse")
    : isReady
      ? t("agv.ready", "Ready")
      : hasAgvMap
        ? t("agv.needsFixes", "Needs fixes")
        : t("agv.notConfigured", "Not configured");

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_60%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">
              {t("agv.eyebrow", "Automation readiness")}
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#f5efe5]">
              {t("agv.title", "AGV")}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#c7d4dc]">
              {t(
                "agv.heroBody",
                "Use this page to evaluate whether a real warehouse is ready for AGV-style task handoff. The system should only claim readiness when there is an actual warehouse map, usable coordinates, and a trustworthy task contract.",
              )}
            </p>
          </div>
          <StatusPill tone={statusTone} text={readinessLabel} />
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <FlowCard
            icon={Boxes}
            title={t("agv.card1Title", "Structured tasks")}
            text={t("agv.card1Body", "AGV handoff only matters once warehouse work is already modeled cleanly.")}
          />
          <FlowCard
            icon={MapPinned}
            title={t("agv.card2Title", "Warehouse map")}
            text={t("agv.card2Body", "Coordinates and AGV-accessible locations are the actual readiness layer.")}
          />
          <FlowCard
            icon={Route}
            title={t("agv.card3Title", "Task contract")}
            text={t("agv.card3Body", "Schedulers should consume the same task API your operation already trusts.")}
          />
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile density="compact" label={t("agv.pendingTasks", "Pending AGV tasks")} value={Array.isArray(tasks) ? tasks.length : 0} />
        <MetricTile density="compact" label={t("agv.locations", "AGV locations")} value={validation?.total_agv_locations ?? 0} />
        <MetricTile density="compact" label={t("agv.readiness", "Readiness")} value={readinessLabel} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
              <MapPinned size={18} />
            </div>
            <div>
              <p className="text-sm font-semibold text-[#13212c]">{t("agv.contextTitle", "Warehouse context")}</p>
              <p className="text-sm text-[#61717d]">
                {t(
                  "agv.contextBody",
                  "Anchor AGV readiness to a real warehouse, not a placeholder record. Choose the site you actually want to validate.",
                )}
              </p>
            </div>
          </div>

          {hasWarehouses ? (
            <div className="mt-5 space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-[#334351]">{t("agv.warehouse", "Warehouse")}</label>
                <select
                  value={activeWarehouseId}
                  onChange={(e) => setSelectedWarehouseId(e.target.value)}
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                >
                  {warehouses.map((warehouse) => (
                    <option key={warehouse.id} value={warehouse.id}>
                      {warehouse.name} ({warehouse.code})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
                <div className="rounded-[1.3rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4">
                  <p className="text-sm font-semibold text-[#13212c]">{activeWarehouse?.name}</p>
                  <p className="mt-1 text-sm text-[#61717d]">
                    {t("common.code", "Code")}: {activeWarehouse?.code} · Timezone: {activeWarehouse?.timezone}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-[#61717d]">
                    {validation?.warehouse_found === false
                      ? t("agv.contextMissing", "This warehouse does not have a valid AGV validation context yet.")
                      : t("agv.contextReady", "This is the live warehouse context used to validate map quality and downstream task handoff.")}
                  </p>
                </div>
                <div className="rounded-[1.3rem] border border-[#13212c]/8 bg-white px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{t("agv.nextStep", "Next step")}</p>
                  <p className="mt-2 text-base font-semibold text-[#13212c]">
                    {isReady
                      ? t("agv.nextStepReady", "Keep the map current")
                      : hasAgvMap
                        ? t("agv.nextStepFix", "Fix map issues")
                        : t("agv.nextStepMap", "Map AGV-ready zones")}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#61717d]">
                    {isReady
                      ? t("agv.nextStepReadyBody", "Your map exists. Keep coordinates and operator routes aligned with real floor changes.")
                      : hasAgvMap
                        ? t("agv.nextStepFixBody", "You already have AGV-ready locations. Resolve the validation issues before using readiness as a customer-facing signal.")
                        : t("agv.nextStepMapBody", "Start in Warehouse Planner, agree on AGV-capable zones, then add location coordinates before routing robots.")}
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
              {t(
                "agv.noWarehouseBody",
                "No warehouse is configured yet. Create a warehouse in setup before using AGV readiness as a customer-facing signal.",
              )}
            </div>
          )}
        </section>

        <section className="space-y-6">
          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
                <Bot size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("agv.snapshot", "Readiness snapshot")}</p>
                <p className="text-sm text-[#61717d]">
                  {t(
                    "agv.snapshotBody",
                    "Treat AGV as an operating capability, not just a marketing label. The readiness signal should be defendable.",
                  )}
                </p>
              </div>
            </div>

            <div className="mt-4 grid gap-3">
              <HintCard
                icon={ScanSearch}
                title={t("agv.hint1Title", "Map validation")}
                text={t("agv.hint1Body", "Every AGV-accessible location should have usable coordinates and a believable route context.")}
              />
              <HintCard
                icon={Bot}
                title={t("agv.hint2Title", "Task integration")}
                text={t("agv.hint2Body", "Pending tasks only matter after a warehouse is chosen, mapped, and trusted by operators.")}
              />
            </div>

            {validation?.planner_profile ? (
              <div className="mt-5 rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{t("agv.physicalConstraints", "Physical constraints")}</p>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <ConstraintChip label={t("agv.aisleWidth", "Aisle width")} value={`${validation.planner_profile.aisle_width_m} m`} />
                  <ConstraintChip label={t("agv.turningRadius", "Turning radius")} value={`${validation.planner_profile.agv_turning_radius_m} m`} />
                  <ConstraintChip label={t("agv.rackHeight", "Rack height")} value={`${validation.planner_profile.rack_height_m} m`} />
                  <ConstraintChip label={t("agv.beamCapacity", "Beam capacity")} value={`${validation.planner_profile.beam_capacity_kg} kg`} />
                </div>
              </div>
            ) : null}
          </div>

          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("agv.howToUse", "How to use this page")}</p>
            <div className="mt-4 space-y-3">
              <GuideRow
                label={t("agv.guide1Title", "1. Stabilize manual flow first")}
                detail={t("agv.guide1Body", "Robotics should layer onto a workflow your operators already trust.")}
              />
              <GuideRow
                label={t("agv.guide2Title", "2. Validate map quality")}
                detail={t("agv.guide2Body", "Location coordinates and reachability are the real AGV foundation.")}
              />
              <GuideRow
                label={t("agv.guide3Title", "3. Use task APIs as the contract")}
                detail={t("agv.guide3Body", "Automation should consume the same task model the warehouse runs today.")}
              />
            </div>
          </div>
        </section>
      </div>

      <section className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("agv.wcsEyebrow", "WCS handoff")}</p>
            <h2 className="mt-2 text-xl font-semibold text-[#13212c]">{t("agv.wcsTitle", "AGV task recovery")}</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <MiniMetric label={t("agv.wcsBindings", "Bindings")} value={String(wcsBindings.length)} />
            <MiniMetric label={t("agv.wcsActive", "Active")} value={String(wcsActiveCount)} />
            <MiniMetric label={t("agv.wcsExceptions", "Exceptions")} value={String(wcsExceptionCount)} tone={wcsExceptionCount ? "warn" : "default"} />
          </div>
        </div>

        {latestWcsBinding ? (
          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="rounded-[1.3rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <BindingField label={t("agv.wcsTask", "WCS task")} value={latestWcsBinding.wcs_task_id || latestWcsBinding.task_id} />
                <BindingField label={t("agv.wcsStep", "Current step")} value={latestWcsBinding.last_step_status_name || latestWcsBinding.status || "assigned"} />
                <BindingField label={t("agv.wcsAgv", "AGV unit")} value={latestWcsBinding.agv_unit_id || "wcs"} />
                <BindingField label={t("agv.wcsCallback", "Last callback")} value={latestWcsBinding.last_callback_at || "not received"} />
              </div>
              <div className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-white px-3 py-3 text-sm text-[#334351]">
                <span className="font-semibold text-[#13212c]">{latestWcsBinding.task_psn || latestWcsBinding.task_id}</span>
                <span className="mx-2 text-[#7e8d98]">·</span>
                <span>{latestWcsBinding.start_pos || "source"} → {latestWcsBinding.end_pos || "destination"}</span>
              </div>
              {latestWcsBinding.failure_reason ? (
                <div className="mt-3 rounded-[1rem] border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
                  {latestWcsBinding.failure_reason}
                </div>
              ) : null}
            </div>
            <RecoveryPath
              title={wcsExceptionCount ? t("agv.wcsRecoveryTitle", "Recover this handoff") : t("agv.wcsRecoveryReadyTitle", "Safe next actions")}
              actions={[
                t("agv.wcsRecoveryPreview", "Run dispatch preview"),
                t("agv.wcsRecoveryHuman", "Switch to human"),
                t("agv.wcsRecoveryCancel", "Cancel local binding"),
                t("agv.wcsRecoveryContact", "Contact WCS"),
              ]}
            />
          </div>
        ) : (
          <div className="mt-5 rounded-[1.3rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm text-[#61717d]">
            {t("agv.wcsEmpty", "No WCS task binding exists for this warehouse yet. Run a dispatch dry-run before creating the first live sandbox task.")}
          </div>
        )}
      </section>

      {validation && validation.issues.length > 0 && (
        <div className="rounded-[1.8rem] border border-amber-200 bg-amber-50 p-6">
          <p className="text-sm font-semibold text-amber-950">
            {t("agv.issuesTitle", "AGV issues to fix before calling this warehouse ready")}
          </p>
          <div className="mt-3 space-y-2 text-sm text-amber-900">
            {validation.issues.map((issue, index) => (
              <p key={`${issue.issue}-${issue.location_id || index}`}>
                {issue.barcode || issue.location_id || t("agv.warehouseFallback", "Warehouse")}: {issue.issue.replace(/_/g, " ")}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ConstraintChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-3 py-3">
      <p className="text-[11px] uppercase tracking-[0.14em] text-[#7e8d98]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}

function MiniMetric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "warn" }) {
  return (
    <div className={`rounded-[1rem] border px-4 py-3 ${tone === "warn" ? "border-amber-200 bg-amber-50" : "border-[#13212c]/8 bg-[#f7f4ee]"}`}>
      <p className="text-[11px] uppercase tracking-[0.14em] text-[#7e8d98]">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${tone === "warn" ? "text-amber-900" : "text-[#13212c]"}`}>{value}</p>
    </div>
  );
}

function BindingField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-[0.14em] text-[#7e8d98]">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}

function RecoveryPath({ title, actions }: { title: string; actions: string[] }) {
  return (
    <div className="rounded-[1.3rem] border border-[#13212c]/8 bg-white p-4">
      <p className="text-sm font-semibold text-[#13212c]">{title}</p>
      <div className="mt-3 grid gap-2">
        {actions.map((action) => (
          <div key={action} className="flex items-center justify-between gap-3 rounded-[0.9rem] border border-[#13212c]/8 bg-[#f7f4ee] px-3 py-2 text-sm font-medium text-[#334351]">
            <span>{action}</span>
            <ArrowRight size={14} className="shrink-0 text-[#61717d]" />
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusPill({
  tone,
  text,
}: {
  tone: "ready" | "warn" | "not_configured" | "idle";
  text: string;
}) {
  const config = {
    ready: {
      className: "border-emerald-300/35 bg-emerald-300/12 text-emerald-200",
      icon: CheckCircle2,
    },
    warn: {
      className: "border-amber-300/35 bg-amber-300/12 text-amber-200",
      icon: AlertTriangle,
    },
    not_configured: {
      className: "border-slate-300/25 bg-slate-200/10 text-slate-200",
      icon: AlertTriangle,
    },
    idle: {
      className: "border-slate-300/25 bg-slate-200/10 text-slate-200",
      icon: AlertTriangle,
    },
  }[tone];

  const Icon = config.icon;

  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${config.className}`}>
      <Icon size={13} />
      {text}
    </div>
  );
}

function FlowCard({ icon: Icon, title, text }: { icon: any; title: string; text: string }) {
  return (
    <div className="rounded-[1.4rem] border border-white/10 bg-white/5 p-4">
      <div className="inline-flex rounded-2xl border border-[#f7bf45]/30 bg-[#f7bf45]/10 p-2.5 text-[#f7bf45]">
        <Icon size={18} />
      </div>
      <p className="mt-4 text-lg font-semibold text-[#f5efe5]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#c4d3dc]">{text}</p>
    </div>
  );
}

function GuideRow({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-[#13212c]">{label}</p>
          <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{detail}</p>
        </div>
        <ArrowRight size={15} className="mt-1 shrink-0 text-[#13212c]" />
      </div>
    </div>
  );
}

function HintCard({ icon: Icon, title, text }: { icon: any; title: string; text: string }) {
  return (
    <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
          <Icon size={16} />
        </div>
        <div>
          <p className="text-sm font-semibold text-[#13212c]">{title}</p>
          <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{text}</p>
        </div>
      </div>
    </div>
  );
}
