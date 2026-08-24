export type PackageOperationFilter =
  | "all"
  | "needs_action"
  | "supervisor_review"
  | "package_open"
  | "putaway_pending"
  | "print_pending"
  | "prebooked"
  | "dock_created"
  | "recently_changed";

export type ExceptionOwnerLane = "all" | "receiving" | "print" | "putaway" | "review";

export type ReceivingPackageFocus =
  | "needs_action"
  | "package_open"
  | "print_pending"
  | "prebooked"
  | "dock_created"
  | null;

export type SelectedReceiveOrder = {
  id: string;
  status: string;
  nonce: number;
  packageFocus: ReceivingPackageFocus;
  packageId: string | null;
  printPackageId: string | null;
  packageNumber: number | null;
};

export type QueueAction =
  | { kind: "receive"; focus: ReceivingPackageFocus }
  | { kind: "putaway" }
  | { kind: "detail" };

type Translate = (key: string, fallback: string, vars?: Record<string, string | number>) => string;

export const RECENT_ACTIVITY_WINDOW_HOURS = 12;
export const LAST_RECEIVING_ORDER_STORAGE_KEY = "receiving.lastActiveOrder";

const RECEIVING_STAGE_STATUSES = new Set(["expected", "arrived", "receiving"]);

export function isReceivingStageOrder(order: any): boolean {
  return !order?.archived && !order?.voided && RECEIVING_STAGE_STATUSES.has(order?.status || "");
}

export function isPutawayHandoffOrder(order: any): boolean {
  return (
    !order?.archived &&
    !order?.voided &&
    order?.status === "putaway" &&
    Number(order?.packages_putaway_pending || 0) > 0
  );
}

export function latestActivityTimestamp(order: any): number {
  const parsed = Date.parse(order?.latest_activity_at || "");
  return Number.isFinite(parsed) ? parsed : 0;
}

export function isRecentlyChangedOrder(order: any, recentCutoff: number): boolean {
  const parsed = latestActivityTimestamp(order);
  return parsed > 0 && parsed >= recentCutoff;
}

export function hasNonDefaultRecordState(order: any): boolean {
  return Boolean(order?.archived || order?.voided);
}

function normalizedSystemReference(value: string | null | undefined): string {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/^((REF|INB)-)+/, "");
}

export function displayInboundReference(order: any): string {
  const reference = String(order?.reference_number || "").trim();
  if (!reference) return "—";
  const orderNumber = String(order?.order_number || "").trim();
  if (orderNumber && normalizedSystemReference(reference) === normalizedSystemReference(orderNumber)) {
    return "—";
  }
  return reference;
}

export function formatRecentActivityLabel(order: any, t: Translate) {
  const timestamp = latestActivityTimestamp(order);
  if (!timestamp) {
    return t("receiving.recentActivityUnknown", "No package activity recorded yet");
  }
  const diffMs = Math.max(0, Date.now() - timestamp);
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return t("receiving.recentActivityNow", "just now");
  if (minutes < 60) return t("receiving.recentActivityMinutes", "{count}m ago", { count: String(minutes) });
  const hours = Math.round(minutes / 60);
  if (hours < 48) return t("receiving.recentActivityHours", "{count}h ago", { count: String(hours) });
  const days = Math.round(hours / 24);
  return t("receiving.recentActivityDays", "{count}d ago", { count: String(days) });
}

export function operationalReasonsForOrder(order: any, recentCutoff: number, t: Translate) {
  const reasons: string[] = [];
  const hasMixedOrigin = (order?.packages_prebooked || 0) > 0 && (order?.packages_dock_created || 0) > 0;
  if (order?.supervisor_review_needed && hasMixedOrigin) {
    reasons.push(t("receiving.reasonSupervisorReview", "Mixed package origins still need review"));
  }
  if ((order?.packages_open || 0) > 0) {
    reasons.push(
      t("receiving.reasonPackagesOpen", "{count} packages still open", {
        count: String(order.packages_open || 0),
      }),
    );
  }
  if ((order?.internal_labels_print_pending || 0) > 0) {
    reasons.push(
      t("receiving.reasonPrintPending", "{count} labels still waiting to print", {
        count: String(order.internal_labels_print_pending || 0),
      }),
    );
  }
  if ((order?.packages_putaway_pending || 0) > 0) {
    reasons.push(
      t("receiving.reasonPutawayPending", "{count} packages still waiting on putaway", {
        count: String(order.packages_putaway_pending || 0),
      }),
    );
  }
  if ((order?.packages_prebooked || 0) > 0) {
    reasons.push(
      t("receiving.reasonPrebooked", "{count} pre-booked packages", {
        count: String(order.packages_prebooked || 0),
      }),
    );
  }
  if ((order?.packages_dock_created || 0) > 0) {
    reasons.push(
      t("receiving.reasonDockCreated", "{count} dock-opened packages", {
        count: String(order.packages_dock_created || 0),
      }),
    );
  }
  if (isRecentlyChangedOrder(order, recentCutoff)) {
    reasons.push(
      t("receiving.reasonRecentlyChanged", "Changed in the last {hours} hours", {
        hours: String(RECENT_ACTIVITY_WINDOW_HOURS),
      }),
    );
  }
  return reasons;
}

