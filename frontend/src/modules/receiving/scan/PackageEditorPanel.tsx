/**
 * Scan step: package editor panel (create / edit a package record).
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import {
  type InboundDetailLineSummary,
} from "../receivingFlowUtils";
import {
  type PackageEditorAction,
  type PackageEditorState,
} from "../receivingFlowState";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface PackageEditorPanelProps {
  t: Translator;
  packageEditor: PackageEditorState;
  dispatchPackageEditor: (patch: PackageEditorAction) => void;
  lineSummaries: InboundDetailLineSummary[];
  lineEditorLabel: (line: InboundDetailLineSummary) => string;
  submitting: boolean;
  onSubmit: () => void;
  onCancel: () => void;
}

export default function PackageEditorPanel({
  t,
  packageEditor,
  dispatchPackageEditor,
  lineSummaries,
  lineEditorLabel,
  submitting,
  onSubmit,
  onCancel,
}: PackageEditorPanelProps) {
  if (!packageEditor.mode) return null;
  return (
          <div className="rounded-2xl border border-[#e3ddd2] bg-[#fbf8f2] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {packageEditor.mode === "edit"
                    ? t("receivingFlow.packageEditorEyebrowEdit", "Edit package")
                    : t("receivingFlow.packageEditorEyebrowCreate", "New package")}
                </p>
                <p className="mt-2 text-sm text-[#51606b]">
                  {packageEditor.mode === "edit"
                    ? t(
                        "receivingFlow.packageEditorBodyEdit",
                        "Update this package before it is confirmed. Once received, the package and its internal label become audit records.",
                      )
                    : t(
                        "receivingFlow.packageEditorBodyCreate",
                        "Create a package first when the freight has no scannable code, or split the inbound line into another carton/MU before receiving it.",
                      )}
                </p>
              </div>
              <button
                type="button"
                onClick={onCancel}
                className="text-xs font-medium text-[#51606b]"
              >
                {t("receivingFlow.packageEditorCancel", "Cancel")}
              </button>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <div>
                <label className="text-xs text-gray-500">
                  {t("receivingFlow.packageEditorLineLabel", "Inbound line")}
                </label>
                <select
                  value={packageEditor.lineId}
                  onChange={(e) => dispatchPackageEditor({ lineId: e.target.value })}
                  disabled={packageEditor.mode === "edit"}
                  className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c] disabled:bg-[#f4f4f4]"
                >
                  <option value="">{t("receivingFlow.packageEditorLinePlaceholder", "Choose inbound line")}</option>
                  {lineSummaries.map((line) => (
                    <option key={line.line_id} value={line.line_id}>
                      {lineEditorLabel(line)}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs text-gray-500">
                  {t("receivingFlow.packageEditorExpectedQtyLabel", "Package expected qty")}
                </label>
                <input
                  type="number"
                  min={1}
                  value={packageEditor.expectedQty}
                  onChange={(e) => dispatchPackageEditor({ expectedQty: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500">
                  {t("receivingFlow.packageEditorTypeLabel", "Package type")}
                </label>
                <select
                  value={packageEditor.type}
                  onChange={(e) => dispatchPackageEditor({ type: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                >
                  <option value="carton">{t("receivingFlow.packageTypeCarton", "Carton")}</option>
                  <option value="crate">{t("receivingFlow.packageTypeCrate", "Crate")}</option>
                  <option value="pallet">{t("receivingFlow.packageTypePallet", "Pallet")}</option>
                  <option value="mu">{t("receivingFlow.packageTypeMu", "MU")}</option>
                </select>
              </div>

              <div>
                <label className="text-xs text-gray-500">
                  {t("receivingFlow.detectedCodeTracking", "Tracking Number")}
                </label>
                <input
                  type="text"
                  value={packageEditor.tracking}
                  onChange={(e) => dispatchPackageEditor({ tracking: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500">
                  {t("receivingFlow.detectedCodeCarton", "Carton Mark")}
                </label>
                <input
                  type="text"
                  value={packageEditor.carton}
                  onChange={(e) => dispatchPackageEditor({ carton: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500">
                  {t("receivingFlow.detectedCodeCustomerBarcode", "Customer Box Code")}
                </label>
                <input
                  type="text"
                  value={packageEditor.customerCode}
                  onChange={(e) => dispatchPackageEditor({ customerCode: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                />
              </div>
            </div>

            {packageEditor.error ? (
              <p className="mt-3 rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-sm text-[#9b452a]">
                {packageEditor.error}
              </p>
            ) : null}

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onSubmit}
                disabled={submitting}
                className="rounded-xl bg-[#13212c] px-4 py-2 text-sm font-medium text-white disabled:opacity-45"
              >
                {packageEditor.mode === "edit"
                  ? t("receivingFlow.packageEditorSaveAction", "Save package")
                  : t("receivingFlow.packageEditorCreateAction", "Create and open package")}
              </button>
              <button
                type="button"
                onClick={onCancel}
                className="rounded-xl border border-[#d7d0c4] bg-white px-4 py-2 text-sm font-medium text-[#13212c]"
              >
                {t("receivingFlow.packageEditorCancel", "Cancel")}
              </button>
            </div>
          </div>
  );
}
