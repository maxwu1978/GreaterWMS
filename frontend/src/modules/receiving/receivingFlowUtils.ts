import type {
  InboundPackageSummary,
  InboundDetailLineSummary,
  InboundDetailSummary,
} from "../../shared/api/receiving";

export type {
  InboundReceivableOrder,
  ScannedReceivingLabel,
  ObservedReceivingCode,
  ReceivingLabelSummary,
  ReceivingLabelTemplateSettings,
  InboundPackageSummary,
  InboundDetailLineSummary,
  InboundDetailSummary,
} from "../../shared/api/receiving";

export interface ReceivedLine {
  line_id: string;
  package_id?: string;
  package_number?: number | null;
  sku_id: string;
  expected: number;
  received: number;
  damaged: number;
  status: string;
  label_code?: string;
  discrepancy_qty?: number;
  discrepancy_status?: string;
  package_count?: number | null;
  pallet_count?: number | null;
  rent_free_days?: number | null;
  measured_weight_kg?: number | null;
  measured_length_cm?: number | null;
  measured_width_cm?: number | null;
  measured_height_cm?: number | null;
  receiving_note?: string | null;
}

export interface ScannerCodeSuggestion {
  id: string;
  label: string;
  value: string;
}

export interface CompleteReceivingSummary {
  id: string;
  status: string;
  created_tasks: number;
  putaway_units: number;
}

export interface ReceivingFlowProps {
  initialOrderId?: string | null;
  initialOrderStatus?: string | null;
  initialPackageFocus?: "needs_action" | "package_open" | "print_pending" | "prebooked" | "dock_created" | null;
  initialPackageId?: string | null;
  initialPrintPackageId?: string | null;
}

export type RecoveryAction =
  | "back_to_orders"
  | "clear_scan"
  | "continue_next"
  | "review_receipts"
  | "review_inbound"
  | "focus_staging"
  | "scan_again"
  | "add_package"
  | "open_next_package"
  | "refresh_order";

export type ReceivingRecoveryState = {
  code: string;
  title: string;
  body: string;
  actions: RecoveryAction[];
};

export type MobileReceiptFocus = "scan" | "dock" | "quantity" | "confirm" | "confirmed";

export function getInitialReceivingStep(
  initialOrderStatus: string | null,
): "select" | "prepare" | "scan" | "review" | "done" {
  if (initialOrderStatus === "receiving") return "scan";
  if (initialOrderStatus === "expected") return "prepare";
  return "select";
}

export function packageOriginLabel(
  origin: string | null | undefined,
  t: (key: string, fallback: string, vars?: Record<string, string | number>) => string,
) {
  if (origin === "dock_created") return t("receiving.packageOriginDockCreated", "Opened at dock");
  return t("receiving.packageOriginPrebooked", "Pre-booked");
}

export function sortInboundPackages(a: InboundPackageSummary, b: InboundPackageSummary) {
  const lineA = a.line_number ?? Number.MAX_SAFE_INTEGER;
  const lineB = b.line_number ?? Number.MAX_SAFE_INTEGER;
  if (lineA !== lineB) return lineA - lineB;
  const lineKeyCompare = (a.order_line_id || "").localeCompare(b.order_line_id || "");
  if (lineKeyCompare) return lineKeyCompare;
  const packageNumberCompare = Number(a.package_number || 0) - Number(b.package_number || 0);
  if (packageNumberCompare) return packageNumberCompare;
  return a.id.localeCompare(b.id);
}

export function normalizePackageType(type: string | null | undefined) {
  return (type || "").trim().toLowerCase();
}

export function packageTypeUsesContainedBoxes(type: string | null | undefined) {
  const normalized = normalizePackageType(type);
  return normalized === "pallet" || normalized === "mu";
}

export function packageTypeIsSingleHandlingUnit(type: string | null | undefined) {
  const normalized = normalizePackageType(type);
  return normalized === "carton" || normalized === "crate";
}

export function splitQuantityAcrossUnits(totalQty: number, unitCount: number) {
  const base = Math.floor(totalQty / unitCount);
  const remainder = totalQty % unitCount;
  return Array.from({ length: unitCount }, (_value, index) => base + (index < remainder ? 1 : 0));
}

export function packageTypeLabel(
  type: string | null | undefined,
  t: (key: string, fallback: string, vars?: Record<string, string | number>) => string,
) {
  switch (normalizePackageType(type)) {
    case "carton":
      return t("receivingFlow.packageTypeCarton", "Carton");
    case "crate":
      return t("receivingFlow.packageTypeCrate", "Crate");
    case "pallet":
      return t("receivingFlow.packageTypePallet", "Pallet");
    case "mu":
      return t("receivingFlow.packageTypeMu", "MU");
    default:
      return type || t("receivingFlow.packageTypePackage", "Package");
  }
}
