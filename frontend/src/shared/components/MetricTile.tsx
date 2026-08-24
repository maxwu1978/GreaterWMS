import clsx from "clsx";
import { type ReactNode } from "react";
import { Link } from "react-router-dom";

type MetricTileTone = "neutral" | "success" | "warning" | "danger";
type MetricTileDensity = "regular" | "compact";

interface MetricTileProps {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: MetricTileTone;
  density?: MetricTileDensity;
  to?: string;
  className?: string;
}

const toneClasses: Record<MetricTileTone, string> = {
  neutral: "border-[#13212c]/8 bg-white text-[#13212c]",
  success: "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]",
  warning: "border-[#f0d9a4] bg-[#fff7e8] text-[#91621a]",
  danger: "border-[#f2c8bd] bg-[#fff1eb] text-[#9b452a]",
};

export default function MetricTile({
  label,
  value,
  detail,
  tone = "neutral",
  density = "regular",
  to,
  className,
}: MetricTileProps) {
  const content = (
    <>
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">{label}</p>
      <p className={clsx("font-semibold tracking-[-0.03em]", density === "compact" ? "mt-1 text-2xl" : "mt-2 text-3xl")}>{value}</p>
      {detail ? (
        <p className={clsx("text-sm leading-6 text-[#61717d]", density === "compact" ? "mt-1.5" : "mt-2")}>{detail}</p>
      ) : null}
    </>
  );

  const classNames = clsx(
    "block rounded-[1.3rem] border px-4 py-4 shadow-[0_12px_28px_rgba(19,33,44,0.04)]",
    toneClasses[tone],
    to && "transition hover:border-[#13212c]/18 hover:bg-[#fffdfa] hover:shadow-[0_18px_38px_rgba(19,33,44,0.07)]",
    density === "compact" && "py-3",
    className,
  );

  if (to) {
    return (
      <Link to={to} className={classNames}>
        {content}
      </Link>
    );
  }

  return <div className={classNames}>{content}</div>;
}
