import clsx from "clsx";
import { type HTMLAttributes, type ReactNode } from "react";

interface EyebrowProps extends HTMLAttributes<HTMLParagraphElement> {
  children: ReactNode;
}

export default function Eyebrow({ children, className, ...props }: EyebrowProps) {
  return (
    <p className={clsx("text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f8d98]", className)} {...props}>
      {children}
    </p>
  );
}
