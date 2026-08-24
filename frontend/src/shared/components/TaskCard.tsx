import clsx from "clsx";
import { type MouseEventHandler, type ReactNode } from "react";
import { Link } from "react-router-dom";

type TaskCardTone = "neutral" | "success" | "warning" | "danger";

interface TaskCardProps {
  label?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  chips?: ReactNode;
  action?: ReactNode;
  selected?: boolean;
  tone?: TaskCardTone;
  to?: string;
  onClick?: MouseEventHandler<HTMLElement>;
  className?: string;
}

const toneClasses: Record<TaskCardTone, string> = {
  neutral: "border-[#13212c]/10 bg-white hover:border-[#13212c]/20 hover:bg-[#fbf8f2]",
  success: "border-[#c8dfd1] bg-[#f7fbf8] hover:border-[#9fcaad]",
  warning: "border-[#f0d9a4] bg-[#fffaf0] hover:border-[#dfbd72]",
  danger: "border-[#f2c8bd] bg-[#fff7f3] hover:border-[#dd9b88]",
};

const selectedClasses = "border-[#24507a]/45 bg-[#eef3f8] text-[#13212c] shadow-sm";
const interactiveClasses = "cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#13212c]/35 focus-visible:ring-offset-2";

export default function TaskCard({ label, title, meta, chips, action, selected = false, tone = "neutral", to, onClick, className }: TaskCardProps) {
  const interactive = Boolean(to || onClick);
  const classes = clsx(
    "group flex w-full items-start justify-between gap-3 rounded-lg border p-3 text-left transition",
    selected ? selectedClasses : toneClasses[tone],
    interactive && interactiveClasses,
    className,
  );
  const content = (
    <>
      <div className="min-w-0 flex-1">
        {label ? (
          <div className={clsx("text-[10px] font-semibold uppercase tracking-[0.16em]", selected ? "text-[#24507a]" : "text-[#7f8d98]")}>{label}</div>
        ) : null}
        <div className="mt-1 break-words text-sm font-semibold text-[#13212c]">{title}</div>
        {meta ? <div className={clsx("mt-1 text-xs leading-5", selected ? "text-[#51606b]" : "text-[#61717d]")}>{meta}</div> : null}
        {chips ? <div className="mt-2 flex flex-wrap gap-1.5">{chips}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </>
  );

  if (to) {
    return (
      <Link to={to} className={classes} aria-current={selected ? "page" : undefined}>
        {content}
      </Link>
    );
  }

  if (onClick) {
    return (
      <button type="button" className={classes} onClick={onClick} aria-pressed={selected}>
        {content}
      </button>
    );
  }

  return <article className={classes}>{content}</article>;
}
