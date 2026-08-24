import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  Database,
  FileSpreadsheet,
  FileUp,
  Link2,
  ShieldCheck,
  Upload,
  WandSparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import api from "../../shared/api/client";
import { queryKeys } from "../../shared/api/queryKeys";
import {
  createManualInboundOrder,
  createManualInventory,
  fetchClientSkus,
  fetchMigrationClients,
  importInboundCsv,
  importInventoryCsv,
  importOutboundCsv,
  previewInboundCsv,
  previewOutboundCsv,
} from "../../shared/api/migration";
import { createOutboundOrder } from "../../shared/api/outboundOrders";
import { fetchWarehouses, fetchWarehouseLocations } from "../../shared/api/planner";
import { fetchSetupProgress } from "../../shared/api/setup";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import { checklistHref } from "../../shared/utils/checklistHref";

const buildEmptyManualInboundPackage = () => ({
  packageType: "carton",
  quantity: "",
  trackingNumber: "",
  cartonMark: "",
  customerBarcode: "",
});

export default function DataMigrationPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedWarehouseId, setSelectedWarehouseId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  const [inboundFile, setInboundFile] = useState<File | null>(null);
  const [inboundImportError, setInboundImportError] = useState("");
  const [inboundImportSummary, setInboundImportSummary] = useState<{ imported: number; errors: { row: number; error: string }[] } | null>(null);
  const [inboundPreview, setInboundPreview] = useState<{
    headers: string[];
    required_fields: string[];
    optional_fields: string[];
    suggested_mapping: Record<string, string>;
    missing_required: string[];
    sample_rows: Record<string, string>[];
    mapped_preview: Record<string, string>[];
    total_rows: number;
  } | null>(null);
  const [inboundMapping, setInboundMapping] = useState<Record<string, string>>({});
  const [formatName, setFormatName] = useState("");
  const [outboundFile, setOutboundFile] = useState<File | null>(null);
  const [outboundImportError, setOutboundImportError] = useState("");
  const [outboundImportSummary, setOutboundImportSummary] = useState<{ imported: number; errors: { row: number | string; error: string }[] } | null>(null);
  const [outboundPreview, setOutboundPreview] = useState<{
    headers: string[];
    required_fields: string[];
    optional_fields: string[];
    suggested_mapping: Record<string, string>;
    missing_required: string[];
    sample_rows: Record<string, string>[];
    mapped_preview: Record<string, string>[];
    total_rows: number;
  } | null>(null);
  const [outboundMapping, setOutboundMapping] = useState<Record<string, string>>({});
  const [outboundFormatName, setOutboundFormatName] = useState("");

  const [manualInbound, setManualInbound] = useState({
    clientId: "",
    warehouseId: "",
    orderNumber: "",
    referenceNumber: "",
    supplierName: "",
    skuId: "",
    quantity: "1",
    packages: [] as Array<{
      packageType: string;
      quantity: string;
      trackingNumber: string;
      cartonMark: string;
      customerBarcode: string;
    }>,
  });
  const [manualOutbound, setManualOutbound] = useState({
    clientId: "",
    warehouseId: "",
    orderNumber: "",
    referenceNumber: "",
    carrier: "",
    skuId: "",
    quantity: "1",
  });
  const [manualInventory, setManualInventory] = useState({
    warehouseId: "",
    locationBarcode: "",
    skuCode: "",
    quantity: "1",
    lotNumber: "",
  });
  const [manualInboundError, setManualInboundError] = useState("");
  const [manualInboundResult, setManualInboundResult] = useState<{ order_number: string; status: string } | null>(null);
  const [manualOutboundError, setManualOutboundError] = useState("");
  const [manualOutboundResult, setManualOutboundResult] = useState<{ order_number: string; status: string } | null>(null);
  const [manualInventoryError, setManualInventoryError] = useState("");
  const [manualInventoryResult, setManualInventoryResult] = useState<{ sku_code: string; quantity: number; location_barcode: string } | null>(null);

  const { data: warehousePage } = useQuery({
    queryKey: queryKeys.migration.warehouses(),
    queryFn: () => fetchWarehouses(),
  });

  const { data: clientPage } = useQuery({
    queryKey: queryKeys.migration.clients(),
    queryFn: fetchMigrationClients,
  });

  const { data: setupProgress } = useQuery({
    queryKey: queryKeys.setup.progressFor("intake"),
    queryFn: fetchSetupProgress,
  });

  const warehouses = warehousePage?.items || [];
  const clients = clientPage?.items || [];
  const activeWarehouseId = selectedWarehouseId || warehouses[0]?.id || "";
  const activeWarehouse = warehouses.find((warehouse: any) => warehouse.id === activeWarehouseId) || null;
  const setupSteps = setupProgress?.steps || [];
  const importPresetStorageKey = "wms_inbound_import_mapping_shared";
  const outboundImportPresetStorageKey = "wms_outbound_import_mapping_shared";

  const savedImportPreset = useMemo(() => {
    try {
      const raw = localStorage.getItem(importPresetStorageKey);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }, []);

  const savedOutboundImportPreset = useMemo(() => {
    try {
      const raw = localStorage.getItem(outboundImportPresetStorageKey);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }, []);

  const { data: inboundSkuPage } = useQuery({
    queryKey: queryKeys.migration.inboundSkus(manualInbound.clientId),
    enabled: Boolean(manualInbound.clientId),
    queryFn: () => fetchClientSkus(manualInbound.clientId),
  });

  const { data: outboundSkuPage } = useQuery({
    queryKey: queryKeys.migration.outboundSkus(manualOutbound.clientId),
    enabled: Boolean(manualOutbound.clientId),
    queryFn: () => fetchClientSkus(manualOutbound.clientId),
  });

  const { data: warehouseLocations } = useQuery({
    queryKey: queryKeys.migration.warehouseLocations(manualInventory.warehouseId || activeWarehouseId),
    enabled: Boolean(manualInventory.warehouseId || activeWarehouseId),
    queryFn: () => fetchWarehouseLocations(manualInventory.warehouseId || activeWarehouseId),
  });

  const inboundSkus = inboundSkuPage?.items || [];
  const outboundSkus = outboundSkuPage?.items || [];
  const locations = warehouseLocations || [];

  const requiredIntakeSteps = useMemo(
    () => setupSteps.filter((step: any) => ["warehouse", "locations", "client", "skus"].includes(step.name) && !step.done),
    [setupSteps],
  );

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error(t("migration.chooseCsv", "Choose a CSV file first."));
      const form = new FormData();
      form.append("file", file);
      return importInventoryCsv(activeWarehouseId, form);
    },
    onSuccess: (data) => {
      setError("");
      setResult(data);
    },
    onError: (err: any) => {
      setResult(null);
      setError(getApiErrorMessage(err, t("migration.errorImport", "Could not import your inventory file.")));
    },
  });

  const previewInboundMutation = useMutation({
    mutationFn: async () => {
      if (!inboundFile) {
        throw new Error(t("receiving.importSelectFile", "Choose a CSV file first."));
      }
      setInboundImportError("");
      setInboundImportSummary(null);
      const formData = new FormData();
      formData.append("file", inboundFile);
      return previewInboundCsv(formData);
    },
    onSuccess: (data) => {
      setInboundPreview(data);
      const presetMapping = savedImportPreset?.mapping || {};
      const mergedMapping: Record<string, string> = {};
      const validHeaders = new Set(data.headers);
      for (const field of [...data.required_fields, ...data.optional_fields]) {
        const presetHeader = presetMapping[field];
        const suggestedHeader = data.suggested_mapping[field];
        if (presetHeader && validHeaders.has(presetHeader)) mergedMapping[field] = presetHeader;
        else if (suggestedHeader && validHeaders.has(suggestedHeader)) mergedMapping[field] = suggestedHeader;
      }
      setInboundMapping(mergedMapping);
      setFormatName(savedImportPreset?.name || "");
    },
    onError: (err: any) => {
      setInboundPreview(null);
      setInboundImportError(getApiErrorMessage(err, t("receiving.importPreviewFailed", "Failed to preview inbound file.")));
    },
  });

  const importInboundMutation = useMutation({
    mutationFn: async () => {
      if (!inboundFile) {
        throw new Error(t("receiving.importSelectFile", "Choose a CSV file first."));
      }
      if (!inboundPreview) {
        throw new Error(t("receiving.importPreviewFirst", "Preview and map the file before importing."));
      }
      setInboundImportError("");
      setInboundImportSummary(null);
      const formData = new FormData();
      formData.append("file", inboundFile);
      formData.append("mapping", JSON.stringify(inboundMapping));
      return importInboundCsv(formData);
    },
    onSuccess: async ({ data }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.receivable() });
      setInboundImportSummary({ imported: data.imported, errors: data.errors || [] });
      if (formatName.trim()) {
        localStorage.setItem(
          importPresetStorageKey,
          JSON.stringify({
            name: formatName.trim(),
            mapping: inboundMapping,
          }),
        );
      }
    },
    onError: (err: any) => {
      setInboundImportSummary(null);
      setInboundImportError(getApiErrorMessage(err, t("receiving.importFailed", "Failed to import inbound orders.")));
    },
  });

  const previewOutboundMutation = useMutation({
    mutationFn: async () => {
      if (!outboundFile) {
        throw new Error(t("migration.chooseOutboundCsv", "Choose an outbound CSV file first."));
      }
      setOutboundImportError("");
      setOutboundImportSummary(null);
      const formData = new FormData();
      formData.append("file", outboundFile);
      return previewOutboundCsv(formData);
    },
    onSuccess: (data) => {
      setOutboundPreview(data);
      const presetMapping = savedOutboundImportPreset?.mapping || {};
      const mergedMapping: Record<string, string> = {};
      const validHeaders = new Set(data.headers);
      for (const field of [...data.required_fields, ...data.optional_fields]) {
        const presetHeader = presetMapping[field];
        const suggestedHeader = data.suggested_mapping[field];
        if (presetHeader && validHeaders.has(presetHeader)) mergedMapping[field] = presetHeader;
        else if (suggestedHeader && validHeaders.has(suggestedHeader)) mergedMapping[field] = suggestedHeader;
      }
      setOutboundMapping(mergedMapping);
      setOutboundFormatName(savedOutboundImportPreset?.name || "");
    },
    onError: (err: any) => {
      setOutboundPreview(null);
      setOutboundImportError(getApiErrorMessage(err, t("migration.outboundPreviewFailed", "Failed to preview outbound file.")));
    },
  });

  const importOutboundMutation = useMutation({
    mutationFn: async () => {
      if (!outboundFile) {
        throw new Error(t("migration.chooseOutboundCsv", "Choose an outbound CSV file first."));
      }
      if (!outboundPreview) {
        throw new Error(t("migration.previewOutboundFirst", "Preview and map the outbound file before importing."));
      }
      setOutboundImportError("");
      setOutboundImportSummary(null);
      const formData = new FormData();
      formData.append("file", outboundFile);
      formData.append("mapping", JSON.stringify(outboundMapping));
      return importOutboundCsv(formData);
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.list() });
      setOutboundImportSummary({ imported: data.imported, errors: data.errors || [] });
      if (outboundFormatName.trim()) {
        localStorage.setItem(
          outboundImportPresetStorageKey,
          JSON.stringify({
            name: outboundFormatName.trim(),
            mapping: outboundMapping,
          }),
        );
      }
    },
    onError: (err: any) => {
      setOutboundImportSummary(null);
      setOutboundImportError(getApiErrorMessage(err, t("migration.outboundImportFailed", "Failed to import outbound orders.")));
    },
  });

  const createManualInboundMutation = useMutation({
    mutationFn: async () => {
      const normalizedPackages = manualInbound.packages
        .map((pkg) => ({
          package_type: pkg.packageType || "carton",
          expected_qty: Number(pkg.quantity || 0),
          external_tracking_number: pkg.trackingNumber.trim() || undefined,
          external_carton_mark: pkg.cartonMark.trim() || undefined,
          external_customer_barcode: pkg.customerBarcode.trim() || undefined,
        }))
        .filter(
          (pkg) =>
            pkg.expected_qty > 0 ||
            Boolean(pkg.external_tracking_number) ||
            Boolean(pkg.external_carton_mark) ||
            Boolean(pkg.external_customer_barcode),
        );

      if (normalizedPackages.length > 0) {
        const invalidPackage = normalizedPackages.find((pkg) => pkg.expected_qty <= 0);
        if (invalidPackage) {
          throw new Error(t("migration.manualInboundPackageQtyRequired", "Every inbound package needs a quantity before you can save it."));
        }
        const packageTotal = normalizedPackages.reduce((sum, pkg) => sum + pkg.expected_qty, 0);
        if (packageTotal !== Number(manualInbound.quantity)) {
          throw new Error(
            t(
              "migration.manualInboundPackageQtyMismatch",
              "Package quantities must add up to the inbound line quantity before you create the order.",
            ),
          );
        }
      }

      return createManualInboundOrder({
        client_id: manualInbound.clientId,
        warehouse_id: manualInbound.warehouseId || activeWarehouseId,
        order_number: manualInbound.orderNumber,
        reference_number: manualInbound.referenceNumber || null,
        supplier_name: manualInbound.supplierName || null,
        lines: [
          {
            sku_id: manualInbound.skuId,
            quantity: Number(manualInbound.quantity),
            packages: normalizedPackages.length ? normalizedPackages : undefined,
          },
        ],
      });
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.receivable() });
      setManualInboundError("");
      setManualInboundResult({ order_number: data.order_number, status: data.status });
      setManualInbound((prev) => ({
        ...prev,
        orderNumber: "",
        referenceNumber: "",
        supplierName: "",
        skuId: "",
        quantity: "1",
        packages: [],
      }));
    },
    onError: (err: any) => {
      setManualInboundResult(null);
      setManualInboundError(getApiErrorMessage(err, t("migration.manualInboundFailed", "Could not create the inbound order.")));
    },
  });

  const createManualOutboundMutation = useMutation({
    mutationFn: async () => {
      return createOutboundOrder({
        client_id: manualOutbound.clientId,
        warehouse_id: manualOutbound.warehouseId || activeWarehouseId,
        order_number: manualOutbound.orderNumber,
        reference_number: manualOutbound.referenceNumber || null,
        carrier: manualOutbound.carrier || null,
        lines: [{ sku_id: manualOutbound.skuId, quantity: Number(manualOutbound.quantity) }],
      });
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.list() });
      setManualOutboundError("");
      setManualOutboundResult({ order_number: data.order_number, status: data.status });
      setManualOutbound((prev) => ({ ...prev, orderNumber: "", referenceNumber: "", carrier: "", skuId: "", quantity: "1" }));
    },
    onError: (err: any) => {
      setManualOutboundResult(null);
      setManualOutboundError(getApiErrorMessage(err, t("migration.manualOutboundFailed", "Could not create the outbound order.")));
    },
  });

  const createManualInventoryMutation = useMutation({
    mutationFn: async () => {
      return createManualInventory({
        warehouse_id: manualInventory.warehouseId || activeWarehouseId,
        location_barcode: manualInventory.locationBarcode,
        sku_code: manualInventory.skuCode,
        quantity: Number(manualInventory.quantity),
        lot_number: manualInventory.lotNumber || null,
      });
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inventory.list() });
      setManualInventoryError("");
      setManualInventoryResult({
        sku_code: data.sku_code,
        quantity: data.quantity,
        location_barcode: data.location_barcode,
      });
      setManualInventory((prev) => ({ ...prev, skuCode: "", quantity: "1", locationBarcode: "", lotNumber: "" }));
    },
    onError: (err: any) => {
      setManualInventoryResult(null);
      setManualInventoryError(getApiErrorMessage(err, t("migration.manualInventoryFailed", "Could not import the single inventory row.")));
    },
  });

  const sampleColumns = useMemo(
    () => ["sku_code", "location_barcode", "client_id", "quantity", "lot_number", "expiry_date"],
    [],
  );

  const requiredImportFields = inboundPreview?.required_fields || [];
  const optionalImportFields = inboundPreview?.optional_fields || [];
  const missingMappedFields = requiredImportFields.filter((field) => !inboundMapping[field]);
  const requiredOutboundFields = outboundPreview?.required_fields || [];
  const optionalOutboundFields = outboundPreview?.optional_fields || [];
  const missingOutboundMappedFields = requiredOutboundFields.filter((field) => !outboundMapping[field]);
  const mappedPreviewRows = useMemo(() => {
    if (!inboundPreview) return [];
    return inboundPreview.sample_rows.map((row) => {
      const mappedRow: Record<string, string> = {};
      for (const field of [...requiredImportFields, ...optionalImportFields]) {
        const header = inboundMapping[field];
        mappedRow[field] = header ? row[header] || "" : "";
      }
      return mappedRow;
    });
  }, [inboundMapping, inboundPreview, optionalImportFields, requiredImportFields]);

  const mappedOutboundPreviewRows = useMemo(() => {
    if (!outboundPreview) return [];
    return outboundPreview.sample_rows.map((row) => {
      const mappedRow: Record<string, string> = {};
      for (const field of [...requiredOutboundFields, ...optionalOutboundFields]) {
        const header = outboundMapping[field];
        mappedRow[field] = header ? row[header] || "" : "";
      }
      return mappedRow;
    });
  }, [outboundMapping, outboundPreview, optionalOutboundFields, requiredOutboundFields]);

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_60%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">
              {t("migration.eyebrow", "External document intake")}
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[#f5efe5]">
              {t("migration.title", "Keep inbound, outbound, and migration intake in one place")}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#c7d4dc]">
              {t(
                "migration.heroBody",
                "This page is the shared intake desk for external documents. Bring ASN and PO files in here before receiving starts, load reviewed inventory snapshots here during migration, and keep API-based order feeds documented in the same place so operators know where system truth enters the WMS.",
              )}
            </p>
          </div>
          <div className="rounded-[1.4rem] border border-white/10 bg-white/5 p-4 lg:max-w-sm">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#9db1bf]">
              {t("migration.assistedImport", "Assisted import")}
            </p>
            <p className="mt-2 text-sm leading-6 text-[#d2dde4]">
              {t(
                "migration.assistedImportBody",
                "AI can help explain messy files, suggest mappings, and surface data quality issues. It should not silently write warehouse truth without a human sign-off step.",
              )}
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <MigrationCard
            icon={FileSpreadsheet}
            title={t("migration.card1Title", "1. Gather source documents")}
            text={t(
              "migration.card1Body",
              "Ask the customer or upstream system for clean ASN, PO, outbound, and inventory extracts before operators start work on the floor.",
            )}
          />
          <MigrationCard
            icon={WandSparkles}
            title={t("migration.card2Title", "2. Map before write")}
            text={t(
              "migration.card2Body",
              "Preview real rows, match customer headers to WMS fields, and save a reusable mapping only after the operator confirms it.",
            )}
          />
          <MigrationCard
            icon={ShieldCheck}
            title={t("migration.card3Title", "3. Write with ownership")}
            text={t(
              "migration.card3Body",
              "Imported records should always land with traceability: who approved them, which file was used, and which operational queue they feed next.",
            )}
          />
        </div>
      </section>

      {requiredIntakeSteps.length ? (
        <section className="rounded-[1.8rem] border border-[#f0cf9d] bg-[#fff7ea] p-5 shadow-[0_20px_52px_rgba(19,33,44,0.06)]">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#8b723f]">
            {t("migration.readinessEyebrow", "Intake readiness")}
          </p>
          <p className="mt-2 text-sm leading-7 text-[#6f6248]">
            {t(
              "migration.readinessBody",
              "Before external files write into the workspace, make sure warehouse, locations, clients, and SKUs already exist. Otherwise the import has nowhere believable to land.",
            )}
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            {requiredIntakeSteps.map((step: any) => (
              <Link
                key={step.name}
                to={checklistHref(step.name)}
                className="inline-flex items-center gap-2 rounded-full border border-[#d7c39e] bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
              >
                {t(`dashboard.checklist.${step.name}.title`, step.title || step.name)}
                <ArrowRight size={14} />
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <section
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="migration-mobile-governance"
        data-admin-mobile-contract="migration-desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("migration.mobileGovernanceTitle", "Import center is desktop-first")}
        </p>
        <p className="mt-1">
          {t(
            "migration.mobileGovernanceBody",
            "Use this phone view to check readiness and handoff rules. Upload files, map columns, confirm imports, and create manual records on iPad or desktop.",
          )}
        </p>
      </section>

      <details
        className="rounded-[1.1rem] border border-[#13212c]/8 bg-white/84 px-4 py-3 md:hidden"
        data-testid="migration-mobile-import-collapsed"
      >
        <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
          {t("migration.mobileImportSummary", "Imports require desktop review")}
        </summary>
        <p className="mt-2 text-sm leading-6 text-[#61717d]">
          {t(
            "migration.mobileImportBody",
            "Inbound, outbound, and inventory imports affect live warehouse truth. Review headers, mappings, rejected rows, and confirmation summaries on a larger screen before writing records.",
          )}
        </p>
      </details>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="hidden space-y-6 md:block" data-testid="migration-desktop-import-workbench">
          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
                <FileUp size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("receiving.importTitle", "Bring in ASN or PO data before trucks arrive")}</p>
                <p className="text-sm text-[#61717d]">
                  {t(
                    "migration.inboundCenterBody",
                    "Use this lane for expected inbound documents from ERP, purchasing, or customer ASN files. Preview the headers, map them once, and push the orders straight into the receiving queue.",
                  )}
                </p>
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-4 rounded-[1.4rem] border border-[#13212c]/10 bg-[#f7f4ee] p-4 md:flex-row md:items-end">
              <Field label={t("receiving.importFile", "Inbound CSV")}>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => {
                    setInboundFile(e.target.files?.[0] || null);
                    setInboundPreview(null);
                    setInboundMapping({});
                    setInboundImportSummary(null);
                    setInboundImportError("");
                  }}
                  className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                />
              </Field>
              <button
                type="button"
                onClick={() => previewInboundMutation.mutate()}
                disabled={!inboundFile || previewInboundMutation.isPending}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/12 bg-white px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#13212c] disabled:opacity-50"
              >
                <FileUp size={15} />
                {previewInboundMutation.isPending ? t("receiving.previewing", "Previewing...") : t("receiving.previewImport", "Preview & map")}
              </button>
              <button
                type="button"
                onClick={() => importInboundMutation.mutate()}
                disabled={!inboundFile || !inboundPreview || missingMappedFields.length > 0 || importInboundMutation.isPending}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:opacity-50"
              >
                <FileUp size={15} />
                {importInboundMutation.isPending ? t("receiving.importing", "Importing...") : t("receiving.importAction", "Import inbound orders")}
              </button>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="rounded-[1.4rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("receiving.importTemplate", "Standard inbound template")}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[
                    "order_number",
                    "client_code",
                    "warehouse_code",
                    "sku_code",
                    "quantity",
                    "reference_number",
                    "supplier_name",
                    "line_number",
                    "package_number",
                    "package_type",
                    "package_tracking_number",
                    "package_carton_mark",
                    "package_customer_barcode",
                  ].map((column) => (
                    <span
                      key={column}
                      className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                    >
                      {column}
                    </span>
                  ))}
                </div>
                <p className="mt-3 text-sm leading-6 text-[#61717d]">
                  {t(
                    "receiving.importTemplateHint",
                    "Customers do not need to match this exactly. Required columns stay the same; line_number and package_* columns are optional when the inbound should arrive with carton or MU context already attached.",
                  )}
                </p>
              </div>

              <div className="rounded-[1.4rem] border border-[#13212c]/10 bg-white px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("receiving.savedFormat", "Saved customer format")}
                </p>
                <input
                  type="text"
                  value={formatName}
                  onChange={(e) => setFormatName(e.target.value)}
                  placeholder={savedImportPreset?.name || t("receiving.savedFormatPlaceholder", "Budapest customer ASN layout")}
                  className="mt-3 w-full rounded-[1rem] border border-[#d7dfe5] bg-[#f9fafb] px-4 py-3 text-sm text-[#13212c]"
                />
                <p className="mt-3 text-sm leading-6 text-[#61717d]">
                  {savedImportPreset
                    ? t("receiving.savedFormatHintExisting", "A saved mapping exists for this workspace. Review it against the uploaded headers, then import to keep using it.")
                    : t("receiving.savedFormatHint", "Optionally name this layout so the next import in this workspace can reuse the same mapping.")}
                </p>
              </div>
            </div>

            {inboundImportError ? (
              <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{inboundImportError}</p>
            ) : null}

            {inboundPreview ? (
              <div className="mt-4 space-y-4">
                <div className="rounded-[1.5rem] border border-[#13212c]/10 bg-white px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                        {t("receiving.mappingEyebrow", "Column mapping")}
                      </p>
                      <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
                        {t("receiving.mappingTitle", "Map the customer's headers before writing inbound orders")}
                      </h3>
                    </div>
                    <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-2 text-sm font-medium text-[#13212c]">
                      {t("receiving.previewRows", "Previewing {count} rows from {total}", {
                        count: String(inboundPreview.sample_rows.length),
                        total: String(inboundPreview.total_rows),
                      })}
                    </div>
                  </div>

                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    {[...requiredImportFields, ...optionalImportFields].map((field) => {
                      const required = requiredImportFields.includes(field);
                      return (
                        <Field key={field} label={`${prettyImportFieldLabel(field, t)}${required ? " *" : ""}`}>
                          <select
                            value={inboundMapping[field] || ""}
                            onChange={(e) =>
                              setInboundMapping((prev) => ({
                                ...prev,
                                [field]: e.target.value,
                              }))
                            }
                            className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                          >
                            <option value="">{t("receiving.mapToHeader", "Choose a CSV column")}</option>
                            {inboundPreview.headers.map((header) => (
                              <option key={`${field}-${header}`} value={header}>
                                {header}
                              </option>
                            ))}
                          </select>
                        </Field>
                      );
                    })}
                  </div>

                  {missingMappedFields.length ? (
                    <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                      {t("receiving.mappingMissing", "Finish the required mappings before import:")}{" "}
                      {missingMappedFields.map((field) => prettyImportFieldLabel(field, t)).join(", ")}
                    </p>
                  ) : null}
                </div>

                <div className="rounded-[1.5rem] border border-[#13212c]/10 bg-white px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                    {t("receiving.previewMappedRows", "Mapped row preview")}
                  </p>
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-left text-sm text-[#13212c]">
                      <thead>
                        <tr className="border-b border-[#e3e8ec]">
                          {[...requiredImportFields, ...optionalImportFields].map((field) => (
                            <th key={field} className="px-3 py-2 font-semibold">
                              {prettyImportFieldLabel(field, t)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {mappedPreviewRows.map((row, idx) => (
                          <tr key={`mapped-preview-${idx}`} className="border-b border-[#f1f3f5] align-top">
                            {[...requiredImportFields, ...optionalImportFields].map((field) => (
                              <td key={`${idx}-${field}`} className="px-3 py-2 text-[#61717d]">
                                {row[field] || "—"}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}

            {inboundImportSummary ? (
              <div className="mt-4 rounded-[1.4rem] border border-[#13212c]/10 bg-white px-4 py-4 text-sm text-[#334351]">
                <p className="font-semibold text-[#13212c]">
                  {t("receiving.importSummary", "Imported {count} inbound orders", { count: String(inboundImportSummary.imported) })}
                </p>
                {inboundImportSummary.errors.length ? (
                  <ul className="mt-3 space-y-1 text-[#8a2f26]">
                    {inboundImportSummary.errors.slice(0, 5).map((entry) => (
                      <li key={`${entry.row}-${entry.error}`}>Row {entry.row}: {entry.error}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            <div className="mt-5 rounded-[1.4rem] border border-[#13212c]/10 bg-white px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                    {t("migration.manualEntry", "Single-record intake")}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-[#13212c]">
                    {t("migration.manualInboundTitle", "Create one inbound order when no file is available")}
                  </p>
                </div>
                <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                  {t("migration.manualEntryOneLine", "One order · one line · optional packages")}
                </span>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <Field label={t("common.client", "Client")}>
                  <select
                    value={manualInbound.clientId}
                    onChange={(e) => setManualInbound((prev) => ({ ...prev, clientId: e.target.value, skuId: "" }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectClient", "Choose client")}</option>
                    {clients.map((client: any) => (
                      <option key={client.id} value={client.id}>
                        {client.name} ({client.code})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("migration.warehouseTarget", "Warehouse target")}>
                  <select
                    value={manualInbound.warehouseId || activeWarehouseId}
                    onChange={(e) => setManualInbound((prev) => ({ ...prev, warehouseId: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectWarehouse", "Choose warehouse")}</option>
                    {warehouses.map((warehouse: any) => (
                      <option key={warehouse.id} value={warehouse.id}>
                        {warehouse.name} ({warehouse.code})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("common.orderNumber", "Order number")}>
                  <input
                    value={manualInbound.orderNumber}
                    onChange={(e) => setManualInbound((prev) => ({ ...prev, orderNumber: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("common.reference", "Reference")}>
                  <input
                    value={manualInbound.referenceNumber}
                    onChange={(e) => setManualInbound((prev) => ({ ...prev, referenceNumber: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("receiving.supplierName", "Supplier name")}>
                  <input
                    value={manualInbound.supplierName}
                    onChange={(e) => setManualInbound((prev) => ({ ...prev, supplierName: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("common.sku", "SKU")}>
                  <select
                    value={manualInbound.skuId}
                    onChange={(e) => setManualInbound((prev) => ({ ...prev, skuId: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectSku", "Choose SKU")}</option>
                    {inboundSkus.map((sku: any) => (
                      <option key={sku.id} value={sku.id}>
                        {sku.sku_code} · {sku.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("common.quantity", "Quantity")}>
                  <input
                    type="number"
                    min={1}
                    value={manualInbound.quantity}
                    onChange={(e) => setManualInbound((prev) => ({ ...prev, quantity: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
              </div>

              <div className="mt-4 rounded-[1.2rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                      {t("migration.manualInboundPackagesEyebrow", "Optional package split")}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-[#13212c]">
                      {t("migration.manualInboundPackagesTitle", "Pre-book cartons or MUs when the customer already knows the package breakdown")}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-[#61717d]">
                      {t("migration.manualInboundPackagesBody", "Leave this empty to create only the inbound line. Add package rows here when freight should arrive with carton-level context already attached.")}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      setManualInbound((prev) => ({
                        ...prev,
                        packages: [...prev.packages, buildEmptyManualInboundPackage()],
                      }))
                    }
                    className="inline-flex items-center justify-center rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                  >
                    {t("migration.manualInboundAddPackage", "Add package")}
                  </button>
                </div>

                {manualInbound.packages.length ? (
                  <div className="mt-4 space-y-3">
                    {manualInbound.packages.map((pkg, index) => (
                      <div key={`manual-inbound-package-${index}`} className="rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <p className="text-sm font-semibold text-[#13212c]">
                            {t("migration.manualInboundPackageHeading", "Package {number}", {
                              number: String(index + 1),
                            })}
                          </p>
                          <button
                            type="button"
                            onClick={() =>
                              setManualInbound((prev) => ({
                                ...prev,
                                packages: prev.packages.filter((_, pkgIndex) => pkgIndex !== index),
                              }))
                            }
                            className="inline-flex items-center justify-center rounded-full border border-red-200 bg-red-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-red-700"
                          >
                            {t("migration.manualInboundRemovePackage", "Remove")}
                          </button>
                        </div>
                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                          <Field label={t("receivingFlow.packageType", "Package type")}>
                            <select
                              value={pkg.packageType}
                              onChange={(e) =>
                                setManualInbound((prev) => ({
                                  ...prev,
                                  packages: prev.packages.map((entry, pkgIndex) =>
                                    pkgIndex === index ? { ...entry, packageType: e.target.value } : entry,
                                  ),
                                }))
                              }
                              className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                            >
                              <option value="carton">{t("receivingFlow.packageTypeCarton", "Carton")}</option>
                              <option value="crate">{t("receivingFlow.packageTypeCrate", "Crate")}</option>
                              <option value="pallet">{t("receivingFlow.packageTypePallet", "Pallet")}</option>
                              <option value="mu">{t("receivingFlow.packageTypeMu", "MU")}</option>
                            </select>
                          </Field>
                          <Field label={t("migration.manualInboundPackageQty", "Package quantity")}>
                            <input
                              type="number"
                              min={1}
                              value={pkg.quantity}
                              onChange={(e) =>
                                setManualInbound((prev) => ({
                                  ...prev,
                                  packages: prev.packages.map((entry, pkgIndex) =>
                                    pkgIndex === index ? { ...entry, quantity: e.target.value } : entry,
                                  ),
                                }))
                              }
                              className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                            />
                          </Field>
                          <Field label={t("receivingFlow.detectedCodeTracking", "Tracking Number")}>
                            <input
                              value={pkg.trackingNumber}
                              onChange={(e) =>
                                setManualInbound((prev) => ({
                                  ...prev,
                                  packages: prev.packages.map((entry, pkgIndex) =>
                                    pkgIndex === index ? { ...entry, trackingNumber: e.target.value } : entry,
                                  ),
                                }))
                              }
                              className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                            />
                          </Field>
                          <Field label={t("receivingFlow.detectedCodeCarton", "Carton Mark")}>
                            <input
                              value={pkg.cartonMark}
                              onChange={(e) =>
                                setManualInbound((prev) => ({
                                  ...prev,
                                  packages: prev.packages.map((entry, pkgIndex) =>
                                    pkgIndex === index ? { ...entry, cartonMark: e.target.value } : entry,
                                  ),
                                }))
                              }
                              className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                            />
                          </Field>
                          <Field label={t("receivingFlow.detectedCodeCustomerBox", "Customer Box Code")}>
                            <input
                              value={pkg.customerBarcode}
                              onChange={(e) =>
                                setManualInbound((prev) => ({
                                  ...prev,
                                  packages: prev.packages.map((entry, pkgIndex) =>
                                    pkgIndex === index ? { ...entry, customerBarcode: e.target.value } : entry,
                                  ),
                                }))
                              }
                              className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                            />
                          </Field>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              {manualInboundError ? <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{manualInboundError}</p> : null}
              {manualInboundResult ? (
                <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  {t("migration.manualInboundSuccess", "Inbound order {order} created with status {status}.", {
                    order: manualInboundResult.order_number,
                    status: manualInboundResult.status,
                  })}
                </p>
              ) : null}

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => createManualInboundMutation.mutate()}
                  disabled={
                    createManualInboundMutation.isPending ||
                    !manualInbound.clientId ||
                    !(manualInbound.warehouseId || activeWarehouseId) ||
                    !manualInbound.orderNumber.trim() ||
                    !manualInbound.skuId ||
                    Number(manualInbound.quantity) <= 0
                  }
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:opacity-50"
                >
                  {createManualInboundMutation.isPending ? t("migration.creatingSingle", "Creating...") : t("migration.createSingleInbound", "Create single inbound order")}
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
                <FileUp size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("migration.outboundImportTitle", "Bring in outbound orders from a file")}</p>
                <p className="text-sm text-[#61717d]">
                  {t(
                    "migration.outboundImportBody",
                    "Use the same intake pattern for outbound orders. Preview the customer file, confirm the mapping, and push the result into the outbound order queue.",
                  )}
                </p>
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-4 rounded-[1.4rem] border border-[#13212c]/10 bg-[#f7f4ee] p-4 md:flex-row md:items-end">
              <Field label={t("migration.outboundCsv", "Outbound CSV")}>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => {
                    setOutboundFile(e.target.files?.[0] || null);
                    setOutboundPreview(null);
                    setOutboundMapping({});
                    setOutboundImportSummary(null);
                    setOutboundImportError("");
                  }}
                  className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                />
              </Field>
              <button
                type="button"
                onClick={() => previewOutboundMutation.mutate()}
                disabled={!outboundFile || previewOutboundMutation.isPending}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/12 bg-white px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#13212c] disabled:opacity-50"
              >
                <FileUp size={15} />
                {previewOutboundMutation.isPending ? t("migration.previewing", "Previewing...") : t("migration.previewOutboundImport", "Preview & map")}
              </button>
              <button
                type="button"
                onClick={() => importOutboundMutation.mutate()}
                disabled={!outboundFile || !outboundPreview || missingOutboundMappedFields.length > 0 || importOutboundMutation.isPending}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:opacity-50"
              >
                <FileUp size={15} />
                {importOutboundMutation.isPending ? t("migration.importing", "Importing...") : t("migration.importOutboundOrders", "Import outbound orders")}
              </button>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="rounded-[1.4rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("migration.outboundTemplate", "Standard outbound template")}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {["order_number", "client_code", "warehouse_code", "sku_code", "quantity", "reference_number", "carrier"].map((column) => (
                    <span
                      key={column}
                      className="rounded-2xl border border-[#13212c]/10 bg-white px-3 py-2 text-[#13212c]"
                    >
                      <span className="block text-[11px] font-semibold uppercase tracking-[0.14em]">
                        {prettyOutboundFieldLabel(column, t)}
                      </span>
                      <span className="mt-1 block text-[10px] uppercase tracking-[0.14em] text-[#7e8d98]">
                        {column}
                      </span>
                    </span>
                  ))}
                </div>
                <p className="mt-3 text-sm leading-6 text-[#61717d]">
                  {t("migration.outboundTemplateHint", "Customer exports can use different headers. Use the same mapping step here before writing any outbound orders.")}
                </p>
              </div>

              <div className="rounded-[1.4rem] border border-[#13212c]/10 bg-white px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("migration.savedFormat", "Saved customer format")}
                </p>
                <input
                  type="text"
                  value={outboundFormatName}
                  onChange={(e) => setOutboundFormatName(e.target.value)}
                  placeholder={savedOutboundImportPreset?.name || t("migration.savedFormatOutboundPlaceholder", "Budapest customer outbound layout")}
                  className="mt-3 w-full rounded-[1rem] border border-[#d7dfe5] bg-[#f9fafb] px-4 py-3 text-sm text-[#13212c]"
                />
                <p className="mt-3 text-sm leading-6 text-[#61717d]">
                  {savedOutboundImportPreset
                    ? t("migration.savedFormatHintExisting", "A saved mapping exists for this workspace. Review it against the uploaded headers, then import to keep using it.")
                    : t("migration.savedFormatHint", "Optionally name this layout so the next import in this workspace can reuse the same mapping.")}
                </p>
              </div>
            </div>

            {outboundImportError ? (
              <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{outboundImportError}</p>
            ) : null}

            {outboundPreview ? (
              <div className="mt-4 space-y-4">
                <div className="rounded-[1.5rem] border border-[#13212c]/10 bg-white px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                        {t("migration.outboundMappingEyebrow", "Column mapping")}
                      </p>
                      <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
                        {t("migration.outboundMappingTitle", "Map the customer's outbound headers before creating orders")}
                      </h3>
                    </div>
                    <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-2 text-sm font-medium text-[#13212c]">
                      {t("receiving.previewRows", "Previewing {count} rows from {total}", {
                        count: String(outboundPreview.sample_rows.length),
                        total: String(outboundPreview.total_rows),
                      })}
                    </div>
                  </div>

                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    {[...requiredOutboundFields, ...optionalOutboundFields].map((field) => {
                      const required = requiredOutboundFields.includes(field);
                      return (
                        <Field key={field} label={`${prettyOutboundFieldLabel(field, t)}${required ? " *" : ""}`}>
                          <select
                            value={outboundMapping[field] || ""}
                            onChange={(e) =>
                              setOutboundMapping((prev) => ({
                                ...prev,
                                [field]: e.target.value,
                              }))
                            }
                            className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                          >
                            <option value="">{t("receiving.mapToHeader", "Choose a CSV column")}</option>
                            {outboundPreview.headers.map((header) => (
                              <option key={`${field}-${header}`} value={header}>
                                {header}
                              </option>
                            ))}
                          </select>
                        </Field>
                      );
                    })}
                  </div>

                  {missingOutboundMappedFields.length ? (
                    <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                      {t("migration.mappingMissing", "Finish the required mappings before import:")}{" "}
                      {missingOutboundMappedFields.map((field) => prettyOutboundFieldLabel(field, t)).join(", ")}
                    </p>
                  ) : null}
                </div>

                <div className="rounded-[1.5rem] border border-[#13212c]/10 bg-white px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                    {t("migration.outboundPreviewRows", "Mapped row preview")}
                  </p>
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-left text-sm text-[#13212c]">
                      <thead>
                        <tr className="border-b border-[#e3e8ec]">
                          {[...requiredOutboundFields, ...optionalOutboundFields].map((field) => (
                            <th key={field} className="px-3 py-2 font-semibold">
                              {prettyOutboundFieldLabel(field, t)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {mappedOutboundPreviewRows.map((row, idx) => (
                          <tr key={`mapped-outbound-preview-${idx}`} className="border-b border-[#f1f3f5] align-top">
                            {[...requiredOutboundFields, ...optionalOutboundFields].map((field) => (
                              <td key={`${idx}-${field}`} className="px-3 py-2 text-[#61717d]">
                                {row[field] || "—"}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}

            {outboundImportSummary ? (
              <div className="mt-4 rounded-[1.4rem] border border-[#13212c]/10 bg-white px-4 py-4 text-sm text-[#334351]">
                <p className="font-semibold text-[#13212c]">
                  {t("migration.outboundImportSummary", "Imported {count} outbound orders", { count: String(outboundImportSummary.imported) })}
                </p>
                {outboundImportSummary.errors.length ? (
                  <ul className="mt-3 space-y-1 text-[#8a2f26]">
                    {outboundImportSummary.errors.slice(0, 5).map((entry) => (
                      <li key={`${entry.row}-${entry.error}`}>Row {entry.row}: {entry.error}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            <div className="mt-5 rounded-[1.4rem] border border-[#13212c]/10 bg-white px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                    {t("migration.manualEntry", "Single-record intake")}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-[#13212c]">
                    {t("migration.manualOutboundTitle", "Create one outbound order when no file is available")}
                  </p>
                </div>
                <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                  {t("migration.manualEntryOneLine", "One order · one line")}
                </span>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <Field label={t("common.client", "Client")}>
                  <select
                    value={manualOutbound.clientId}
                    onChange={(e) => setManualOutbound((prev) => ({ ...prev, clientId: e.target.value, skuId: "" }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectClient", "Choose client")}</option>
                    {clients.map((client: any) => (
                      <option key={client.id} value={client.id}>
                        {client.name} ({client.code})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("migration.warehouseTarget", "Warehouse target")}>
                  <select
                    value={manualOutbound.warehouseId || activeWarehouseId}
                    onChange={(e) => setManualOutbound((prev) => ({ ...prev, warehouseId: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectWarehouse", "Choose warehouse")}</option>
                    {warehouses.map((warehouse: any) => (
                      <option key={warehouse.id} value={warehouse.id}>
                        {warehouse.name} ({warehouse.code})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("common.orderNumber", "Order number")}>
                  <input
                    value={manualOutbound.orderNumber}
                    onChange={(e) => setManualOutbound((prev) => ({ ...prev, orderNumber: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("common.reference", "Reference")}>
                  <input
                    value={manualOutbound.referenceNumber}
                    onChange={(e) => setManualOutbound((prev) => ({ ...prev, referenceNumber: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("common.carrier", "Carrier")}>
                  <input
                    value={manualOutbound.carrier}
                    onChange={(e) => setManualOutbound((prev) => ({ ...prev, carrier: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("common.sku", "SKU")}>
                  <select
                    value={manualOutbound.skuId}
                    onChange={(e) => setManualOutbound((prev) => ({ ...prev, skuId: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectSku", "Choose SKU")}</option>
                    {outboundSkus.map((sku: any) => (
                      <option key={sku.id} value={sku.id}>
                        {sku.sku_code} · {sku.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("common.quantity", "Quantity")}>
                  <input
                    type="number"
                    min={1}
                    value={manualOutbound.quantity}
                    onChange={(e) => setManualOutbound((prev) => ({ ...prev, quantity: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
              </div>

              {manualOutboundError ? <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{manualOutboundError}</p> : null}
              {manualOutboundResult ? (
                <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  {t("migration.manualOutboundSuccess", "Outbound order {order} created with status {status}.", {
                    order: manualOutboundResult.order_number,
                    status: manualOutboundResult.status,
                  })}
                </p>
              ) : null}

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => createManualOutboundMutation.mutate()}
                  disabled={
                    createManualOutboundMutation.isPending ||
                    !manualOutbound.clientId ||
                    !(manualOutbound.warehouseId || activeWarehouseId) ||
                    !manualOutbound.orderNumber.trim() ||
                    !manualOutbound.skuId ||
                    Number(manualOutbound.quantity) <= 0
                  }
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:opacity-50"
                >
                  {createManualOutboundMutation.isPending ? t("migration.creatingSingle", "Creating...") : t("migration.createSingleOutbound", "Create single outbound order")}
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
                <Upload size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("migration.importTitle", "Inventory CSV import")}</p>
                <p className="text-sm text-[#61717d]">
                  {t(
                    "migration.importBody",
                    "Use the reviewed inventory file as the first import. This is the safest way to establish on-hand truth before deeper client or billing migration.",
                  )}
                </p>
              </div>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div>
                <label htmlFor="migration-warehouse" className="mb-1.5 block text-sm font-medium text-[#334351]">
                  {t("migration.warehouseTarget", "Warehouse target")}
                </label>
                <select
                  id="migration-warehouse"
                  value={activeWarehouseId}
                  onChange={(e) => setSelectedWarehouseId(e.target.value)}
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                >
                  {warehouses.length === 0 ? <option value="">{t("migration.createWarehouseFirst", "Create a warehouse first")}</option> : null}
                  {warehouses.map((warehouse: any) => (
                    <option key={warehouse.id} value={warehouse.id}>
                      {warehouse.name} ({warehouse.code})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="migration-file" className="mb-1.5 block text-sm font-medium text-[#334351]">
                  {t("migration.inventoryCsv", "Inventory CSV")}
                </label>
                <input
                  id="migration-file"
                  type="file"
                  accept=".csv"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition file:mr-4 file:rounded-full file:border-0 file:bg-[#13212c] file:px-4 file:py-2 file:text-xs file:font-semibold file:uppercase file:tracking-[0.14em] file:text-[#f4efe8]"
                />
              </div>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
              <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-[#f7f4ee] px-5 py-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("migration.expectedColumns", "Expected columns")}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {sampleColumns.map((column) => (
                    <span
                      key={column}
                      className="rounded-2xl border border-[#13212c]/10 bg-white px-3 py-2 text-[#13212c]"
                    >
                      <span className="block text-[11px] font-semibold uppercase tracking-[0.14em]">
                        {prettyInventoryFieldLabel(column, t)}
                      </span>
                      <span className="mt-1 block text-[10px] uppercase tracking-[0.14em] text-[#7e8d98]">
                        {column}
                      </span>
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-white px-5 py-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                  {t("migration.currentTarget", "Current target")}
                </p>
                <p className="mt-2 text-base font-semibold text-[#13212c]">
                  {activeWarehouse ? `${activeWarehouse.name} (${activeWarehouse.code})` : t("migration.noWarehouse", "No warehouse selected")}
                </p>
                <p className="mt-2 text-sm leading-6 text-[#61717d]">
                  {file
                    ? t("migration.fileReady", "File selected. Review the destination and expected columns before importing.")
                    : t("migration.fileWaiting", "Choose a reviewed CSV file before the import action becomes available.")}
                </p>
              </div>
            </div>

            {error ? (
              <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
            ) : null}

            {result ? (
              <div className="mt-4 rounded-[1.4rem] border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-900">
                <p className="font-semibold uppercase tracking-[0.14em] text-emerald-700">
                  {t("migration.importResult", "Import result")}
                </p>
                <p className="mt-2">{t("migration.importedRows", "Imported rows: {count}", { count: result.imported })}</p>
                <p>{t("migration.totalRows", "Total rows processed: {count}", { count: result.total_rows })}</p>
                {result.errors?.length ? (
                  <p className="mt-2">{t("migration.errorRows", "Rows with errors: {count}", { count: result.errors.length })}</p>
                ) : null}
              </div>
            ) : null}

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                disabled={!file || !activeWarehouseId || uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploadMutation.isPending ? t("migration.importing", "Importing...") : t("migration.importReviewedCsv", "Import reviewed inventory CSV")}
                <ArrowRight size={15} />
              </button>

              <a
                href={`${api.defaults.baseURL}/data/inventory/csv`}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/12 px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:border-[#13212c]/24"
              >
                {t("migration.exportCurrentInventory", "Export current inventory")}
                <Database size={15} />
              </a>
            </div>

            <div className="mt-5 rounded-[1.4rem] border border-[#13212c]/10 bg-white px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                    {t("migration.manualEntry", "Single-record intake")}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-[#13212c]">
                    {t("migration.manualInventoryTitle", "Import one inventory row when no file is available")}
                  </p>
                </div>
                <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                  {t("migration.manualInventoryTag", "One location · one SKU")}
                </span>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <Field label={t("migration.warehouseTarget", "Warehouse target")}>
                  <select
                    value={manualInventory.warehouseId || activeWarehouseId}
                    onChange={(e) => setManualInventory((prev) => ({ ...prev, warehouseId: e.target.value, locationBarcode: "" }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectWarehouse", "Choose warehouse")}</option>
                    {warehouses.map((warehouse: any) => (
                      <option key={warehouse.id} value={warehouse.id}>
                        {warehouse.name} ({warehouse.code})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("common.location", "Location")}>
                  <select
                    value={manualInventory.locationBarcode}
                    onChange={(e) => setManualInventory((prev) => ({ ...prev, locationBarcode: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  >
                    <option value="">{t("migration.selectLocation", "Choose location")}</option>
                    {locations.map((location: any) => (
                      <option key={location.id} value={location.barcode}>
                        {location.barcode}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={t("common.skuCode", "SKU code")}>
                  <input
                    value={manualInventory.skuCode}
                    onChange={(e) => setManualInventory((prev) => ({ ...prev, skuCode: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("common.quantity", "Quantity")}>
                  <input
                    type="number"
                    min={1}
                    value={manualInventory.quantity}
                    onChange={(e) => setManualInventory((prev) => ({ ...prev, quantity: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
                <Field label={t("common.lotNumber", "Lot number")}>
                  <input
                    value={manualInventory.lotNumber}
                    onChange={(e) => setManualInventory((prev) => ({ ...prev, lotNumber: e.target.value }))}
                    className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                  />
                </Field>
              </div>

              {manualInventoryError ? <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{manualInventoryError}</p> : null}
              {manualInventoryResult ? (
                <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  {t("migration.manualInventorySuccess", "Inventory row saved: {sku} at {location} now has {quantity} units.", {
                    sku: manualInventoryResult.sku_code,
                    location: manualInventoryResult.location_barcode,
                    quantity: String(manualInventoryResult.quantity),
                  })}
                </p>
              ) : null}

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => createManualInventoryMutation.mutate()}
                  disabled={
                    createManualInventoryMutation.isPending ||
                    !(manualInventory.warehouseId || activeWarehouseId) ||
                    !manualInventory.locationBarcode ||
                    !manualInventory.skuCode.trim() ||
                    Number(manualInventory.quantity) <= 0
                  }
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:opacity-50"
                >
                  {createManualInventoryMutation.isPending ? t("migration.creatingSingle", "Creating...") : t("migration.importSingleInventory", "Import single inventory row")}
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
              {t("migration.lanesTitle", "Document lanes")}
            </p>
            <div className="mt-4 space-y-3">
              <GuideRow
                label={t("migration.laneInboundLabel", "Inbound orders")}
                detail={t("migration.laneInboundBody", "CSV import is available now. Imported rows land in the receiving queue as expected inbound work.")}
              />
              <GuideRow
                label={t("migration.laneInventoryLabel", "Inventory snapshot")}
                detail={t("migration.laneInventoryBody", "CSV import is available now. Use it during go-live or migration to establish opening stock truth.")}
              />
              <GuideRow
                label={t("migration.laneOutboundLabel", "Outbound orders")}
                detail={t("migration.laneOutboundBodyExtended", "CSV import is now available for outbound orders too. Use files for one-off onboarding or customer spreadsheets, and keep API feeds for steady upstream order flow.")}
              />
            </div>
          </div>

          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#f7bf45]/28 bg-[#f7bf45]/12 p-2.5 text-[#d19009]">
                <Link2 size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("migration.apiHubTitle", "API and workflow handoff")}</p>
                <p className="text-sm text-[#61717d]">{t("migration.apiHubBodyFlexible", "Keep the intake model simple: files and APIs can both be used, but operators should still know which queue each document feeds next.")}</p>
              </div>
            </div>

            <div className="mt-4 space-y-3 text-sm leading-7 text-[#61717d]">
              <p>{t("migration.apiInboundBody", "Inbound files or ASN API calls should feed Receiving first, not Putaway directly.")}</p>
              <p>{t("migration.apiOutboundBodyFlexible", "Outbound files or API feeds should both create outbound orders first. Picking tasks should still be generated by the WMS from those orders.")}</p>
              <p className="font-medium text-[#13212c]">{t("migration.apiRuleFlexible", "Best practice: external systems send documents, the WMS creates the execution work, and operators confirm before live stock moves.")}</p>
            </div>

            <div className="mt-5 grid gap-3">
              <Link
                to="/receiving"
                className="inline-flex items-center justify-between rounded-[1.2rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm font-semibold text-[#13212c]"
              >
                {t("migration.openReceivingQueue", "Open receiving queue")}
                <ArrowRight size={15} />
              </Link>
              <Link
                to="/picking"
                className="inline-flex items-center justify-between rounded-[1.2rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm font-semibold text-[#13212c]"
              >
                {t("migration.openOutboundQueue", "Open outbound queue")}
                <ArrowRight size={15} />
              </Link>
            </div>
          </div>

          <div className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#f7bf45]/28 bg-[#f7bf45]/12 p-2.5 text-[#d19009]">
                <Bot size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("migration.aiQuestion", "Should AI be involved?")}</p>
                <p className="text-sm text-[#61717d]">{t("migration.aiAnswer", "Yes, but only as an assistant.")}</p>
              </div>
            </div>

            <div className="mt-4 space-y-3 text-sm leading-7 text-[#61717d]">
              <p>
                {t(
                  "migration.aiBody1",
                  "Use AI to suggest column mapping, flag suspicious duplicates, normalize messy headers, and explain data quality issues to the customer.",
                )}
              </p>
              <p>
                {t(
                  "migration.aiBody2",
                  "Do not let AI silently write live warehouse records without a human review step. Inventory, client, and billing imports affect operations and commercial exposure.",
                )}
              </p>
              <p className="font-medium text-[#13212c]">
                {t("migration.aiBody3", "Best practice: AI suggests, operator confirms, system imports.")}
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}


function prettyImportFieldLabel(field: string, t: (key: string, fallback?: string, vars?: Record<string, string>) => string) {
  const labels: Record<string, string> = {
    order_number: t("common.poNumber", "PO #"),
    client_code: t("receiving.importFieldClientCode", "Client code"),
    warehouse_code: t("receiving.importFieldWarehouseCode", "Warehouse code"),
    sku_code: t("receiving.importFieldSkuCode", "SKU code"),
    quantity: t("common.quantity", "Quantity"),
    reference_number: t("common.reference", "Reference"),
    supplier_name: t("receiving.supplierName", "Supplier name"),
  };
  return labels[field] || field;
}

function prettyOutboundFieldLabel(field: string, t: (key: string, fallback?: string, vars?: Record<string, string>) => string) {
  const labels: Record<string, string> = {
    order_number: t("migration.outboundOrderNumber", "Outbound order #"),
    client_code: t("receiving.importFieldClientCode", "Client code"),
    warehouse_code: t("receiving.importFieldWarehouseCode", "Warehouse code"),
    sku_code: t("receiving.importFieldSkuCode", "SKU code"),
    quantity: t("common.quantity", "Quantity"),
    reference_number: t("common.reference", "Reference"),
    carrier: t("common.carrier", "Carrier"),
  };
  return labels[field] || field;
}

function prettyInventoryFieldLabel(field: string, t: (key: string, fallback?: string, vars?: Record<string, string>) => string) {
  const labels: Record<string, string> = {
    sku_code: t("common.skuCode", "SKU code"),
    location_barcode: t("common.location", "Location"),
    client_id: t("common.client", "Client"),
    quantity: t("common.quantity", "Quantity"),
    lot_number: t("common.lotNumber", "Lot number"),
    expiry_date: t("common.expiryDate", "Expiry date"),
  };
  return labels[field] || field;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[#71808c]">{label}</span>
      {children}
    </label>
  );
}

function MigrationCard({ icon: Icon, title, text }: { icon: any; title: string; text: string }) {
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
      <p className="text-sm font-semibold text-[#13212c]">{label}</p>
      <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}
