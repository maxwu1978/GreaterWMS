import { Link } from "react-router-dom";

type UpstreamActionLinkProps = {
  to: string;
  label: string;
  className?: string;
};

export default function UpstreamActionLink({ to, label, className = "" }: UpstreamActionLinkProps) {
  return (
    <Link
      to={to}
      className={`inline-flex items-center justify-center rounded-full border border-[#13212c]/12 bg-white px-5 py-3 text-center text-sm font-semibold uppercase leading-tight tracking-[0.14em] text-[#13212c] transition hover:bg-[#f7f4ee] ${className}`}
    >
      {label}
    </Link>
  );
}
