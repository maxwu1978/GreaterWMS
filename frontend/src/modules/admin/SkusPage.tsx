import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Boxes, PackageSearch, ScanLine } from "lucide-react";
import { createSku as createSkuRequest, fetchSkusPage } from "../../shared/api/skus";
import { fetchClients } from "../../shared/api/clients";
import { queryKeys } from "../../shared/api/queryKeys";
import { getApiErrorMessage } from "../../shared/api/error-message";
import DataTable from "../../shared/components/DataTable";
import { useI18n } from "../../shared/i18n";
import { sortTableRows, type SortDirection } from "../../shared/utils/tableSort";

type ClientRow = {
  id: string;
  name: string;
  code: string;
};

type SkuRow = {
  id: string;
  client_id: string;
  sku_code: string;
  name: string;
  barcode: string | null;
  weight_kg: number | null;
  requires_lot: boolean;
  requires_expiry: boolean;
};

type SkuSortField = "sku_code" | "name" | "client_id" | "barcode" | "weight_kg" | "tracking";

export default function SkusPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState({
    client_id: "",
    sku_code: "",
    name: "",
    barcode: "",
    weight_kg: "",
    requires_lot: false,
    requires_expiry: false,
  });
  const [skuSortField, setSkuSortField] = useState<SkuSortField>("sku_code");
  const [skuSortDirection, setSkuSortDirection] = useState<SortDirection>("asc");

  const { data: clientPage } = useQuery({
    queryKey: queryKeys.skus.masterClients(),
    queryFn: () => fetchClients({ limit: 500 }),
  });

  const { data: skuPage, isLoading } = useQuery({
    queryKey: queryKeys.skus.masterList(),
    queryFn: fetchSkusPage,
  });

  const clients: ClientRow[] = clientPage?.items || [];
  const skus: SkuRow[] = skuPage?.items || [];
  const clientNameMap = useMemo(() => Object.fromEntries(clients.map((client) => [client.id, client.name])), [clients]);
  const getSkuComparable = (sku: SkuRow) => {
    if (skuSortField === "client_id") return clientNameMap[sku.client_id] || sku.client_id;
    if (skuSortField === "tracking") {
      if (sku.requires_lot && sku.requires_expiry) return "lot expiry";
      if (sku.requires_lot) return "lot";
      if (sku.requires_expiry) return "expiry";
      return "standard";
    }
    return sku[skuSortField] ?? "";
  };
  const sortedSkus = useMemo(
    () => sortTableRows(skus, getSkuComparable, skuSortDirection),
    [clientNameMap, skuSortDirection, skuSortField, skus],
  );
  const handleSkuHeaderClick = (key: string) => {
    if (!["sku_code", "name", "client_id", "barcode", "weight_kg", "tracking"].includes(key)) return;
    if (skuSortField === key) {
      setSkuSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSkuSortField(key as SkuSortField);
    setSkuSortDirection("asc");
  };

  const createSku = useMutation({
    mutationFn: async () =>
      createSkuRequest({
        client_id: form.client_id,
        sku_code: form.sku_code,
        name: form.name,
        barcode: form.barcode || null,
        weight_kg: form.weight_kg ? Number(form.weight_kg) : null,
        requires_lot: form.requires_lot,
        requires_expiry: form.requires_expiry,
      }),
    onSuccess: async () => {
      setError("");
      setSuccess(t("skus.created", "SKU created."));
      setForm({
        client_id: "",
        sku_code: "",
        name: "",
        barcode: "",
        weight_kg: "",
        requires_lot: false,
        requires_expiry: false,
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.skus.masterList() });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("skus.createError", "Could not create the SKU.")));
    },
  });

  const columns = [
    {
      key: "__row_number",
      header: t("common.rowNumber", "No."),
      className: "w-[72px] text-[#7f8d98]",
      render: (_row: SkuRow, index: number) => index + 1,
    },
    { key: "sku_code", header: t("common.sku", "SKU"), sortable: true },
    { key: "name", header: t("common.name", "Name"), sortable: true },
    {
      key: "client_id",
      header: t("common.client", "Client"),
      sortable: true,
      render: (row: SkuRow) => clientNameMap[row.client_id] || row.client_id,
    },
    {
      key: "barcode",
      header: t("skus.barcode", "Barcode"),
      sortable: true,
      render: (row: SkuRow) => row.barcode || "—",
    },
    {
      key: "weight_kg",
      header: t("skus.weight", "Weight (kg)"),
      sortable: true,
      render: (row: SkuRow) => (row.weight_kg ? `${row.weight_kg}` : "—"),
    },
    {
      key: "tracking",
      header: t("skus.tracking", "Tracking"),
      sortable: true,
      render: (row: SkuRow) => {
        const parts = [
          row.requires_lot ? t("skus.lot", "Lot") : null,
          row.requires_expiry ? t("skus.expiry", "Expiry") : null,
        ].filter(Boolean);
        return parts.length ? parts.join(" + ") : t("skus.standard", "Standard");
      },
    },
  ];

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_60%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">
              {t("skus.eyebrow", "Master data")}
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#f5efe5]">
              {t("skus.title", "SKUs")}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#c7d4dc]">
              {t(
                "skus.body",
                "Maintain the product master here after setup. SKU definitions give receiving, inventory, picking, billing, and portal visibility a stable operational identity.",
              )}
            </p>
          </div>
          <div className="rounded-[1.4rem] border border-white/10 bg-white/5 p-4 lg:max-w-sm">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#9db1bf]">
              {t("skus.maintenanceMap", "Maintenance map")}
            </p>
            <p className="mt-2 text-sm leading-6 text-[#d2dde4]">
              {t(
                "skus.maintenanceBody",
                "Use setup for first-load guidance, then return here when a client launches a new item, changes barcode structure, or needs lot and expiry tracking updated.",
              )}
            </p>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard icon={Boxes} label={t("skus.metricSkus", "SKUs")} value={skus.length} />
        <MetricCard icon={PackageSearch} label={t("skus.metricTrackedLots", "Lot tracked")} value={skus.filter((sku) => sku.requires_lot).length} />
        <MetricCard icon={ScanLine} label={t("skus.metricBarcoded", "Barcoded")} value={skus.filter((sku) => sku.barcode).length} />
      </div>

      <div
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="desktop-first-mobile-notice"
        data-admin-mobile-contract="sku-desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("skus.mobileManagementNoticeTitle", "SKU master data is a management workspace")}
        </p>
        <p className="mt-1">
          {t(
            "skus.mobileManagementNoticeBody",
            "Use this phone view to confirm an item exists. Add or maintain detailed SKU records on iPad or desktop before warehouse execution.",
          )}
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_380px]">
        <details
          className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/85 px-4 py-3 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:hidden"
          data-testid="skus-mobile-add-collapsed"
        >
          <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
            {t("skus.mobileAddSkuSummary", "Add SKU is desktop-preferred")}
          </summary>
          <p className="mt-2 text-sm leading-6 text-[#61717d]">
            {t("skus.mobileAddSkuBody", "Use phone to confirm an item exists. Add SKU records, barcode details, weight, lot tracking, and expiry rules on iPad or desktop.")}
          </p>
        </details>

        <section className="hidden rounded-[1.8rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
              <Boxes size={18} />
            </div>
            <div>
              <p className="text-sm font-semibold text-[#13212c]">{t("skus.addSku", "Add SKU")}</p>
              <p className="text-sm text-[#61717d]">
                {t(
                  "skus.addSkuBody",
                  "Create the live product definition here so receiving, stock control, and outbound work can point to the same item identity.",
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
            <Field label={t("common.client", "Client")}>
              <select
                value={form.client_id}
                onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              >
                <option value="">{t("skus.selectClient", "Select a client")}</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name} ({client.code})
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("common.sku", "SKU")}>
              <input
                type="text"
                value={form.sku_code}
                onChange={(e) => setForm({ ...form, sku_code: e.target.value.toUpperCase() })}
                placeholder={t("skus.codePlaceholder", "SKU-1001")}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            <Field label={t("common.name", "Name")}>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={t("skus.namePlaceholder", "Frozen dumplings 500g")}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label={t("skus.barcode", "Barcode")}>
                <input
                  type="text"
                  value={form.barcode}
                  onChange={(e) => setForm({ ...form, barcode: e.target.value })}
                  placeholder={t("skus.barcodePlaceholder", "5991234567890")}
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                />
              </Field>
              <Field label={t("skus.weight", "Weight (kg)")}>
                <input
                  type="number"
                  step="0.01"
                  value={form.weight_kg}
                  onChange={(e) => setForm({ ...form, weight_kg: e.target.value })}
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                />
              </Field>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-center gap-3 rounded-[1.25rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm text-[#13212c]">
                <input
                  type="checkbox"
                  checked={form.requires_lot}
                  onChange={(e) => setForm({ ...form, requires_lot: e.target.checked })}
                />
                {t("skus.requiresLot", "Track lot numbers")}
              </label>
              <label className="flex items-center gap-3 rounded-[1.25rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm text-[#13212c]">
                <input
                  type="checkbox"
                  checked={form.requires_expiry}
                  onChange={(e) => setForm({ ...form, requires_expiry: e.target.checked })}
                />
                {t("skus.requiresExpiry", "Track expiry dates")}
              </label>
            </div>

            <button
              type="button"
              disabled={createSku.isPending || !form.client_id || !form.sku_code || !form.name}
              onClick={() => createSku.mutate()}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040] disabled:opacity-50"
            >
              {createSku.isPending ? t("skus.creating", "Creating SKU...") : t("skus.create", "Create SKU")}
              <ArrowRight size={15} />
            </button>
          </div>
        </section>

        <section className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("skus.guide", "How to maintain later")}</p>
          <div className="mt-4 space-y-3">
            <GuideRow label={t("skus.guide1Title", "1. Add SKU before live receiving")} detail={t("skus.guide1Detail", "Inbound should not rely on ad hoc product names. Create the product master first so receiving and inventory stay aligned.")} />
            <GuideRow label={t("skus.guide2Title", "2. Link every SKU to a client")} detail={t("skus.guide2Detail", "A 3PL product belongs inside a client account even if the physical item seems shared across warehouses.")} />
            <GuideRow label={t("skus.guide3Title", "3. Use lot and expiry only when needed")} detail={t("skus.guide3Detail", "Turn on stricter tracking for the products that actually require it, rather than overcomplicating every item.")} />
          </div>
        </section>
      </div>

      <DataTable
        columns={columns}
        data={sortedSkus}
        loading={isLoading}
        onHeaderClick={handleSkuHeaderClick}
        sortField={skuSortField}
        sortDirection={skuSortDirection}
        emptyMessage={t("skus.empty", "No SKUs configured yet")}
        emptyHint={t("skus.emptyHint", "Create the first product master before starting real receiving, putaway, or outbound work.")}
        emptyActionLabel={t("skus.emptyAction", "Create your first SKU")}
        emptyActionHref="/setup?step=skus"
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
