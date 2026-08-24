/**
 * Scan step: receipt correction panel (fix quantities, staging, references).
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import {
  type InboundPackageSummary,
} from "../receivingFlowUtils";
import {
  type CorrectionAction,
  type CorrectionState,
} from "../receivingFlowState";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface ReceiptCorrectionPanelProps {
  t: Translator;
  correction: CorrectionState;
  dispatchCorrection: (patch: CorrectionAction) => void;
  packageRecords: InboundPackageSummary[];
  stagingLocations: any[];
  canCorrectPackageQuantity: (pkg: InboundPackageSummary) => boolean;
  saving: boolean;
  onSubmit: () => void;
  onCancel: () => void;
}

export default function ReceiptCorrectionPanel({
  t,
  correction,
  dispatchCorrection,
  packageRecords,
  stagingLocations,
  canCorrectPackageQuantity,
  saving,
  onSubmit,
  onCancel,
}: ReceiptCorrectionPanelProps) {
  if (!correction.packageId) return null;
          const packageToCorrect = packageRecords.find((pkg) => pkg.id === correction.packageId);
          if (!packageToCorrect) return null;
          const quantityEditable = canCorrectPackageQuantity(packageToCorrect);
          return (
            <div id="receiving-receipt-correction" className="rounded-2xl border border-[#d6e2ef] bg-[#f4f8fb] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("receivingFlow.correctionEyebrow", "Correct receipt")}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-[#13212c]">
                    {t("receivingFlow.packageCardTitle", "Package {number}", {
                      number: packageToCorrect.package_number,
                    })}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[#51606b]">
                    {quantityEditable
                      ? t(
                          "receivingFlow.correctionBodyEditable",
                          "Update quantities while this package is still before putaway. Inventory will be corrected with an adjustment transaction.",
                        )
                      : t(
                          "receivingFlow.correctionBodyLocked",
                          "Quantity is locked after putaway release. You can still correct references, measurements, and notes.",
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

              <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <section className="space-y-3">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                    {t("receivingFlow.quantityEyebrow", "Receipt quantity")}
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.receiveSkuQty", "Receive SKU qty")}
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={correction.receivedQty}
                        onChange={(e) => dispatchCorrection({ receivedQty: e.target.value })}
                        disabled={!quantityEditable || saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c] disabled:bg-[#f4f4f4]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.damagedSkuQty", "Damaged SKU qty")}
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={correction.damagedQty}
                        onChange={(e) => dispatchCorrection({ damagedQty: e.target.value })}
                        disabled={!quantityEditable || saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c] disabled:bg-[#f4f4f4]"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500">
                      {t("receivingFlow.stagingLocation", "Staging Location")}
                    </label>
                    <select
                      value={correction.stagingLocation}
                      onChange={(e) => dispatchCorrection({ stagingLocation: e.target.value })}
                      disabled={!quantityEditable || saving}
                      className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c] disabled:bg-[#f4f4f4]"
                    >
                      <option value="">{t("receivingFlow.chooseStagingLocation", "Choose staging location")}</option>
                      {stagingLocations.map((location: any) => (
                        <option key={location.id} value={location.id}>
                          {location.barcode} · {location.location_type}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.packageCount", "Contained boxes")}
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={correction.packageCount}
                        onChange={(e) => dispatchCorrection({ packageCount: e.target.value })}
                        disabled={!quantityEditable || saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c] disabled:bg-[#f4f4f4]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.palletCount", "Pallets Quantity")}</label>
                      <input
                        type="number"
                        min={0}
                        value={correction.palletCount}
                        onChange={(e) => dispatchCorrection({ palletCount: e.target.value })}
                        disabled={!quantityEditable || saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c] disabled:bg-[#f4f4f4]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.rentFreeDays", "Rent-free period (days)")}</label>
                      <input
                        type="number"
                        min={0}
                        value={correction.rentFreeDays}
                        onChange={(e) => dispatchCorrection({ rentFreeDays: e.target.value })}
                        disabled={!quantityEditable || saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c] disabled:bg-[#f4f4f4]"
                      />
                    </div>
                  </div>
                </section>

                <section className="space-y-3">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                    {t("receivingFlow.correctionReferences", "References and measurements")}
                  </p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.detectedCodeTracking", "Tracking Number")}</label>
                      <input
                        type="text"
                        value={correction.tracking}
                        onChange={(e) => dispatchCorrection({ tracking: e.target.value })}
                        disabled={saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.detectedCodeCarton", "Carton Mark")}</label>
                      <input
                        type="text"
                        value={correction.carton}
                        onChange={(e) => dispatchCorrection({ carton: e.target.value })}
                        disabled={saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.detectedCodeCustomerBarcode", "Customer Box Code")}
                      </label>
                      <input
                        type="text"
                        value={correction.customerCode}
                        onChange={(e) => dispatchCorrection({ customerCode: e.target.value })}
                        disabled={saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                      />
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-4">
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.grossWeightKg", "Gross weight (kg)")}</label>
                      <input
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.001"
                        value={correction.weightKg}
                        onChange={(e) => dispatchCorrection({ weightKg: e.target.value })}
                        disabled={saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.outerLengthCm", "Outer L (cm)")}</label>
                      <input
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.01"
                        value={correction.lengthCm}
                        onChange={(e) => dispatchCorrection({ lengthCm: e.target.value })}
                        disabled={saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.outerWidthCm", "Outer W (cm)")}</label>
                      <input
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.01"
                        value={correction.widthCm}
                        onChange={(e) => dispatchCorrection({ widthCm: e.target.value })}
                        disabled={saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">{t("receivingFlow.outerHeightCm", "Outer H (cm)")}</label>
                      <input
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.01"
                        value={correction.heightCm}
                        onChange={(e) => dispatchCorrection({ heightCm: e.target.value })}
                        disabled={saving}
                        className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500">{t("receivingFlow.receivingNote", "Receiving note")}</label>
                    <textarea
                      value={correction.note}
                      onChange={(e) => dispatchCorrection({ note: e.target.value })}
                      disabled={saving}
                      rows={3}
                      className="mt-1 w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                    />
                  </div>
                </section>
              </div>

              {correction.error ? (
                <p className="mt-3 rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-sm text-[#9b452a]">
                  {correction.error}
                </p>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={onSubmit}
                  disabled={saving}
                  className="rounded-xl bg-[#13212c] px-4 py-2 text-sm font-medium text-white disabled:opacity-45"
                >
                  {saving
                    ? t("receivingFlow.correctionSaving", "Saving correction...")
                    : t("receivingFlow.correctionSaveAction", "Save correction")}
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
