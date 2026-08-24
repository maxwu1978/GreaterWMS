/**
 * Scan step: confirmed internal labels panel (print queue and reprints).
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import type { MutableRefObject } from "react";
import StatusBadge from "../../../shared/components/StatusBadge";
import {
  type ReceivingLabelSummary,
  type ScannedReceivingLabel,
} from "../receivingFlowUtils";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface ConfirmedLabelsPanelProps {
  t: Translator;
  confirmedLabelsRef: MutableRefObject<HTMLDivElement | null>;
  receivingLabels: ReceivingLabelSummary[];
  printableLabelCount: number;
  unprintedLabelCount: number;
  printedLabelCount: number;
  lastPrintedLabelCount: number;
  activeTemplateFieldLabels: { field: string; label: string }[];
  templateFieldLabelsShown: boolean;
  activePrintPackageId: string;
  scannedLabel: ScannedReceivingLabel | null;
  externalCodesForLabel: (label: {
    external_tracking_number?: string | null;
    external_carton_mark?: string | null;
    external_customer_barcode?: string | null;
  }) => (string | null)[];
  onEditTemplate: () => void;
  onPrintLabels: (labelCode?: string) => void;
}

export default function ConfirmedLabelsPanel({
  t,
  confirmedLabelsRef,
  receivingLabels,
  printableLabelCount,
  unprintedLabelCount,
  printedLabelCount,
  lastPrintedLabelCount,
  activeTemplateFieldLabels,
  templateFieldLabelsShown,
  activePrintPackageId,
  scannedLabel,
  externalCodesForLabel,
  onEditTemplate,
  onPrintLabels,
}: ConfirmedLabelsPanelProps) {
  if (printableLabelCount <= 0) return null;
  return (
          <div ref={confirmedLabelsRef} className="bg-white rounded-lg shadow p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("receivingFlow.confirmedLabelsEyebrow", "Confirmed internal labels")}
                </p>
                <p className="mt-2 text-sm leading-6 text-[#51606b]">
                  {t(
                    "receivingFlow.confirmedLabelsStateCopy",
                    "These warehouse-owned labels were issued after receipt confirmation. Print any pending labels before the packages leave the dock handoff.",
                  )}
                </p>
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full border border-[#d7d0c4] bg-[#fcfaf5] px-3 py-1 font-medium text-[#51606b]">
                    {t("receivingFlow.internalLabelsReadyToPrint", "{count} ready to print", {
                      count: unprintedLabelCount,
                    })}
                  </span>
                  <span className="rounded-full border border-[#d7d0c4] bg-[#fcfaf5] px-3 py-1 font-medium text-[#51606b]">
                    {t("receivingFlow.internalLabelsPrinted", "{count} already printed", {
                      count: printedLabelCount,
                    })}
                  </span>
                  {lastPrintedLabelCount > 0 ? (
                    <span className="rounded-full border border-[#c8dfd1] bg-[#eef8f0] px-3 py-1 font-medium text-[#28543b]">
                      {t("receivingFlow.internalLabelsPrintedJustNow", "Printed {count} just now", {
                        count: lastPrintedLabelCount,
                      })}
                    </span>
                  ) : null}
                </div>
                <details className="mt-3 hidden rounded-2xl border border-[#e3ddd2] bg-[#fcfaf5] p-3 md:block">
                  <summary className="cursor-pointer list-none">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                          {t("receivingFlow.labelTemplateEyebrow", "Print template")}
                        </span>
                        <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                          {t("receivingFlow.labelTemplateFieldCount", "{count} fields", {
                            count: activeTemplateFieldLabels.length,
                          })}
                        </span>
                      </div>
                    </div>
                  </summary>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-2">
                      <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                        {templateFieldLabelsShown
                          ? t("receivingFlow.labelTemplateTitlesShown", "Field titles shown")
                          : t("receivingFlow.labelTemplateTitlesHidden", "Field titles hidden")}
                      </span>
                      <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                        {t("receivingFlow.labelTemplatePackageHeader", "Package header always shown")}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={onEditTemplate}
                      className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                    >
                      {t("receivingFlow.labelTemplateAction", "Edit template")}
                    </button>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {activeTemplateFieldLabels.map(({ field, label }) => (
                      <span
                        key={field}
                        className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]"
                      >
                        {label}
                      </span>
                    ))}
                  </div>
                </details>
              </div>
              {printableLabelCount > 0 ? (
                <button
                  type="button"
                  onClick={() => onPrintLabels()}
                  className="rounded-xl border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-medium text-[#13212c]"
                >
                  {t("receivingFlow.printInternalLabelsAction", "Print labels")}
                </button>
              ) : null}
            </div>
            <div className="hidden gap-3 md:grid md:grid-cols-2 xl:grid-cols-3">
              {receivingLabels
                .filter((label) => label.status === "received")
                .map((label) => {
                const isHighlightedPrintPackage = activePrintPackageId && label.package_id === activePrintPackageId;
                const labelExternalCodes = externalCodesForLabel(label);
                const packagingBits = [
                  label.package_count != null
                    ? t("receivingFlow.packageCardBoxes", "{count} boxes", {
                        count: label.package_count,
                      })
                    : null,
                  label.pallet_count != null
                    ? t("receivingFlow.packageCardPallets", "{count} pallets", {
                        count: label.pallet_count,
                      })
                    : null,
                  label.measured_weight_kg != null
                    ? t("receivingFlow.packageCardWeight", "{weight} kg", {
                        weight: label.measured_weight_kg,
                      })
                    : null,
                ].filter(Boolean);
                const packageHeader = [
                  label.package_number != null
                    ? t("receivingFlow.packageCardTitle", "Package {number}", {
                        number: label.package_number,
                      })
                    : null,
                  label.package_type || label.label_type || null,
                ].filter(Boolean);
                return (
                <div
                  key={label.id}
                  className={`rounded-2xl border p-3 ${
                    scannedLabel?.label_code === label.label_code
                      ? "border-[#13212c] bg-[#f7f4ee]"
                      : "border-[#e3ddd2] bg-[#fcfaf5]"
                  } ${
                    !scannedLabel?.label_code && isHighlightedPrintPackage ? "ring-2 ring-[#4977c8]/35" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-[#13212c]">{label.label_code}</p>
                      {packageHeader.length > 0 ? (
                        <p className="mt-2 text-xs font-medium uppercase tracking-[0.16em] text-[#7f8d98]">
                          {packageHeader.join(" · ")}
                        </p>
                      ) : null}
                      <div className="mt-2 flex items-center gap-2 text-xs text-[#6b7280]">
                        <span>
                          {t("receivingFlow.labelExpected", "Expected")}: {label.expected_qty}
                        </span>
                        <span>·</span>
                        <span>
                          {label.print_count && label.print_count > 0
                            ? t("receivingFlow.printedCount", "Printed {count} times", {
                                count: label.print_count,
                              })
                            : t("receivingFlow.notPrintedYet", "Not printed yet")}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span
                          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                            (label.print_count || 0) > 0
                              ? "bg-[#eef8f0] text-[#28543b]"
                              : "bg-[#fff6e6] text-[#91621a]"
                          }`}
                        >
                          {(label.print_count || 0) > 0
                            ? t("receivingFlow.internalLabelPrintedState", "Printed")
                            : t("receivingFlow.internalLabelPendingPrintState", "Print next")}
                        </span>
                        {packagingBits.map((bit) => (
                          <span
                            key={bit}
                            className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-[#51606b]"
                          >
                            {bit}
                          </span>
                        ))}
                      </div>
                      {labelExternalCodes.length > 0 ? (
                        <div className="mt-2 space-y-1">
                          {labelExternalCodes.map((code) => (
                            <p key={code} className="text-xs text-[#6b7280]">
                              {code}
                            </p>
                          ))}
                        </div>
                      ) : null}
                      {label.receiving_note ? (
                        <p className="mt-2 text-xs leading-5 text-[#6b7280]">
                          {t("receivingFlow.packageCardNotePrefix", "Dock note")}: {label.receiving_note}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onPrintLabels(label.label_code)}
                        disabled={label.status !== "received"}
                        className="rounded-xl border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#13212c]"
                      >
                        {t("receivingFlow.reprintAction", "Reprint")}
                      </button>
                      <StatusBadge status={label.status} />
                    </div>
                  </div>
                </div>
              )})}
            </div>
            <details className="rounded-2xl border border-[#e3ddd2] bg-[#fcfaf5] p-3 md:hidden">
              <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                {t("receivingFlow.mobilePrintQueueToggle", "Show confirmed labels")}
              </summary>
              <div className="mt-3 space-y-3">
                {receivingLabels
                  .filter((label) => label.status === "received")
                  .map((label) => (
                    <div key={label.id} className="rounded-2xl border border-[#e3ddd2] bg-white p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[#13212c]">{label.label_code}</p>
                          <p className="mt-1 text-xs text-[#61717d]">
                            {label.package_number != null
                              ? t("receivingFlow.packageCardTitle", "Package {number}", {
                                  number: label.package_number,
                                })
                              : t("receivingFlow.labelType", "Label type")}
                            {label.package_type ? ` · ${label.package_type}` : ""}
                          </p>
                        </div>
                        <span
                          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                            (label.print_count || 0) > 0
                              ? "bg-[#eef8f0] text-[#28543b]"
                              : "bg-[#fff6e6] text-[#91621a]"
                          }`}
                        >
                          {(label.print_count || 0) > 0
                            ? t("receivingFlow.internalLabelPrintedState", "Printed")
                            : t("receivingFlow.internalLabelPendingPrintState", "Print next")}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => onPrintLabels(label.label_code)}
                          disabled={label.status !== "received"}
                          className="rounded-xl border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#13212c]"
                        >
                          {t("receivingFlow.reprintAction", "Reprint")}
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </details>
          </div>
  );
}
