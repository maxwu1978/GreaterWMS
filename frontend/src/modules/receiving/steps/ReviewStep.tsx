/**
 * Step 4 of the interactive receiving workflow: review and complete receiving.
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import StatusBadge from "../../../shared/components/StatusBadge";
import { ReceivingFlowProgress, RecoveryPanel } from "../receivingFlowComponents";
import {
  type ReceivedLine,
  type ReceivingRecoveryState,
  type RecoveryAction,
} from "../receivingFlowUtils";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface ReviewStepProps {
  t: Translator;
  receivedLines: ReceivedLine[];
  completeErrorText: string;
  completeRecovery: ReceivingRecoveryState | null;
  completePending: boolean;
  onBackToScanning: () => void;
  onComplete: () => void;
  onRecoveryAction: (action: RecoveryAction) => void;
}

export default function ReviewStep({
  t,
  receivedLines,
  completeErrorText,
  completeRecovery,
  completePending,
  onBackToScanning,
  onComplete,
  onRecoveryAction,
}: ReviewStepProps) {
  const hasDiscrepancies = receivedLines.some((l) => l.status !== "exact");
  const exactCount = receivedLines.filter((line) => line.status === "exact").length;
  const shortCount = receivedLines.filter((line) => line.status === "short").length;
  const overCount = receivedLines.filter((line) => line.status === "over").length;
  const damagedUnits = receivedLines.reduce((sum, line) => sum + line.damaged, 0);
  const receivedUnits = receivedLines.reduce((sum, line) => sum + Math.max(0, line.received - line.damaged), 0);

  return (
    <div className="space-y-4">
      <ReceivingFlowProgress currentStage="review" t={t} />
      <h2 className="text-lg font-semibold">
        {t("receivingFlow.step3Title", "Review and complete receiving")}
      </h2>

      <div className="bg-white rounded-lg shadow p-4">
        <div className="mb-4 grid gap-3 md:grid-cols-4">
          <div className="rounded-2xl border border-[#e3ddd2] bg-[#f8f4ec] p-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
              {t("receivingFlow.reviewExact", "Exact")}
            </p>
            <p className="mt-2 text-sm font-semibold text-[#13212c]">{exactCount}</p>
          </div>
          <div className="rounded-2xl border border-[#f3d7a8] bg-[#fff7e8] p-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#b07100]">
              {t("receivingFlow.reviewOver", "Over")}
            </p>
            <p className="mt-2 text-sm font-semibold text-[#8a5600]">{overCount}</p>
          </div>
          <div className="rounded-2xl border border-[#cfe0f4] bg-[#f0f7ff] p-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#436b9d]">
              {t("receivingFlow.reviewShort", "Short")}
            </p>
            <p className="mt-2 text-sm font-semibold text-[#2d4d77]">{shortCount}</p>
          </div>
          <div className="rounded-2xl border border-[#f2c2b4] bg-[#fff1eb] p-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#9b452a]">
              {t("receivingFlow.reviewDamaged", "Damaged units")}
            </p>
            <p className="mt-2 text-sm font-semibold text-[#7c2f19]">{damagedUnits}</p>
          </div>
        </div>
        <h3 className="text-sm font-medium text-gray-700 mb-3">
          {t("receivingFlow.receiptSummary", "Receipt Summary")}
        </h3>
        {receivedLines.map((line, i) => (
          <div
            key={i}
            className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
          >
            <span className="text-sm font-medium">{line.sku_id}</span>
            <div className="flex items-center gap-4 text-sm">
              <span>
                {t("receivingFlow.expectedLabel", "Expected:")} {line.expected}
              </span>
              <span>
                {t("receivingFlow.receivedLabel", "Received:")} {line.received}
              </span>
              {line.discrepancy_qty ? (
                <span className={line.discrepancy_qty > 0 ? "text-amber-600" : "text-blue-600"}>
                  {line.discrepancy_qty > 0
                    ? t("receivingFlow.overShort", "Over: {count}", { count: line.discrepancy_qty })
                    : t("receivingFlow.shortShort", "Short: {count}", {
                        count: Math.abs(line.discrepancy_qty),
                      })}
                </span>
              ) : null}
              <StatusBadge status={line.status} />
            </div>
          </div>
        ))}
      </div>

      {hasDiscrepancies && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="text-sm text-yellow-800 font-medium">
            {t(
              "receivingFlow.discrepancyNotice",
              "Discrepancies detected. Putaway tasks will be created for actual received quantities."
            )}
          </p>
          <p className="mt-2 text-sm text-yellow-700">
            {t(
              "receivingFlow.discrepancySummary",
              "The warehouse will release {count} good units into putaway after you complete this receipt.",
              { count: receivedUnits },
            )}
          </p>
        </div>
      )}

      {!completeErrorText ? (
        <div className="flex gap-3">
          <button
            onClick={onBackToScanning}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium"
          >
            ← {t("receivingFlow.backToScanning", "Back to Scanning")}
          </button>
          <button
            onClick={onComplete}
            disabled={completePending}
            className="px-6 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
          >
            {completePending
              ? t("receivingFlow.completing", "Completing...")
              : `${t("receivingFlow.completeReceiving", "Complete Receiving")} ✓`}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-sm text-[#9b452a]">
            {completeErrorText}
          </p>
          {completeRecovery ? (
            <RecoveryPanel
              code={completeRecovery.code}
              title={completeRecovery.title}
              body={completeRecovery.body}
              actions={completeRecovery.actions}
              onAction={onRecoveryAction}
              t={t}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
