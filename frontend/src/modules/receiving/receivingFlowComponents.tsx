import WorkflowRecoveryPanel from "../../shared/components/WorkflowRecoveryPanel";
import type { RecoveryAction } from "./receivingFlowUtils";

type TranslationFn = (key: string, fallback: string, vars?: Record<string, string | number>) => string;

export function RecoveryPanel({
  code,
  title,
  body,
  actions,
  onAction,
  t,
}: {
  code: string;
  title: string;
  body: string;
  actions: RecoveryAction[];
  onAction: (action: RecoveryAction) => void;
  t: TranslationFn;
}) {
  const actionLabel = (action: RecoveryAction) => {
    switch (action) {
      case "back_to_orders":
        return t("receivingFlow.recoveryActionBackToOrders", "Back to work queue");
      case "clear_scan":
        return t("receivingFlow.recoveryActionClearScan", "Clear this scan");
      case "continue_next":
        return t("receivingFlow.recoveryActionContinueNext", "Skip this code and continue");
      case "review_receipts":
        return t("receivingFlow.recoveryActionReviewReceipts", "Review received items");
      case "review_inbound":
        return t("receivingFlow.recoveryActionReviewInbound", "Review and complete inbound");
      case "focus_staging":
        return t("receivingFlow.recoveryActionPickStaging", "Pick staging location");
      case "scan_again":
        return t("receivingFlow.recoveryActionScanAgain", "Try another scan");
      case "add_package":
        return t("receivingFlow.recoveryActionAddPackage", "Add the first package");
      case "open_next_package":
        return t("receivingFlow.recoveryActionOpenNextPackage", "Open next package");
      case "refresh_order":
        return t("receivingFlow.recoveryActionRefreshOrder", "Refresh status");
    }
  };

  const visibleActions: RecoveryAction[] =
    actions.length <= 2
      ? actions
      : Array.from(new Set([actions[0], actions.includes("back_to_orders") ? "back_to_orders" : actions[1]]));
  const safeExit =
    visibleActions.find((action) => action === "back_to_orders" || action === "review_inbound" || action === "refresh_order") ||
    visibleActions[visibleActions.length - 1];

  return (
    <WorkflowRecoveryPanel
      workflow="receiving"
      code={code}
      action={visibleActions[0]}
      safeExit={safeExit}
      title={title}
      body={body}
      recommendedActionLabel={actionLabel(visibleActions[0])}
      returnEntryLabel={actionLabel(safeExit)}
      labels={{
        whatHappened: t("recovery.whatHappened", "What happened"),
        whyBlocked: t("recovery.whyBlocked", "Why this cannot continue"),
        recommendedAction: t("recovery.recommendedAction", "Recommended action"),
        returnEntry: t("recovery.returnEntry", "Return entry"),
      }}
      actions={visibleActions.map((action, index) => (
        <button
          key={action}
          type="button"
          onClick={() => onAction(action)}
          data-testid={`receiving-recovery-action-${action}`}
          data-recovery-action={action}
          className={
            index === 0
              ? "min-h-[44px] rounded-xl border border-[#13212c] bg-[#13212c] px-3 py-2 text-sm font-semibold text-white sm:min-h-0 sm:rounded-full sm:py-1.5 sm:text-xs"
              : "min-h-[44px] rounded-xl border border-[#13212c]/10 bg-white px-3 py-2 text-sm font-semibold text-[#13212c] sm:min-h-0 sm:rounded-full sm:py-1.5 sm:text-xs"
          }
        >
          {actionLabel(action)}
        </button>
      ))}
    />
  );
}

export function ProcessSignal({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="min-h-[92px] rounded-2xl border border-[#d7d0c4] bg-[#fcfaf5] px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{label}</p>
      <div className="mt-2 flex items-end justify-between gap-3">
        <p className="text-2xl font-semibold tracking-[-0.02em] text-[#13212c]">{value}</p>
        <p className="max-w-[12rem] text-right text-xs leading-5 text-[#61717d]">{detail}</p>
      </div>
    </div>
  );
}

type ReceivingFlowStage = "choose" | "scan" | "review";

export function ReceivingFlowProgress({
  currentStage,
  t,
}: {
  currentStage: ReceivingFlowStage;
  t: TranslationFn;
}) {
  const stages: Array<{ id: ReceivingFlowStage; number: string; label: string; detail: string }> = [
    {
      id: "choose",
      number: "1",
      label: t("receivingFlow.progressChoose", "Choose work"),
      detail: t("receivingFlow.progressChooseDetail", "Pick the inbound order to open or continue."),
    },
    {
      id: "scan",
      number: "2",
      label: t("receivingFlow.progressScan", "Scan and receive"),
      detail: t("receivingFlow.progressScanDetail", "Confirm packages, quantities, and staging."),
    },
    {
      id: "review",
      number: "3",
      label: t("receivingFlow.progressReview", "Review and complete"),
      detail: t("receivingFlow.progressReviewDetail", "Check exceptions before releasing putaway work."),
    },
  ];
  const currentIndex = stages.findIndex((stage) => stage.id === currentStage);
  const activeStage = stages[Math.max(0, currentIndex)];

  return (
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white/88 p-3 shadow-[0_12px_28px_rgba(19,33,44,0.05)]">
      <div className="flex items-center justify-between gap-3 md:hidden">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
            {t("receivingFlow.progressEyebrow", "Receiving flow")}
          </p>
          <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">{activeStage.label}</p>
        </div>
        <span className="shrink-0 rounded-full border border-[#d7d0c4] bg-[#fbf8f2] px-3 py-1 text-xs font-semibold text-[#51606b]">
          {activeStage.number}/{stages.length}
        </span>
      </div>
      <p className="hidden text-[11px] uppercase tracking-[0.2em] text-[#7f8d98] md:block">
        {t("receivingFlow.progressEyebrow", "Receiving flow")}
      </p>
      <div className="mt-3 hidden gap-2 md:grid md:grid-cols-3">
        {stages.map((stage, index) => {
          const isActive = stage.id === currentStage;
          const isComplete = index < currentIndex;
          return (
            <div
              key={stage.id}
              aria-current={isActive ? "step" : undefined}
              className={`flex min-h-[74px] items-start gap-3 rounded-[1rem] border px-3 py-3 ${
                isActive
                  ? "border-[#24507a]/20 bg-[#eef3f8] text-[#13212c]"
                  : isComplete
                    ? "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]"
                    : "border-[#13212c]/8 bg-[#fbf8f2] text-[#61717d]"
              }`}
            >
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                  isActive
                    ? "bg-[#24507a] text-white"
                    : isComplete
                      ? "bg-[#28543b] text-white"
                      : "bg-white text-[#51606b]"
                }`}
              >
                {stage.number}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold leading-5">{stage.label}</span>
                <span className="mt-1 block text-xs leading-5 text-[#61717d]">{stage.detail}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
