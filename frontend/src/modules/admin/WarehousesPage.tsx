import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, MapPinned, Plus, Ruler, Warehouse } from "lucide-react";
import { queryKeys } from "../../shared/api/queryKeys";
import { createWarehouse as createWarehouseRequest, fetchWarehouseZones, fetchWarehousesPage } from "../../shared/api/planner";
import { getApiErrorMessage } from "../../shared/api/error-message";
import DataTable from "../../shared/components/DataTable";
import { useI18n } from "../../shared/i18n";
import { sortTableRows, type SortDirection } from "../../shared/utils/tableSort";

type WarehouseRow = {
  id: string;
  name: string;
  code: string;
  timezone: string;
  is_active: boolean;
};

type ZoneRow = {
  id: string;
  warehouse_id: string;
  name: string;
  code: string;
  is_agv_zone: boolean;
  sequence: number;
  location_count: number;
};

type WarehouseSortField = "name" | "code" | "timezone" | "zones" | "locations";

export default function WarehousesPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState({
    name: "",
    code: "",
    timezone: "Europe/Budapest",
  });
  const [warehouseSortField, setWarehouseSortField] = useState<WarehouseSortField>("name");
  const [warehouseSortDirection, setWarehouseSortDirection] = useState<SortDirection>("asc");

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.warehouses.masterData(),
    queryFn: fetchWarehousesPage,
  });

  const warehouses: WarehouseRow[] = data?.items || [];

  const zoneQueries = useQuery({
    queryKey: queryKeys.warehouses.zoneCounts(warehouses.map((warehouse) => warehouse.id).join(",")),
    queryFn: async () => {
      const entries = await Promise.all(
        warehouses.map(async (warehouse) => {
          const zones = await fetchWarehouseZones(warehouse.id);
          return [warehouse.id, zones as ZoneRow[]] as const;
        }),
      );
      return Object.fromEntries(entries);
    },
    enabled: warehouses.length > 0,
  });

  const zoneMap = zoneQueries.data || {};
  const getWarehouseLocationCount = (warehouse: WarehouseRow) =>
    zoneMap[warehouse.id]?.reduce((sum: number, zone: ZoneRow) => sum + (zone.location_count || 0), 0) || 0;
  const getWarehouseComparable = (warehouse: WarehouseRow) => {
    if (warehouseSortField === "zones") return zoneMap[warehouse.id]?.length || 0;
    if (warehouseSortField === "locations") return getWarehouseLocationCount(warehouse);
    return warehouse[warehouseSortField] ?? "";
  };
  const sortedWarehouses = useMemo(
    () => sortTableRows(warehouses, getWarehouseComparable, warehouseSortDirection),
    [warehouseSortDirection, warehouseSortField, warehouses, zoneMap],
  );
  const handleWarehouseHeaderClick = (key: string) => {
    if (!["name", "code", "timezone", "zones", "locations"].includes(key)) return;
    if (warehouseSortField === key) {
      setWarehouseSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setWarehouseSortField(key as WarehouseSortField);
    setWarehouseSortDirection("asc");
  };

  const warehouseMetrics = useMemo(() => {
    const active = warehouses.filter((warehouse) => warehouse.is_active).length;
    const zones = warehouses.reduce((sum, warehouse) => sum + (zoneMap[warehouse.id]?.length || 0), 0);
    const locations = warehouses.reduce(
      (sum, warehouse) =>
        sum +
        (zoneMap[warehouse.id]?.reduce((zoneTotal, zone) => zoneTotal + (zone.location_count || 0), 0) || 0),
      0,
    );
    return { active, zones, locations };
  }, [warehouses, zoneMap]);

  const createWarehouse = useMutation({
    mutationFn: async () => createWarehouseRequest(form),
    onSuccess: async () => {
      setError("");
      setSuccess(t("warehouses.created", "Warehouse created."));
      setForm({ name: "", code: "", timezone: "Europe/Budapest" });
      await queryClient.invalidateQueries({ queryKey: queryKeys.warehouses.masterData() });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("warehouses.createError", "Could not create the warehouse.")));
    },
  });

  const columns = [
    {
      key: "__row_number",
      header: t("common.rowNumber", "No."),
      className: "w-[72px] text-[#7f8d98]",
      render: (_row: WarehouseRow, index: number) => index + 1,
    },
    { key: "name", header: t("common.warehouse", "Warehouse"), sortable: true },
    { key: "code", header: t("common.code", "Code"), sortable: true },
    { key: "timezone", header: t("warehouses.timezone", "Timezone"), sortable: true },
    {
      key: "zones",
      header: t("warehouses.zones", "Zones"),
      sortable: true,
      render: (row: WarehouseRow) => zoneMap[row.id]?.length || 0,
    },
    {
      key: "locations",
      header: t("warehouses.locations", "Locations"),
      sortable: true,
      render: (row: WarehouseRow) => getWarehouseLocationCount(row),
    },
    {
      key: "actions",
      header: t("common.next", "Next"),
      render: () => (
        <div className="flex flex-wrap gap-2">
          <a
            href="/warehouse-planner"
            className="inline-flex items-center rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-[#13212c]"
          >
            {t("warehouses.openPlanner", "Open planner")}
          </a>
          <a
            href="/setup?step=locations"
            className="inline-flex items-center rounded-full bg-[#13212c] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-[#f4efe8]"
          >
            {t("warehouses.editSetup", "Edit setup")}
          </a>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_60%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">
              {t("warehouses.eyebrow", "Master data")}
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#f5efe5]">
              {t("warehouses.title", "Warehouses")}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#c7d4dc]">
              {t(
                "warehouses.body",
                "Maintain warehouse master records here after setup. Use the warehouse planner to adjust zones, storage logic, AGV constraints, and physical layout once the core warehouse record exists.",
              )}
            </p>
          </div>
          <div className="rounded-[1.4rem] border border-white/10 bg-white/5 p-4 lg:max-w-sm">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#9db1bf]">
              {t("warehouses.maintenanceMap", "Maintenance map")}
            </p>
            <p className="mt-2 text-sm leading-6 text-[#d2dde4]">
              {t(
                "warehouses.maintenanceBody",
                "Use this page for warehouse identity and timezone. Use Warehouse Planner for zones, locations, aisle logic, AGV readiness, and storage rules.",
              )}
            </p>
          </div>
        </div>
      </section>

      <div
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="warehouses-mobile-governance"
        data-admin-mobile-contract="warehouse-desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("warehouses.mobileManagementNoticeTitle", "Warehouse master data is desktop-first")}
        </p>
        <p className="mt-1">
          {t("warehouses.mobileManagementNoticeBody", "Use this phone view to confirm warehouse identity and counts. Create warehouses, zones, locations, and planner rules on iPad or desktop.")}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard icon={Warehouse} label={t("warehouses.metricWarehouses", "Warehouses")} value={warehouseMetrics.active} />
        <MetricCard icon={MapPinned} label={t("warehouses.metricZones", "Zones")} value={warehouseMetrics.zones} />
        <MetricCard icon={Ruler} label={t("warehouses.metricLocations", "Locations")} value={warehouseMetrics.locations} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_380px]">
        <details
          className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/85 px-4 py-3 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:hidden"
          data-testid="warehouses-mobile-add-collapsed"
        >
          <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
            {t("warehouses.mobileAddWarehouseSummary", "Add warehouse is desktop-preferred")}
          </summary>
          <p className="mt-2 text-sm leading-6 text-[#61717d]">
            {t("warehouses.mobileAddWarehouseBody", "Phone review is for warehouse identity and readiness. Create records, zones, locations, planner rules, and AGV constraints on iPad or desktop.")}
          </p>
        </details>

        <section className="hidden rounded-[1.8rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[#f7bf45]/28 bg-[#f7bf45]/12 p-2.5 text-[#d19009]">
              <Plus size={18} />
            </div>
            <div>
              <p className="text-sm font-semibold text-[#13212c]">{t("warehouses.addWarehouse", "Add warehouse")}</p>
              <p className="text-sm text-[#61717d]">
                {t(
                  "warehouses.addWarehouseBody",
                  "Create the warehouse record here, then move into planner or setup to define aisle, rack, level, zone, and AGV-specific structure.",
                )}
              </p>
            </div>
          </div>

          {error ? (
            <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
          ) : null}
          {success ? (
            <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{success}</p>
          ) : null}

          <div className="mt-5 space-y-4">
            <Field label={t("common.warehouse", "Warehouse")}>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={t("warehouses.namePlaceholder", "Budapest Fulfillment Center")}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            <Field label={t("common.code", "Code")}>
              <input
                type="text"
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                placeholder={t("warehouses.codePlaceholder", "BUD-01")}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            <Field label={t("warehouses.timezone", "Timezone")}>
              <input
                type="text"
                value={form.timezone}
                onChange={(e) => setForm({ ...form, timezone: e.target.value })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>

            <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3 text-sm leading-6 text-[#61717d]">
              {t(
                "warehouses.note",
                "Warehouse identity lives here. Storage layout, AGV constraints, and location design continue in Warehouse Planner so operators do not have to revisit onboarding every time they make a physical change.",
              )}
            </div>

            <button
              type="button"
              disabled={createWarehouse.isPending || !form.name || !form.code || !form.timezone}
              onClick={() => createWarehouse.mutate()}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040] disabled:opacity-50"
            >
              {createWarehouse.isPending ? t("warehouses.creating", "Creating warehouse...") : t("warehouses.create", "Create warehouse")}
              <ArrowRight size={15} />
            </button>
          </div>
        </section>

        <section className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("warehouses.guide", "How to maintain later")}</p>
          <div className="mt-4 space-y-3">
            <GuideRow label={t("warehouses.guide1Title", "1. Keep one warehouse record per site")} detail={t("warehouses.guide1Detail", "Use this page for the site name, code, and timezone that the rest of the system depends on.")} />
            <GuideRow label={t("warehouses.guide2Title", "2. Move to planner for layout changes")} detail={t("warehouses.guide2Detail", "Zones, locations, AGV paths, aisle width, and rack constraints belong in the planner rather than here.")} />
            <GuideRow label={t("warehouses.guide3Title", "3. Revisit setup only for guided generation")} detail={t("warehouses.guide3Detail", "Use setup when you want the system to regenerate a starter location skeleton, not for day-to-day master data maintenance.")} />
          </div>
        </section>
      </div>

      <DataTable
        columns={columns}
        data={sortedWarehouses}
        loading={isLoading || zoneQueries.isLoading}
        onHeaderClick={handleWarehouseHeaderClick}
        sortField={warehouseSortField}
        sortDirection={warehouseSortDirection}
        emptyMessage={t("warehouses.empty", "No warehouses created yet")}
        emptyHint={t("warehouses.emptyHint", "Create the warehouse record first, then continue into shelf, zone, and AGV planning from the warehouse planner.")}
        emptyActionLabel={t("warehouses.emptyAction", "Create your first warehouse")}
        emptyActionHref="/setup?step=warehouse"
      />
    </div>
  );
}

function MetricCard({ icon: Icon, label, value }: { icon: any; label: string; value: number }) {
  return (
    <div className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/84 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.05)]">
      <div className="inline-flex rounded-2xl border border-[#13212c]/10 bg-[#f7f4ee] p-2.5 text-[#13212c]">
        <Icon size={18} />
      </div>
      <p className="mt-4 text-xs uppercase tracking-[0.18em] text-[#7b8893]">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{value}</p>
    </div>
  );
}

function GuideRow({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3">
      <p className="text-sm font-semibold text-[#13212c]">{label}</p>
      <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-[#334351]">{label}</span>
      {children}
    </label>
  );
}
