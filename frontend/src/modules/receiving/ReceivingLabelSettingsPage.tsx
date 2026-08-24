import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Printer, Settings2 } from "lucide-react";
import { Link } from "react-router-dom";
import { queryKeys } from "../../shared/api/queryKeys";
import { fetchReceivingLabelTemplate, updateReceivingLabelTemplate } from "../../shared/api/receiving";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";

const DEFAULT_TEMPLATE_FIELDS = ["order_number", "sku_code", "expected_qty", "tracking_number"];

const FIELD_OPTIONS = [
  { value: "order_number", labelKey: "receivingLabelSettings.fieldOrderNumber", fallback: "Inbound order" },
  { value: "package_number", labelKey: "receivingLabelSettings.fieldPackageNumber", fallback: "Package number" },
  { value: "package_type", labelKey: "receivingLabelSettings.fieldPackageType", fallback: "Package type" },
  { value: "reference_number", labelKey: "receivingLabelSettings.fieldReferenceNumber", fallback: "Reference" },
  { value: "sku_code", labelKey: "receivingLabelSettings.fieldSkuCode", fallback: "SKU code" },
  { value: "sku_name", labelKey: "receivingLabelSettings.fieldSkuName", fallback: "SKU name" },
  { value: "expected_qty", labelKey: "receivingLabelSettings.fieldExpectedQty", fallback: "Expected qty" },
  { value: "received_qty", labelKey: "receivingLabelSettings.fieldReceivedQty", fallback: "Received qty" },
  { value: "tracking_number", labelKey: "receivingLabelSettings.fieldTrackingNumber", fallback: "Tracking number" },
  { value: "carton_mark", labelKey: "receivingLabelSettings.fieldCartonMark", fallback: "Carton mark" },
  { value: "customer_barcode", labelKey: "receivingLabelSettings.fieldCustomerBarcode", fallback: "Customer box code" },
  { value: "package_count", labelKey: "receivingLabelSettings.fieldPackageCount", fallback: "Number of boxes" },
  { value: "pallet_count", labelKey: "receivingLabelSettings.fieldPalletCount", fallback: "Pallets quantity" },
  { value: "weight", labelKey: "receivingLabelSettings.fieldWeight", fallback: "Weight" },
  { value: "dimensions", labelKey: "receivingLabelSettings.fieldDimensions", fallback: "Dimensions" },
  { value: "rent_free_days", labelKey: "receivingLabelSettings.fieldRentFreeDays", fallback: "Rent-free days" },
  { value: "receiving_note", labelKey: "receivingLabelSettings.fieldReceivingNote", fallback: "Receiving note" },
] as const;

const SAMPLE_LABEL_VALUES: Record<string, string> = {
  order_number: "INB-2026-0417-001",
  package_number: "2",
  package_type: "Carton",
  reference_number: "REF-DOCK-0417",
  sku_code: "DAN-FLOUR-020",
  sku_name: "Bread Flour Sack 20kg",
  expected_qty: "5",
  received_qty: "5",
  tracking_number: "TRK-7788-ALPHA",
  carton_mark: "CTN-A-00417",
  customer_barcode: "CUST-BOX-4417",
  package_count: "2",
  pallet_count: "1",
  weight: "12.5 kg",
  dimensions: "40 × 30 × 20 cm",
  rent_free_days: "7",
  receiving_note: "Dock check complete",
};

