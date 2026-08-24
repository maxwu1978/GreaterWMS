import { ArrowLeft } from "lucide-react";

export type MobileFlowStepStatus = "done" | "active" | "pending";

export interface MobileFlowStepItem {
  key: string;
  number: string;
  label: string;
  status: MobileFlowStepStatus;
}

interface MobileFlowGuideProps {
  eyebrow: string;
  contextTitle: string;
  title: string;
  hint: string;
  steps: MobileFlowStepItem[];
  backLabel: string;
  onBack: () => void;
  className?: string;
  compact?: boolean;
}

export default function MobileFlowGuide({
  eyebrow,
  contextTitle,
  title,
  hint,
  steps,
  backLabel,
  onBack,
  className = "",
  compact = false,
}: MobileFlowGuideProps) {
  if (compact) {
    const activeStep = steps.find((step) => step.status === "active") || steps[0];

    return (
      <div className={`max-w-full overflow-hidden rounded-2xl border border-[#13212c]/8 bg-white p-3 shadow md:hidden ${className}`}>
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[#13212c]/10 bg-[#fbf8f2] px-3 py-1.5 text-xs font-semibold text-[#13212c]"
          >
            <ArrowLeft size={14} />
            {backLabel}
          </button>
          <p className="min-w-0 truncate text-xs font-semibold text-[#51606b]">{contextTitle}</p>
        </div>

        <div className="mt-3 flex min-w-0 items-center gap-1.5">
          {steps.map((step) => (
            <div
              key={step.key}
              aria-current={step.status === "active" ? "step" : undefined}
              className={`flex min-w-0 flex-1 items-center justify-center gap-1 rounded-full border px-2 py-1.5 text-[11px] font-semibold ${
                step.status === "done"
                  ? "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]"
                  : step.status === "active"
                    ? "border-[#24507a]/20 bg-[#24507a] text-white"
                    : "border-[#e3ddd2] bg-[#fcfaf5] text-[#7f8d98]"
              }`}
            >
              <span>{step.status === "done" ? "✓" : step.number}</span>
              {step.status === "active" ? <span className="truncate">{step.label}</span> : null}
            </div>
          ))}
        </div>

        <div className="mt-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
            {eyebrow} · {activeStep.label}
          </p>
          <p className="mt-1 text-base font-semibold leading-snug text-[#13212c]">{title}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`max-w-full overflow-hidden rounded-2xl border border-[#13212c]/8 bg-white p-4 shadow md:hidden ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{eyebrow}</p>
          <h2 className="mt-1 break-words text-base font-semibold leading-snug text-[#13212c]">{contextTitle}</h2>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[#13212c]/10 bg-[#fbf8f2] px-3 py-1.5 text-xs font-semibold text-[#13212c]"
        >
          <ArrowLeft size={14} />
          {backLabel}
        </button>
      </div>

      <div className="mt-4 grid min-w-0 gap-1.5" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((step) => (
          <div
            key={step.key}
            aria-current={step.status === "active" ? "step" : undefined}
            className={`min-w-0 rounded-xl border px-1.5 py-2 text-center ${
              step.status === "done"
                ? "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]"
                : step.status === "active"
                  ? "border-[#24507a]/20 bg-[#eef3f8] text-[#13212c]"
                  : "border-[#e3ddd2] bg-[#fcfaf5] text-[#7f8d98]"
            }`}
          >
            <div
              className={`mx-auto flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                step.status === "done"
                  ? "bg-[#28543b] text-white"
                  : step.status === "active"
                    ? "bg-[#24507a] text-white"
                    : "bg-white text-[#7f8d98]"
              }`}
            >
              {step.status === "done" ? "✓" : step.number}
            </div>
            <p className="mt-1 break-words text-[11px] font-semibold leading-tight">{step.label}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-xl border border-[#d7e4ef] bg-[#f3f8fb] px-3 py-3">
        <p className="text-sm font-semibold text-[#13212c]">{title}</p>
        <p className="mt-1 text-xs leading-5 text-[#51606b]">{hint}</p>
      </div>
    </div>
  );
}