export function recommendedFilterForOrder(order: any, recentCutoff: number): PackageOperationFilter | null {
  if (order?.supervisor_review_needed) return "supervisor_review";
  if ((order?.packages_open || 0) > 0 && (order?.packages_dock_created || 0) > 0) return "dock_created";
  if ((order?.packages_open || 0) > 0 && (order?.packages_prebooked || 0) > 0) return "prebooked";
  if ((order?.packages_open || 0) > 0) return "package_open";
  if ((order?.internal_labels_print_pending || 0) > 0) return "print_pending";
  if ((order?.packages_putaway_pending || 0) > 0) return "putaway_pending";
  if (isRecentlyChangedOrder(order, recentCutoff)) return "recently_changed";
  return null;
}

export function packageNeedsReceivingAttention(pkg: any) {
  return ["expected", "receiving", "received", "staged"].includes(pkg?.status || "");
}

export function packageNeedsPrint(pkg: any) {
  return (pkg?.receiving_labels || []).some((label: any) => Number(label?.print_count || 0) <= 0);
}

export function packageNeedsPutaway(pkg: any) {
  return (
    pkg?.status === "putaway_pending" ||
    (pkg?.downstream_tasks || []).some((task: any) => task?.status !== "completed")
  );
}

export function packageLatestActivityTimestamp(pkg: any): number {
  const timestamps = [
    pkg?.confirmed_at,
    ...(pkg?.observed_codes || []).map((code: any) => code?.created_at),
    ...(pkg?.receiving_labels || []).flatMap((label: any) => [label?.received_at, label?.printed_at]),
    ...(pkg?.downstream_tasks || []).flatMap((task: any) => [task?.created_at, task?.started_at, task?.completed_at]),
  ]
    .map((value) => Date.parse(value || ""))
    .filter((value) => Number.isFinite(value));
  if (!timestamps.length) return 0;
  return Math.max(...timestamps);
}

export function packagePrimaryCode(pkg: any) {
  const primaryObserved = (pkg?.observed_codes || []).find((code: any) => code?.is_primary) || (pkg?.observed_codes || [])[0];
  return (
    primaryObserved?.code_value ||
    pkg?.external_tracking_number ||
    pkg?.external_carton_mark ||
    pkg?.external_customer_barcode ||
    null
  );
}

export function packageMatchesOperationFilter(pkg: any, filter: PackageOperationFilter, recentCutoff: number) {
  if (filter === "all" || filter === "needs_action") {
    return packageNeedsReceivingAttention(pkg) || packageNeedsPrint(pkg) || packageNeedsPutaway(pkg);
  }
  if (filter === "supervisor_review") {
    return (
      pkg?.package_origin === "dock_created" &&
      (packageNeedsReceivingAttention(pkg) || packageNeedsPrint(pkg) || packageNeedsPutaway(pkg))
    );
  }
  if (filter === "package_open") return packageNeedsReceivingAttention(pkg);
  if (filter === "putaway_pending") return packageNeedsPutaway(pkg);
  if (filter === "print_pending") return packageNeedsPrint(pkg);
  if (filter === "prebooked") return pkg?.package_origin === "prebooked";
  if (filter === "dock_created") return pkg?.package_origin === "dock_created";
  if (filter === "recently_changed") return packageLatestActivityTimestamp(pkg) >= recentCutoff;
  return true;
}

export function packageRecommendedOwner(pkg: any, t: Translate) {
  const lane = packageRecommendedOwnerLane(pkg);
  if (lane === "receiving") return t("receiving.packageDispatchOwnerReceiving", "Dock receiving");
  if (lane === "print") return t("receiving.packageDispatchOwnerPrint", "Label printing");
  if (lane === "putaway") return t("receiving.packageDispatchOwnerPutaway", "Putaway team");
  return t("receiving.packageDispatchOwnerReview", "Supervisor review");
}

export function packageRecommendedOwnerLane(pkg: any): ExceptionOwnerLane {
  if (packageNeedsReceivingAttention(pkg)) return "receiving";
  if (packageNeedsPrint(pkg)) return "print";
  if (packageNeedsPutaway(pkg)) return "putaway";
  return "review";
}

export function packagePrimaryBlocker(pkg: any, t: Translate) {
  if (packageNeedsReceivingAttention(pkg)) {
    return t("receiving.packageDispatchBlockerReceiving", "Still needs dock confirmation");
  }
  if (packageNeedsPrint(pkg)) {
    return t("receiving.packageDispatchBlockerPrint", "Internal label is still waiting to print");
  }
  if (packageNeedsPutaway(pkg)) {
    return t("receiving.packageDispatchBlockerPutaway", "Confirmed stock is still waiting on putaway");
  }
  if (pkg?.package_origin === "dock_created") {
    return t("receiving.packageDispatchBlockerReview", "Dock-opened package still needs lead review");
  }
  return t("receiving.packageDispatchBlockerClear", "No active blocker");
}