export default function ReceivingLabelSettingsPage() {
  const { t } = useI18n();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fields, setFields] = useState<string[]>([]);
  const [showFieldLabels, setShowFieldLabels] = useState(true);

  const settingsQuery = useQuery({
    queryKey: queryKeys.receiving.labelTemplate(),
    queryFn: fetchReceivingLabelTemplate,
  });

  useEffect(() => {
    if (!settingsQuery.data) return;
    setFields(settingsQuery.data.fields);
    setShowFieldLabels(settingsQuery.data.show_field_labels);
  }, [settingsQuery.data]);

  const availableFields = useMemo(() => {
    const allowed = new Set(settingsQuery.data?.available_fields || FIELD_OPTIONS.map((field) => field.value));
    return FIELD_OPTIONS.filter((field) => allowed.has(field.value));
  }, [settingsQuery.data]);

  const activePreviewFields = useMemo(
    () =>
      fields
        .map((field) => availableFields.find((option) => option.value === field))
        .filter((field): field is (typeof FIELD_OPTIONS)[number] => Boolean(field)),
    [availableFields, fields],
  );

  const hasUnsavedChanges = useMemo(() => {
    if (!settingsQuery.data) return false;
    if (settingsQuery.data.show_field_labels !== showFieldLabels) return true;
    if (settingsQuery.data.fields.length !== fields.length) return true;
    return settingsQuery.data.fields.some((field, index) => field !== fields[index]);
  }, [fields, settingsQuery.data, showFieldLabels]);

  useEffect(() => {
    if (!hasUnsavedChanges) return;
    setMessage("");
    setError("");
  }, [hasUnsavedChanges]);

  const isDefaultTemplate =
    showFieldLabels &&
    fields.length === DEFAULT_TEMPLATE_FIELDS.length &&
    fields.every((field, index) => field === DEFAULT_TEMPLATE_FIELDS[index]);

  const saveMutation = useMutation({
    mutationFn: async () =>
      updateReceivingLabelTemplate({
        fields,
        show_field_labels: showFieldLabels,
      }),
    onSuccess: (data) => {
      settingsQuery.refetch();
      setFields(data.fields);
      setShowFieldLabels(data.show_field_labels);
      setMessage(
        t(
          "receivingLabelSettings.saveSuccess",
          "Internal label print fields saved. Newly printed receiving labels will follow this template.",
        ),
      );
      setError("");
    },
    onError: (err: any) => {
      setMessage("");
      setError(
        getApiErrorMessage(
          err,
          t("receivingLabelSettings.saveError", "Could not save the internal label print template."),
        ),
      );
    },
  });

  const toggleField = (field: string) => {
    setFields((current) => (current.includes(field) ? current.filter((item) => item !== field) : [...current, field]));
  };

  const moveField = (field: string, direction: -1 | 1) => {
    setFields((current) => {
      const index = current.indexOf(field);
      if (index === -1) return current;
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  };

  const resetToDefault = () => {
    setFields(DEFAULT_TEMPLATE_FIELDS);
    setShowFieldLabels(true);
    setMessage("");
    setError("");
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <section className="rounded-[1.5rem] border border-[#13212c]/8 bg-white p-6 shadow-[0_10px_26px_rgba(19,33,44,0.05)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[#7e8d98]">
              {t("receivingLabelSettings.eyebrow", "Receiving label template")}
            </p>
            <h1 className="mt-3 text-[2rem] font-semibold tracking-[-0.04em] text-[#13212c]">
              {t(
                "receivingLabelSettings.title",
                "Choose what your warehouse prints on each internal receiving label.",
              )}
            </h1>
            <p className="mt-4 text-sm leading-7 text-[#61717d]">
              {t(
                "receivingLabelSettings.body",
                "Pick the fields that matter on the dock, keep them in the order your operators expect, and let the printer output stay consistent from receiving through putaway.",
              )}
            </p>
          </div>
          <div className="grid w-full gap-3 lg:max-w-md lg:grid-cols-3">
            <SummaryChip
              label={t("receivingLabelSettings.summaryFields", "Selected fields")}
              value={String(fields.length)}
            />
            <SummaryChip
              label={t("receivingLabelSettings.summaryLabels", "Field titles")}
              value={
                showFieldLabels
                  ? t("receivingLabelSettings.summaryLabelsOn", "Shown")
                  : t("receivingLabelSettings.summaryLabelsOff", "Hidden")
              }
            />
            <SummaryChip
              label={t("receivingLabelSettings.summaryStatus", "Template status")}
              value={
                hasUnsavedChanges
                  ? t("receivingLabelSettings.summaryStatusDirty", "Unsaved changes")
                  : t("receivingLabelSettings.summaryStatusSaved", "Saved")
              }
            />
          </div>
        </div>
      </section>

      <section
        className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
        data-testid="receiving-label-mobile-governance"
        data-admin-mobile-contract="receiving-settings-desktop-first"
      >
        <p className="font-semibold text-[#13212c]">
          {t("receivingLabelSettings.mobileNoticeTitle", "Receiving label template is desktop-first")}
        </p>
        <p className="mt-1">
          {t("receivingLabelSettings.mobileNoticeBody", "Use this phone view to check selected fields and status. Reorder fields, change printer-facing labels, and save templates on iPad or desktop.")}
        </p>
      </section>

      <details
        className="rounded-[1.1rem] border border-[#13212c]/8 bg-white/84 px-4 py-3 md:hidden"
        data-testid="receiving-label-mobile-settings-collapsed"
      >
        <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
          {t("receivingLabelSettings.mobileEditSummary", "Edit template on desktop")}
        </summary>
        <p className="mt-2 text-sm leading-6 text-[#61717d]">
          {t("receivingLabelSettings.mobileEditBody", "Field selection, label visibility, and print order affect every dock label, so edits stay in the desktop management path.")}
        </p>
      </details>

      <section className="hidden rounded-[1.5rem] border border-[#13212c]/8 bg-white p-6 shadow-[0_10px_26px_rgba(19,33,44,0.05)] md:block">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className="space-y-5">
            <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-[#13212c]/10 bg-white text-[#13212c]">
                  <Printer size={18} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-[#13212c]">
                    {t("receivingLabelSettings.selectionTitle", "Printable fields")}
                  </p>
                  <p className="text-sm leading-6 text-[#61717d]">
                    {t(
                      "receivingLabelSettings.selectionBody",
                      "Internal code and machine-readable barcode stay on the label. Everything below lets you decide what supporting details operators see around it.",
                    )}
                  </p>
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {availableFields.map((field) => {
                  const checked = fields.includes(field.value);
                  return (
                    <label
                      key={field.value}
                      className={`rounded-[1rem] border px-4 py-3 ${checked ? "border-[#13212c]/15 bg-white" : "border-[#d7dfe5] bg-[#fbf8f2]"}`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleField(field.value)}
                          className="mt-1 h-4 w-4"
                        />
                        <div>
                          <p className="text-sm font-medium text-[#13212c]">
                            {t(field.labelKey, field.fallback)}
                          </p>
                          <p className="mt-1 text-xs text-[#61717d]">{field.value}</p>
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-[#13212c]/10 bg-[#f7f4ee] text-[#13212c]">
                  <Settings2 size={18} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-[#13212c]">
                    {t("receivingLabelSettings.orderTitle", "Print order")}
                  </p>
                  <p className="text-sm leading-6 text-[#61717d]">
                    {t(
                      "receivingLabelSettings.orderBody",
                      "Move the selected fields up or down to match the way your operators read labels on the dock.",
                    )}
                  </p>
                </div>
              </div>

              <div className="mt-5 space-y-3">
                {fields.map((field, index) => {
                  const option = availableFields.find((item) => item.value === field);
                  if (!option) return null;
                  return (
                    <div
                      key={field}
                      className="flex items-center justify-between gap-3 rounded-[0.9rem] border border-[#d7dfe5] bg-[#fbf8f2] px-4 py-3"
                    >
                      <div>
                        <p className="text-sm font-medium text-[#13212c]">{t(option.labelKey, option.fallback)}</p>
                        <p className="mt-1 text-xs text-[#61717d]">{field}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => moveField(field, -1)}
                          disabled={index === 0}
                          className="rounded-full border border-[#d7dfe5] px-3 py-1 text-xs font-medium text-[#13212c] disabled:opacity-40"
                        >
                          {t("receivingLabelSettings.moveUp", "Up")}
                        </button>
                        <button
                          type="button"
                          onClick={() => moveField(field, 1)}
                          disabled={index === fields.length - 1}
                          className="rounded-full border border-[#d7dfe5] px-3 py-1 text-xs font-medium text-[#13212c] disabled:opacity-40"
                        >
                          {t("receivingLabelSettings.moveDown", "Down")}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              <label className="mt-5 flex items-start gap-3 rounded-[0.9rem] border border-[#d7dfe5] bg-[#fbf8f2] px-4 py-3">
                <input
                  type="checkbox"
                  checked={showFieldLabels}
                  onChange={(e) => setShowFieldLabels(e.target.checked)}
                  className="mt-1 h-4 w-4"
                />
                <div>
                  <p className="text-sm font-medium text-[#13212c]">
                    {t("receivingLabelSettings.showFieldLabels", "Show field titles on the label")}
                  </p>
                  <p className="mt-1 text-xs text-[#61717d]">
                    {t(
                      "receivingLabelSettings.showFieldLabelsBody",
                      "Turn this off if the dock wants the leanest possible sticker and already knows the field order.",
                    )}
                  </p>
                </div>
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || fields.length === 0 || !hasUnsavedChanges}
                className="inline-flex items-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold text-[#f4efe8] disabled:opacity-50"
              >
                <CheckCircle2 size={16} />
                {saveMutation.isPending
                  ? t("receivingLabelSettings.saving", "Saving...")
                  : t("receivingLabelSettings.saveAction", "Save label template")}
              </button>
              <button
                type="button"
                onClick={resetToDefault}
                disabled={isDefaultTemplate}
                className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/12 bg-[#f7f4ee] px-5 py-3 text-sm font-semibold text-[#13212c] disabled:opacity-40"
              >
                <Settings2 size={16} />
                {t("receivingLabelSettings.resetAction", "Reset to default")}
              </button>
              <Link
                to="/receiving"
                className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/12 bg-white px-5 py-3 text-sm font-semibold text-[#13212c]"
              >
                <Printer size={16} />
                {t("receivingLabelSettings.backToReceiving", "Back to inbound receiving")}
              </Link>
            </div>

            {message ? <p className="text-sm text-[#2a6c42]">{message}</p> : null}
            {error ? <p className="text-sm text-[#9b382d]">{error}</p> : null}
            {isDefaultTemplate ? (
              <p className="text-sm text-[#61717d]">
                {t(
                  "receivingLabelSettings.resetHint",
                  "You are currently using the default dock template."
                )}
              </p>
            ) : null}
          </div>

          <div className="space-y-4">
            <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#13212c] p-5 text-[#f4efe8] shadow-[0_10px_28px_rgba(19,33,44,0.18)]">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] uppercase tracking-[0.2em] text-[#b8c5ce]">
                  {t("receivingLabelSettings.previewCardEyebrow", "Label preview")}
                </p>
                <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[11px] font-medium text-[#f4efe8]">
                  {hasUnsavedChanges
                    ? t("receivingLabelSettings.previewDirty", "Previewing unsaved changes")
                    : t("receivingLabelSettings.previewSaved", "Preview matches saved template")}
                </span>
              </div>
              <div className="mt-4 rounded-[1.1rem] border border-white/10 bg-white px-4 py-4 text-[#13212c]">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                      {t("receivingLabelSettings.previewPackageEyebrow", "Package context")}
                    </p>
                    <p className="mt-2 text-sm font-semibold">Package 2 · Carton</p>
                    <p className="mt-3 text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                      {t("receivingLabelSettings.previewInternalCode", "Internal code")}
                    </p>
                    <p className="mt-2 text-base font-semibold">RCV-INB-2026-0417-001</p>
                  </div>
                  <div className="rounded-lg border border-dashed border-[#d7dfe5] px-3 py-2 text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                    {t("receivingLabelSettings.previewBarcode", "Barcode / QR")}
                  </div>
                </div>
                <div className="mt-4 space-y-2">
                  {activePreviewFields.length > 0 ? (
                    activePreviewFields.map((field) => (
                      <div
                        key={field.value}
                        className="flex items-start justify-between gap-3 rounded-[0.8rem] border border-[#e4e9ed] bg-[#fbf8f2] px-3 py-2"
                      >
                        <p className="min-w-0 text-xs font-medium text-[#61717d]">
                          {showFieldLabels ? t(field.labelKey, field.fallback) : ""}
                        </p>
                        <p className="min-w-0 flex-1 text-right text-sm font-semibold text-[#13212c]">
                          {SAMPLE_LABEL_VALUES[field.value] || "—"}
                        </p>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-[0.8rem] border border-dashed border-[#d7dfe5] bg-[#fbf8f2] px-3 py-3 text-sm text-[#61717d]">
                      {t(
                        "receivingLabelSettings.previewEmpty",
                        "Select at least one supporting field to preview how the printed internal label will read on the dock.",
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
            <InfoCard
              eyebrow={t("receivingLabelSettings.previewEyebrow", "Preview logic")}
              title={t("receivingLabelSettings.previewTitle", "The warehouse code, barcode, and package header always stay on the label.")}
              body={t(
                "receivingLabelSettings.previewBody",
                "This template only controls the supporting fields around the internal code. Each printed label still keeps the warehouse-owned identifier and the package context so operators know which carton or MU they are holding.",
              )}
            />
            <InfoCard
              eyebrow={t("receivingLabelSettings.packageFieldsEyebrow", "Package-first fields")}
              title={t("receivingLabelSettings.packageFieldsTitle", "Use package number and package type when the dock thinks in cartons, pallets, or MUs.")}
              body={t(
                "receivingLabelSettings.packageFieldsBody",
                "These fields help the printed label match the physical package. They are especially useful when one inbound line is split into multiple cartons that need their own internal codes and downstream putaway paths.",
              )}
            />
            <InfoCard
              eyebrow={t("receivingLabelSettings.governanceEyebrow", "Governance")}
              title={t("receivingLabelSettings.governanceTitle", "Keep the printout focused on what the dock actually uses.")}
              body={t(
                "receivingLabelSettings.governanceBody",
                "Long notes and extra measurements are useful in the system, but some warehouses only want the most actionable details on stickers. This template lets each tenant choose the right balance.",
              )}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

function SummaryChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-[#13212c]/10 bg-[#f7f4ee] p-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}

function InfoCard({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#fcfaf5] p-5">
      <p className="text-[11px] uppercase tracking-[0.2em] text-[#7e8d98]">{eyebrow}</p>
      <p className="mt-3 text-sm font-semibold text-[#13212c]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#61717d]">{body}</p>
    </div>
  );
}
