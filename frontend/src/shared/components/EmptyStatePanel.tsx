import clsx from "clsx";

interface EmptyStatePanelProps {
  title: string;
  message: string;
  hint?: string;
  actionHref?: string;
  actionLabel?: string;
  className?: string;
}

export default function EmptyStatePanel({ title, message, hint, actionHref, actionLabel, className }: EmptyStatePanelProps) {
  return (
    <div className={clsx("mx-auto max-w-md rounded-[1.4rem] border border-[#13212c]/8 bg-[#fbf8f2] px-5 py-6 text-center", className)}>
      <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8c97]">{title}</p>
      <p className="mt-3 text-sm leading-7 text-[#61717d]">{message}</p>
      {hint && <p className="mt-2 text-sm leading-6 text-[#8b98a3]">{hint}</p>}
      {actionLabel && actionHref && (
        <a
          href={actionHref}
          className="mt-4 inline-flex items-center justify-center rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1d3040]"
        >
          {actionLabel}
        </a>
      )}
    </div>
  );
}
