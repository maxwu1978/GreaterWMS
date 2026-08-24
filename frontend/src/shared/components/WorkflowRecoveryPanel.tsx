import { type ReactNode } from "react";

type RecoveryTone = "info" | "warning" | "error" | "neutral";

const toneClasses: Record<RecoveryTone, string> = {
  info: "border-[#b7d3f4] bg-[#eef5ff] text-[#245da8]",
  warning: "border-[#e6c06a]/55 bg-[#fff8e8] text-[#8a5b00]",
  error: "border-[#e4c1b8] bg-[#fff1ed] text-[#8f3627]",
  neutral: "border-[#d6e2ef] bg-[#f4f8fb] text-[#51606b]",
};

export type WorkflowRecoveryPanelProps = {
  workflow: "receiving" | "putaway" | "picking" | "shipping";
  code: string;
  action: string;
  safeExit?: string;
  title: ReactNode;
  body: ReactNode;
  recommendedActionLabel: ReactNode;
  returnEntryLabel: ReactNode;
  labels: {
    whatHappened: string;
    whyBlocked: string;
    recommendedAction: string;
    returnEntry: string;
  };
  tone?: RecoveryTone;
  className?: string;
  bodyExtra?: ReactNode;
  actions: ReactNode;
  as?: "div" | "section";
  actionsClassName?: string;
};

export default function WorkflowRecoveryPanel({
  workflow,
  code,
  action,
  safeExit,
  title,
  body,
  recommendedActionLabel,
  returnEntryLabel,
  labels,
  tone = "neutral",
  className = "",
  bodyExtra,
  actions,
  as = "div",
  actionsClassName = "mt-3 grid gap-2 sm:flex sm:flex-wrap",
}: WorkflowRecoveryPanelProps) {
  const Container = as;
  const recoveryCode = code.includes(".") ? code : `${workflow}.${code}`;

  return (
    <Container
      className={`rounded-2xl border p-4 ${toneClasses[tone]} ${className}`}
      data-testid={`${workflow}-recovery-panel`}
      data-recovery-code={recoveryCode}
      data-recovery-action={action}
      data-recovery-safe-exit={safeExit}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div data-testid={`${workflow}-recovery-what-happened`}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98] opacity-80">
            {labels.whatHappened}
          </p>
          <p className="mt-1 text-sm font-semibold text-[#13212c]">{title}</p>
        </div>
        <div data-testid={`${workflow}-recovery-why-blocked`}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98] opacity-80">
            {labels.whyBlocked}
          </p>
          <p className="mt-1 text-sm leading-6">{body}</p>
          {bodyExtra}
        </div>
        <div data-testid={`${workflow}-recovery-recommended-action`}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98] opacity-80">
            {labels.recommendedAction}
          </p>
          <p className="mt-1 text-sm font-semibold text-[#13212c]">{recommendedActionLabel}</p>
        </div>
        <div data-testid={`${workflow}-recovery-return-entry`}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98] opacity-80">
            {labels.returnEntry}
          </p>
          <p className="mt-1 text-sm leading-6">{returnEntryLabel}</p>
        </div>
      </div>
      <div className={actionsClassName}>{actions}</div>
    </Container>
  );
}
