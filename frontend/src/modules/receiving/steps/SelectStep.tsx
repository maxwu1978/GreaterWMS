/**
 * Step 1 of the interactive receiving workflow: choose inbound work.
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import StatusBadge from "../../../shared/components/StatusBadge";
import { ReceivingFlowProgress } from "../receivingFlowComponents";
import { type InboundReceivableOrder } from "../receivingFlowUtils";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface SelectStepProps {
  t: Translator;
  orders: InboundReceivableOrder[];
  activeReceivingOrders: InboundReceivableOrder[];
  readyToOpenOrders: InboundReceivableOrder[];
  startPending: boolean;
  startPendingOrderId: string | null;
  onSelectOrder: (order: InboundReceivableOrder) => void;
}

export default function SelectStep({
  t,
  orders,
  activeReceivingOrders,
  readyToOpenOrders,
  startPending,
  startPendingOrderId,
  onSelectOrder,
}: SelectStepProps) {
  if (orders.length === 0) {
    return (
      <div className="space-y-4">
        <ReceivingFlowProgress currentStage="choose" t={t} />
        <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-white/88 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
            {t("receivingFlow.openSectionEyebrow", "Start next inbound")}
          </p>
          <h2 className="mt-2 text-lg font-semibold text-[#13212c]">
            {t("receivingFlow.selectEmptyTitle", "No inbound orders are waiting right now")}
          </h2>
          <p className="mt-3 text-sm leading-6 text-[#61717d]">
            {t(
              "receivingFlow.selectEmptyBody",
              "Receiving work is clear for now. Stay on this page only when the next inbound order actually needs dock action.",
            )}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ReceivingFlowProgress currentStage="choose" t={t} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            {t("receivingFlow.step1Title", "Choose inbound work")}
          </h2>
        </div>
        <button
          type="button"
          onClick={() => {
            const nextOrder = activeReceivingOrders[0] || readyToOpenOrders[0];
            if (nextOrder) {
              onSelectOrder(nextOrder);
            }
          }}
          disabled={(!activeReceivingOrders.length && !readyToOpenOrders.length) || startPending}
          className="rounded-xl border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-medium text-[#13212c] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {t("receivingFlow.jumpToScanner", "Jump to scanner")}
        </button>
      </div>
      <div className="space-y-4">
        <details
          open
          className="rounded-[1.2rem] border border-[#13212c]/8 bg-white/80 p-3 shadow-[0_12px_28px_rgba(19,33,44,0.05)]"
        >
          <summary className="cursor-pointer marker:text-[#7f8d98]">
            <span className="ml-2 inline-flex w-[calc(100%-1.5rem)] items-center justify-between gap-3 align-middle">
              <span className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
                {t("receivingFlow.resumeSectionEyebrow", "Continue receiving")}
              </span>
              <span className="rounded-full border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#51606b]">
                {activeReceivingOrders.length}
              </span>
            </span>
          </summary>
          {activeReceivingOrders.length === 0 ? (
            <div className="mt-3 rounded-2xl border border-dashed border-[#d8d1c5] bg-[#f7f3ec] p-4 text-sm text-[#7f8d98]">
              {t("receivingFlow.resumeSectionEmpty", "No inbound orders are currently mid-receipt.")}
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              {activeReceivingOrders.map((order) => (
                <button
                  key={order.id}
                  onClick={() => onSelectOrder(order)}
                  className="flex w-full items-center justify-between rounded-2xl bg-white p-4 shadow transition-colors hover:bg-blue-50"
                >
                  <div className="text-left">
                    <p className="font-medium">{order.order_number}</p>
                    <p className="text-sm text-gray-500">
                      {t("receivingFlow.refLabel", "Ref:")} {order.reference_number || "—"}
                    </p>
                    <p className="mt-2 inline-flex rounded-full bg-[#13212c] px-3 py-1 text-xs font-medium text-white">
                      {t("receivingFlow.resumeAction", "Continue receiving")}
                    </p>
                  </div>
                  <StatusBadge status={order.status} />
                </button>
              ))}
            </div>
          )}
        </details>

        <details
          open
          className="rounded-[1.2rem] border border-[#13212c]/8 bg-white/80 p-3 shadow-[0_12px_28px_rgba(19,33,44,0.05)]"
        >
          <summary className="cursor-pointer marker:text-[#7f8d98]">
            <span className="ml-2 inline-flex w-[calc(100%-1.5rem)] items-center justify-between gap-3 align-middle">
              <span className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
                {t("receivingFlow.openSectionEyebrow", "Start next inbound")}
              </span>
              <span className="rounded-full border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#51606b]">
                {readyToOpenOrders.length}
              </span>
            </span>
          </summary>
          {readyToOpenOrders.length === 0 ? (
            <div className="mt-3 rounded-2xl border border-dashed border-[#d8d1c5] bg-[#f7f3ec] p-4 text-sm text-[#7f8d98]">
              {t("receivingFlow.openSectionEmpty", "No inbound orders are waiting to be opened right now.")}
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              {readyToOpenOrders.map((order) => (
                <button
                  key={order.id}
                  onClick={() => onSelectOrder(order)}
                  disabled={startPending}
                  className="flex w-full items-center justify-between rounded-2xl bg-white p-4 shadow transition-colors hover:bg-blue-50"
                >
                  <div className="text-left">
                    <p className="font-medium">{order.order_number}</p>
                    <p className="text-sm text-gray-500">
                      {t("receivingFlow.refLabel", "Ref:")} {order.reference_number || "—"}
                    </p>
                    <p className="mt-2 inline-flex rounded-full bg-[#eef3f6] px-3 py-1 text-xs font-medium text-[#13212c]">
                      {startPendingOrderId === order.id
                        ? t("receivingFlow.prepareStarting", "Opening receiving...")
                        : t("receivingFlow.openAction", "Start receiving")}
                    </p>
                  </div>
                  <StatusBadge status={order.status} />
                </button>
              ))}
            </div>
          )}
        </details>
      </div>
    </div>
  );
}
