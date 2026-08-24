import clsx from "clsx";
import { type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";

type PillTone = "neutral" | "active" | "success" | "warning" | "danger";

interface PillBaseProps {
  active?: boolean;
  count?: ReactNode;
  tone?: PillTone;
}

type PillButtonProps = PillBaseProps &
  ButtonHTMLAttributes<HTMLButtonElement> & {
    as?: "button";
  };

type PillSpanProps = PillBaseProps &
  HTMLAttributes<HTMLSpanElement> & {
    as: "span";
  };

type PillProps = PillButtonProps | PillSpanProps;

const toneClasses: Record<PillTone, string> = {
  neutral: "border-[#13212c]/10 bg-white text-[#61717d]",
  active: "border-[#13212c] bg-[#13212c] text-[#f4efe8]",
  success: "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]",
  warning: "border-[#f0d9a4] bg-[#fff7e8] text-[#91621a]",
  danger: "border-[#f2c8bd] bg-[#fff1eb] text-[#9b452a]",
};

const baseClasses =
  "inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition disabled:cursor-not-allowed disabled:opacity-50";

export default function Pill(props: PillProps) {
  const { active = false, count, tone = "neutral", className, children, as = "button" } = props;
  const resolvedTone = active ? "active" : tone;
  const classes = clsx(baseClasses, toneClasses[resolvedTone], className);
  const countNode =
    count !== undefined ? (
      <span className={clsx("rounded-full px-2 py-0.5 text-[10px]", active ? "bg-white/12 text-[#f4efe8]" : "bg-[#f7f4ee] text-[#61717d]")}>
        {count}
      </span>
    ) : null;

  if (as === "span") {
    const { active: _active, as: _as, count: _count, tone: _tone, className: _className, children: _children, ...spanProps } = props;

    return (
      <span className={classes} {...spanProps}>
        <span>{children}</span>
        {countNode}
      </span>
    );
  }

  const buttonSource = props as PillButtonProps;
  const { active: _active, as: _as, count: _count, tone: _tone, className: _className, children: _children, type = "button", ...buttonProps } = buttonSource;

  return (
    <button type={type} className={classes} {...buttonProps}>
      <span>{children}</span>
      {countNode}
    </button>
  );
}
