/**
 * Final step of the interactive receiving workflow: receiving complete.
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import { type CompleteReceivingSummary } from "../receivingFlowUtils";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface DoneStepProps {
  t: Translator;
  completeSummary: CompleteReceivingSummary | undefined;
  onGoToPutaway: () => void;
  onReceiveAnother: () => void;
}

export default function DoneStep({ t, completeSummary, onGoToPutaway, onReceiveAnother }: DoneStepProps) {
  return (
    <div className="text-center py-12">
      <div className="text-5xl mb-4">✓</div>
      <h2 className="text-xl font-bold text-green-700 mb-2">
        {t("receivingFlow.completeTitle", "Receiving Complete")}
      </h2>
      <p className="text-gray-500 mb-6">
        {t("receivingFlow.completeBody", "Putaway tasks have been created automatically.")}
      </p>
      {completeSummary ? (
        <div className="mx-auto mb-6 max-w-xl rounded-2xl border border-[#d7d0c4] bg-[#f8f4ec] p-4 text-left">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
            {t("receivingFlow.putawayHandoffTitle", "Putaway handoff")}
          </p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-[#e3ddd2] bg-white p-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("receivingFlow.putawayTaskCount", "Putaway tasks created")}
              </p>
              <p className="mt-2 text-lg font-semibold text-[#13212c]">
                {completeSummary.created_tasks}
              </p>
            </div>
            <div className="rounded-2xl border border-[#e3ddd2] bg-white p-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("receivingFlow.putawayUnitCount", "Units released to putaway")}
              </p>
              <p className="mt-2 text-lg font-semibold text-[#13212c]">
                {completeSummary.putaway_units}
              </p>
            </div>
          </div>
        </div>
      ) : null}
      <div className="flex justify-center gap-3">
        <button
          onClick={onGoToPutaway}
          className="px-6 py-2 bg-[#13212c] text-white rounded-lg font-medium"
        >
          {completeSummary
            ? t("receivingFlow.goToPutawayCount", "Go to putaway tasks ({count})", {
                count: completeSummary.created_tasks,
              })
            : t("receivingFlow.goToPutaway", "Go to Putaway")}
        </button>
        <button
          onClick={onReceiveAnother}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium"
        >
          {t("receivingFlow.receiveAnother", "Receive Another Order")}
        </button>
      </div>
    </div>
  );
}
