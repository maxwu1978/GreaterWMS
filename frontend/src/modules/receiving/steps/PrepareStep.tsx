/**
 * Step 2 of the interactive receiving workflow: open an inbound order for receiving.
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import { ReceivingFlowProgress } from "../receivingFlowComponents";
import { type InboundReceivableOrder } from "../receivingFlowUtils";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface PrepareStepProps {
  t: Translator;
  order: InboundReceivableOrder;
  startPending: boolean;
  printableLabelCount: number;
  printError: string;
  onBack: () => void;
  onStartReceiving: () => void;
  onPrintLabels: () => void;
}

export default function PrepareStep({
  t,
  order,
  startPending,
  printableLabelCount,
  printError,
  onBack,
  onStartReceiving,
  onPrintLabels,
}: PrepareStepProps) {
  return (
    <div className="space-y-4">
      <ReceivingFlowProgress currentStage="choose" t={t} />
      <div className="rounded-2xl bg-white p-5 shadow">
        <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
          {t("receivingFlow.prepareEyebrow", "Expected arrival")}
        </p>
        <h2 className="mt-2 text-lg font-semibold text-[#13212c]">
          {t("receivingFlow.prepareTitle", "Open this inbound order for receiving")}
        </h2>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-[#e3ddd2] bg-[#f8f4ec] p-4">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
              {t("receivingFlow.prepareOrderLabel", "Inbound order")}
            </p>
            <p className="mt-2 text-base font-semibold text-[#13212c]">{order.order_number}</p>
          </div>
          <div className="rounded-2xl border border-[#e3ddd2] bg-[#f8f4ec] p-4">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
              {t("receivingFlow.prepareRefLabel", "Reference")}
            </p>
            <p className="mt-2 text-base font-semibold text-[#13212c]">
              {order.reference_number || "—"}
            </p>
          </div>
          <div className="rounded-2xl border border-[#e3ddd2] bg-[#f8f4ec] p-4">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
              {t("receivingFlow.prepareStatusLabel", "What changes now")}
            </p>
            <p className="mt-2 text-sm font-medium text-[#13212c]">{t("receivingFlow.prepareStatusShort", "Expected → receiving")}</p>
          </div>
        </div>

        <div className="mt-4">
          <span className="rounded-full border border-[#d7d0c4] bg-[#fff8ea] px-3 py-1.5 text-xs font-medium text-[#6b5a22]">
            {t("receivingFlow.prepareNoticeShort", "Only open receiving once dock work has actually started.")}
          </span>
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <button
            onClick={onBack}
            className="rounded-xl bg-[#eef2f5] px-4 py-2 text-sm font-medium text-[#13212c]"
          >
            {t("receivingFlow.prepareBack", "Back to inbound list")}
          </button>
          <button
            onClick={onStartReceiving}
            disabled={startPending}
            className="rounded-xl bg-[#13212c] px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {startPending
              ? t("receivingFlow.prepareStarting", "Opening receiving...")
              : t("receivingFlow.prepareConfirm", "Start receiving")}
          </button>
          {printableLabelCount > 0 ? (
            <button
              type="button"
              onClick={onPrintLabels}
              className="rounded-xl border border-[#13212c]/10 bg-white px-5 py-2 text-sm font-medium text-[#13212c]"
            >
              {t("receivingFlow.printInternalLabelsAction", "Print labels")}
            </button>
          ) : null}
        </div>
        {printError ? (
          <p className="mt-3 rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-sm text-[#9b452a]">
            {printError}
          </p>
        ) : null}

      </div>
    </div>
  );
}
