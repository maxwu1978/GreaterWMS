/**
 * Color-coded status badge for orders, tasks, and invoices.
 */

import clsx from "clsx";
import { useI18n } from "../i18n";

const statusColors: Record<string, string> = {
  // Orders
  draft: "bg-gray-100 text-gray-600",
  expected: "bg-blue-100 text-blue-700",
  arrived: "bg-indigo-100 text-indigo-700",
  receiving: "bg-yellow-100 text-yellow-700",
  putaway: "bg-orange-100 text-orange-700",
  pending: "bg-yellow-100 text-yellow-700",
  allocated: "bg-blue-100 text-blue-700",
  picking: "bg-purple-100 text-purple-700",
  picked: "bg-indigo-100 text-indigo-700",
  packing: "bg-pink-100 text-pink-700",
  packed: "bg-teal-100 text-teal-700",
  shipped: "bg-green-100 text-green-700",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-600",
  // Tasks
  assigned: "bg-blue-100 text-blue-700",
  in_progress: "bg-yellow-100 text-yellow-700",
  failed: "bg-red-100 text-red-600",
  // Invoices
  sent: "bg-blue-100 text-blue-700",
  paid: "bg-green-100 text-green-700",
  overdue: "bg-red-100 text-red-600",
};

export default function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const color = statusColors[status] || "bg-gray-100 text-gray-600";
  return (
    <span className={clsx("inline-flex shrink-0 whitespace-nowrap px-2 py-0.5 rounded-full text-xs font-medium leading-none", color)}>
      {t(`status.${status}`, status.replace(/_/g, " "))}
    </span>
  );
}
