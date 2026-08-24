import { useState, type ChangeEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileUp } from "lucide-react";
import ActionButton from "../../shared/components/ActionButton";
import { getApiErrorMessage } from "../../shared/api/error-message";
import {
  confirmPackList,
  previewPackList,
  type PackListImportPayload,
  type PackListImportPreview,
} from "../../shared/api/packLists";
import { useI18n } from "../../shared/i18n";

type PackListImportPanelProps = {
  onImported?: () => Promise<void>;
};

function idempotencyKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `pack-list-ui-${crypto.randomUUID()}`;
  }
  return `pack-list-ui-${Date.now()}`;
}

function messageFor(value: Record<string, unknown>) {
  return String(value.message || value.error || value.code || "Review this row");
}

export default function PackListImportPanel({ onImported }: PackListImportPanelProps) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [sourceText, setSourceText] = useState("");
  const [orderNumber, setOrderNumber] = useState("");
  const [clientCode, setClientCode] = useState("");
  const [warehouseCode, setWarehouseCode] = useState("");
  const [createInboundIfMissing, setCreateInboundIfMissing] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [preview, setPreview] = useState<PackListImportPreview | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const payload = (): PackListImportPayload => ({
    source_text: sourceText,
    file_name: file?.name || "pack-list.csv",
    order_number: orderNumber.trim() || null,
    client_code: clientCode.trim() || null,
    warehouse_code: warehouseCode.trim() || null,
    source_type: "customer_pack_list",
    create_inbound_if_missing: createInboundIfMissing,
  });

  const previewMutation = useMutation({
    mutationFn: () => previewPackList(payload()),
    onSuccess: (nextPreview) => {
      setPreview(nextPreview);
      setResult(null);
      setReviewed(false);
    },
  });

  const confirmMutation = useMutation({
    mutationFn: () => {
      const token = preview?.confirmation_payload?.confirmation_token;
      if (!token) throw new Error("Preview confirmation token is missing");
      return confirmPackList({ ...payload(), confirmation_token: token }, idempotencyKey());
    },
    onSuccess: async (nextResult) => {
      setResult(nextResult);
      await onImported?.();
    },
  });

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] || null;
    setFile(nextFile);
    setPreview(null);
    setResult(null);
    setReviewed(false);
    if (!nextFile) {
      setSourceText("");
      return;
    }
    setSourceText(await nextFile.text());
  };

  const errors = preview?.errors || [];
  const warnings = preview?.warnings || [];
  const rows = preview?.rows || [];
  const canConfirm = Boolean(
    preview?.ok &&
      preview.confirmation_payload?.confirmation_token &&
      reviewed &&
      !confirmMutation.isPending,
  );
  const previewError = previewMutation.error
    ? getApiErrorMessage(previewMutation.error, t("receiving.packListPreviewError", "Could not preview the Pack List."))
    : null;
  const confirmError = confirmMutation.error
    ? getApiErrorMessage(confirmMutation.error, t("receiving.packListConfirmError", "Could not save the Pack List."))
    : null;

  return (
    <section className="rounded-[1.85rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
            {t("receiving.packListEyebrow", "Pre-arrival intake")}
          </p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-[#13212c]">
            {t("receiving.packListTitle", "Import customer Pack List")}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#61717d]">
            {t(
              "receiving.packListBody",
              "Preview package details before arrival. This does not receive freight or change inventory.",
            )}
          </p>
        </div>
        <div className="rounded-full border border-[#24507a]/15 bg-[#eef3f8] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#355a84]">
          {t("receiving.packListEta", "ETA: Not provided")}
        </div>
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <label className="flex min-h-24 cursor-pointer items-center gap-3 rounded-[1.2rem] border border-dashed border-[#24507a]/25 bg-[#f7fafc] px-4 py-3 transition hover:border-[#24507a]/50">
          <span className="rounded-xl bg-[#24507a] p-2 text-white">
            <FileUp size={18} />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[#13212c]">
              {file?.name || t("receiving.packListChooseFile", "Choose CSV or JSON Pack List")}
            </span>
            <span className="mt-1 block text-xs text-[#61717d]">
              {t("receiving.packListFileHint", "The file is parsed locally in the browser, then sent to the governed preview endpoint.")}
            </span>
          </span>
          <input type="file" accept=".csv,.json,text/csv,application/json" onChange={handleFileChange} className="sr-only" />
        </label>

        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
          <input
            value={orderNumber}
            onChange={(event) => setOrderNumber(event.target.value)}
            placeholder={t("receiving.packListOrderPlaceholder", "Inbound order number")}
            className="rounded-xl border border-[#13212c]/12 bg-white px-3 py-2.5 text-sm text-[#13212c] outline-none ring-[#24507a]/25 placeholder:text-[#9aa6af] focus:ring-2"
          />
          <input
            value={clientCode}
            onChange={(event) => setClientCode(event.target.value)}
            placeholder={t("receiving.packListClientPlaceholder", "Client code, if not in file")}
            className="rounded-xl border border-[#13212c]/12 bg-white px-3 py-2.5 text-sm text-[#13212c] outline-none ring-[#24507a]/25 placeholder:text-[#9aa6af] focus:ring-2"
          />
          <input
            value={warehouseCode}
            onChange={(event) => setWarehouseCode(event.target.value)}
            placeholder={t("receiving.packListWarehousePlaceholder", "Warehouse code")}
            className="rounded-xl border border-[#13212c]/12 bg-white px-3 py-2.5 text-sm text-[#13212c] outline-none ring-[#24507a]/25 placeholder:text-[#9aa6af] focus:ring-2"
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-[#51606b]">
          <input
            type="checkbox"
            checked={createInboundIfMissing}
            onChange={(event) => setCreateInboundIfMissing(event.target.checked)}
            className="h-4 w-4 accent-[#24507a]"
          />
          {t("receiving.packListCreateInbound", "Create the pre-arrival inbound order if it does not exist")}
        </label>
        <ActionButton
          onClick={() => previewMutation.mutate()}
          disabled={!sourceText.trim() || previewMutation.isPending}
        >
          {previewMutation.isPending
            ? t("receiving.packListPreviewing", "Previewing...")
            : t("receiving.packListPreviewAction", "Preview Pack List")}
        </ActionButton>
      </div>

      {previewError ? <p className="mt-3 text-sm text-[#9b452a]">{previewError}</p> : null}
      {confirmError ? <p className="mt-3 text-sm text-[#9b452a]">{confirmError}</p> : null}

      {preview ? (
        <div className="mt-5 border-t border-[#13212c]/8 pt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-[#eef3f8] px-3 py-1.5 font-semibold text-[#355a84]">
                {t("receiving.packListRows", "{count} rows", { count: String(preview.summary?.valid_rows ?? 0) })}
              </span>
              <span className="rounded-full bg-[#eef7ef] px-3 py-1.5 font-semibold text-[#2f6c43]">
                {t("receiving.packListPackages", "{count} packages", { count: String(preview.summary?.packages ?? 0) })}
              </span>
              <span className="rounded-full bg-[#f5efe5] px-3 py-1.5 font-semibold text-[#6c5a39]">
                {t("receiving.packListQuantity", "Qty {count}", { count: String(preview.summary?.quantity ?? 0) })}
              </span>
              <span className="rounded-full bg-[#f7f4ee] px-3 py-1.5 font-semibold text-[#6c7a86]">
                {t("receiving.packListSerials", "SN {count}", { count: String(preview.summary?.serial_numbers ?? 0) })}
              </span>
            </div>
            <span className={`rounded-full px-3 py-1.5 text-xs font-semibold ${preview.ok ? "bg-[#eef7ef] text-[#2f6c43]" : "bg-[#fff1eb] text-[#9b452a]"}`}>
              {preview.ok ? t("receiving.packListPreviewValid", "Ready for review") : t("receiving.packListPreviewBlocked", "Fix preview errors")}
            </span>
          </div>

          {errors.length ? (
            <div className="mt-4 rounded-xl border border-[#f2c8bd] bg-[#fff1eb] p-3 text-sm text-[#9b452a]">
              <div className="flex items-center gap-2 font-semibold"><AlertTriangle size={16} /> {t("receiving.packListErrors", "Errors")}</div>
              <ul className="mt-2 space-y-1">{errors.slice(0, 5).map((error, index) => <li key={`pack-list-error-${index}`}>{messageFor(error)}</li>)}</ul>
            </div>
          ) : null}

          {warnings.length ? (
            <div className="mt-4 rounded-xl border border-[#e6d4b2] bg-[#fff7ea] p-3 text-sm text-[#8b723f]">
              <div className="flex items-center gap-2 font-semibold"><AlertTriangle size={16} /> {t("receiving.packListWarnings", "Warnings")}</div>
              <ul className="mt-2 space-y-1">{warnings.slice(0, 5).map((warning, index) => <li key={`pack-list-warning-${index}`}>{messageFor(warning)}</li>)}</ul>
            </div>
          ) : null}

          {rows.length ? (
            <div className="mt-4 overflow-x-auto rounded-xl border border-[#13212c]/8">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-[#f7f4ee] text-[10px] uppercase tracking-[0.12em] text-[#7e8d98]">
                  <tr>
                    <th className="px-3 py-2">{t("receiving.packListPackageColumn", "Package")}</th>
                    <th className="px-3 py-2">{t("receiving.packListSkuColumn", "SKU")}</th>
                    <th className="px-3 py-2">{t("receiving.packListQtyColumn", "Qty")}</th>
                    <th className="px-3 py-2">{t("receiving.packListCustomerSkuColumn", "Customer SKU")}</th>
                    <th className="px-3 py-2">{t("receiving.packListSnColumn", "SN")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#13212c]/8 bg-white">
                  {rows.map((row, index) => (
                    <tr key={`pack-list-row-${index}`}>
                      <td className="whitespace-nowrap px-3 py-2 font-medium text-[#13212c]">{String(row.package_code || "—")}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-[#51606b]">{String(row.sku_code || "—")}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-[#51606b]">{String(row.quantity || "—")}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-[#51606b]">{String(row.customer_sku || "—")}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-[#51606b]">{String(row.serial_number || "Not provided")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {preview.ok ? (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#24507a]/12 bg-[#eef3f8] px-3 py-3">
              <label className="flex items-center gap-2 text-sm text-[#355a84]">
                <input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} className="h-4 w-4 accent-[#24507a]" />
                {t("receiving.packListReviewConfirm", "I reviewed the rows and want to save pre-arrival data")}
              </label>
              <ActionButton variant="success" onClick={() => confirmMutation.mutate()} disabled={!canConfirm}>
                {confirmMutation.isPending ? t("receiving.packListSaving", "Saving...") : t("receiving.packListConfirmAction", "Confirm import")}
              </ActionButton>
            </div>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-[#c8dfd1] bg-[#eef8f0] p-3 text-sm text-[#28543b]">
          <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
          <span>
            {t("receiving.packListSaved", "Pack List saved as pre-arrival data. Inventory was not changed.")} {String(result.order_number || "")}
          </span>
        </div>
      ) : null}
    </section>
  );
}
