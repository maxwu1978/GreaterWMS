import clsx from "clsx";
import { type ButtonHTMLAttributes } from "react";

type ActionButtonVariant = "primary" | "secondary" | "success" | "danger";

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ActionButtonVariant;
}

const variantClasses: Record<ActionButtonVariant, string> = {
  primary: "border-[#13212c] bg-[#13212c] text-[#f4efe8] hover:bg-[#1d3040]",
  secondary: "border-[#13212c]/10 bg-white text-[#13212c] hover:bg-[#f7f4ee]",
  success: "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b] hover:bg-[#e2f4e6]",
  danger: "border-[#f2c8bd] bg-[#fff1eb] text-[#9b452a] hover:bg-[#ffe6dc]",
};

export default function ActionButton({ variant = "primary", className, children, type = "button", ...props }: ActionButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-full border px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] transition disabled:cursor-not-allowed disabled:opacity-50",
        variantClasses[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
