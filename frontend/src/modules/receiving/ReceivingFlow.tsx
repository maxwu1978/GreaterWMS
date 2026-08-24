/**
 * Interactive receiving workflow — step-by-step guided process.
 *
 * Steps:
 * 1. Select inbound order
 * 2. Scan labels or carton codes at dock (barcode → qty → confirm)
 * 3. Review discrepancies
 * 4. Complete receiving → triggers putaway tasks
 */

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { queryKeys } from "../../shared/api/queryKeys";
import { workbenchSummaryKeys } from "../../shared/api/workbenchSummaries";
import { isOfflineMutationQueuedError } from "../../shared/offline/outbox";
import { useReceivingFlowData } from "./useReceivingFlowData";
import { useReceivingMutations } from "./useReceivingMutations";
import {
  correctionReducer,
  initialCorrectionState,
  initialPackageEditorState,
  packageEditorReducer,
} from "./receivingFlowState";
import SelectStep from "./steps/SelectStep";
import PrepareStep from "./steps/PrepareStep";
import ReviewStep from "./steps/ReviewStep";
import DoneStep from "./steps/DoneStep";
import PackageEditorPanel from "./scan/PackageEditorPanel";
import ReceiptCorrectionPanel from "./scan/ReceiptCorrectionPanel";
import ConfirmedLabelsPanel from "./scan/ConfirmedLabelsPanel";
import ReceivedLinesPanel from "./scan/ReceivedLinesPanel";
import BarcodeScanner from "../../scanner/BarcodeScanner";
import MobileFlowGuide, { type MobileFlowStepItem } from "../../shared/components/MobileFlowGuide";
import { useI18n } from "../../shared/i18n";
import { ProcessSignal, ReceivingFlowProgress, RecoveryPanel } from "./receivingFlowComponents";
import {
  getInitialReceivingStep,
  normalizePackageType,
  packageOriginLabel,
  packageTypeIsSingleHandlingUnit,
  packageTypeLabel,
  packageTypeUsesContainedBoxes,
  sortInboundPackages,
  splitQuantityAcrossUnits,
  type CompleteReceivingSummary,
  type InboundDetailLineSummary,
  type InboundPackageSummary,
  type InboundReceivableOrder,
  type MobileReceiptFocus,
  type ReceivedLine,
  type ReceivingFlowProps,
  type ReceivingLabelSummary,
  type ReceivingRecoveryState,
  type RecoveryAction,
  type ScannedReceivingLabel,
  type ScannerCodeSuggestion,
} from "./receivingFlowUtils";

export default function ReceivingFlow({
  initialOrderId = null,
  initialOrderStatus = null,
  initialPackageFocus = null,
  initialPackageId = null,
  initialPrintPackageId = null,
}: ReceivingFlowProps) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const derivedInitialStep = getInitialReceivingStep(initialOrderStatus);
  const [step, setStep] = useState<"select" | "prepare" | "scan" | "review" | "done">(derivedInitialStep);
  const [orderId, setOrderId] = useState(initialOrderId || "");
  const [receivedLines, setReceivedLines] = useState<ReceivedLine[]>([]);
  const [currentQty, setCurrentQty] = useState("1");
  const [damagedQty, setDamagedQty] = useState("0");
  const [stagingLocation, setStagingLocation] = useState("");
  const [stagingLocationEntry, setStagingLocationEntry] = useState("");
  const [stagingLocationEntryError, setStagingLocationEntryError] = useState("");
  const [mobileReceiptFocus, setMobileReceiptFocus] = useState<MobileReceiptFocus>("scan");
  const [handlingUnitCount, setHandlingUnitCount] = useState("1");
  const [packageCount, setPackageCount] = useState("");
  const [palletCount, setPalletCount] = useState("");
  const [rentFreeDays, setRentFreeDays] = useState("");
  const [measuredWeightKg, setMeasuredWeightKg] = useState("");
  const [measuredLengthCm, setMeasuredLengthCm] = useState("");
  const [measuredWidthCm, setMeasuredWidthCm] = useState("");
  const [measuredHeightCm, setMeasuredHeightCm] = useState("");
  const [receivingNote, setReceivingNote] = useState("");
  const [scannedLabel, setScannedLabel] = useState<ScannedReceivingLabel | null>(null);
  const [activePackageFocus, setActivePackageFocus] = useState<ReceivingFlowProps["initialPackageFocus"]>(initialPackageFocus);
  const [packageFocusArmed, setPackageFocusArmed] = useState(Boolean(initialPackageFocus));
  const [activeDrillPackageId, setActiveDrillPackageId] = useState(initialPackageId || "");
  const [activePrintPackageId, setActivePrintPackageId] = useState(initialPrintPackageId || "");
  const [packageDrillArmed, setPackageDrillArmed] = useState(Boolean(initialPackageId || initialPrintPackageId));
  const [draftCodeValue, setDraftCodeValue] = useState("");
  const [draftCodeType, setDraftCodeType] = useState("other");
  const [editingCodeId, setEditingCodeId] = useState<string | null>(null);
  const [scanError, setScanError] = useState("");
  const [lastAttemptedScanCode, setLastAttemptedScanCode] = useState("");
  const [printError, setPrintError] = useState("");
  const [receiptError, setReceiptError] = useState("");
  const [receiptOfflineNotice, setReceiptOfflineNotice] = useState("");
  const [lastConfirmedLabelCode, setLastConfirmedLabelCode] = useState("");
  const [lastConfirmedExternalCount, setLastConfirmedExternalCount] = useState(0);
  const [lastPrintedLabelCount, setLastPrintedLabelCount] = useState(0);
  const [measurementDefaultsKey, setMeasurementDefaultsKey] = useState("");
  const confirmedLabelsRef = useRef<HTMLDivElement | null>(null);
  const scanSurfaceRef = useRef<HTMLDivElement | null>(null);
  const confirmReceiptRef = useRef<HTMLDivElement | null>(null);
  const stagingLocationEntryRef = useRef<HTMLDivElement | null>(null);
  const [packageEditor, dispatchPackageEditor] = useReducer(packageEditorReducer, initialPackageEditorState);
  const [handlingUnitSplitError, setHandlingUnitSplitError] = useState("");
  const [correction, dispatchCorrection] = useReducer(correctionReducer, initialCorrectionState);

  const {
    orders,
    selectedOrder,
    stagingLocations,
    receivingLabels,
    isLoadingReceivingLabels,
    packages,
    isLoadingPackages,
    orderDetail,
    labelTemplateSettings,
    observedCodes,
  } = useReceivingFlowData({ orderId, scannedLabel });
  const readyToOpenOrders = orders.filter((order) => order.status !== "receiving");
  const activeReceivingOrders = orders.filter((order) => order.status === "receiving");

  const stagingLocationCode = (location: any) =>
    String(
      location?.barcode ||
        [location?.aisle, location?.rack, location?.level, location?.position].filter(Boolean).join("-") ||
        location?.code ||
        location?.id ||
        "",
    );

  const stagingLocationLabel = (location: any) =>
    [stagingLocationCode(location), location?.location_type].filter(Boolean).join(" · ");
  const stagingScannerSuggestions = stagingLocations.slice(0, 6).map((location: any) => ({
    label: String(location?.location_type || t("receivingFlow.stagingLocation", "Staging Location")),
    value: stagingLocationCode(location),
  }));

  const selectedStagingLocation = stagingLocations.find(
    (location: any) => location.id === stagingLocation || location.barcode === stagingLocation,
  );

  const normalizeStagingLookup = (value: unknown) =>
    String(value || "")
      .trim()
      .toLowerCase();

  const stagingLocationLookupValues = (location: any) =>
    [
      location?.id,
      location?.barcode,
      location?.code,
      location?.aisle,
      location?.rack,
      location?.level,
      location?.position,
      [location?.aisle, location?.rack, location?.level, location?.position].filter(Boolean).join("-"),
    ]
      .map(normalizeStagingLookup)
      .filter(Boolean);

  const findStagingLocationByEntry = (entry: string) => {
    const normalizedEntry = normalizeStagingLookup(entry);
    if (!normalizedEntry) return null;

    const exact = stagingLocations.find((location: any) =>
      stagingLocationLookupValues(location).some((value) => value === normalizedEntry),
    );
    if (exact) return exact;

    const partialMatches = stagingLocations.filter((location: any) =>
      stagingLocationLookupValues(location).some((value) => value.includes(normalizedEntry)),
    );
    return partialMatches.length === 1 ? partialMatches[0] : null;
  };

  const resolvedStagingLocationId =
    selectedStagingLocation?.id || stagingLocations.find((location: any) => location.barcode === stagingLocation)?.id || "";

  useEffect(() => {
    if (!scannedLabel || stagingLocation || stagingLocations.length !== 1) {
      return;
    }
    setStagingLocation(stagingLocations[0].id);
    setStagingLocationEntry(stagingLocationCode(stagingLocations[0]));
  }, [scannedLabel, stagingLocation, stagingLocations]);

  const packageLookupCode = (pkg: InboundPackageSummary) =>
    pkg.external_tracking_number || pkg.external_carton_mark || pkg.external_customer_barcode || "";
  const apiErrorText = (error: any, fallback: string) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && typeof item.msg === "string") return item.msg;
          return "";
        })
        .filter(Boolean);
      if (messages.length > 0) return messages.join(" ");
    }
    if (detail && typeof detail === "object") {
      if (typeof detail.message === "string") return detail.message;
      if (typeof detail.msg === "string") return detail.msg;
      if (typeof detail.error === "string") return detail.error;
    }
    if (typeof error?.message === "string") return error.message;
    return fallback;
  };
  const apiErrorCode = (error: any) => {
    const detail = error?.response?.data?.detail;
    return detail && typeof detail === "object" && typeof detail.code === "string" ? detail.code : "";
  };
  const offlineQueuedText = () =>
    t("offline.mutationQueued", "Saved offline. It will sync automatically when the connection is back.");

  const lineSummaries = useMemo(() => orderDetail?.lines || [], [orderDetail]);
  const detailPackages = useMemo(
    () =>
      lineSummaries.flatMap((line) =>
        (line.packages || [])
          .filter((pkg): pkg is Partial<InboundPackageSummary> & { id: string } => Boolean(pkg?.id))
          .map((pkg) => ({
            id: pkg.id,
            order_line_id: pkg.order_line_id || line.line_id,
            line_number: pkg.line_number ?? line.line_number ?? null,
            sku_id: pkg.sku_id || line.sku_id || null,
            sku_code: pkg.sku_code || line.sku_code || null,
            sku_name: pkg.sku_name || line.sku_name || null,
            package_number: Number(pkg.package_number || 0),
            label_sequence: pkg.label_sequence ?? null,
            package_type: pkg.package_type || "carton",
            package_origin: pkg.package_origin ?? null,
            status: pkg.status || "expected",
            expected_qty: Number(pkg.expected_qty || 0),
            received_qty: Number(pkg.received_qty || 0),
            damaged_qty: Number(pkg.damaged_qty || 0),
            staging_location_id: pkg.staging_location_id ?? null,
            external_tracking_number: pkg.external_tracking_number ?? null,
            external_carton_mark: pkg.external_carton_mark ?? null,
            external_customer_barcode: pkg.external_customer_barcode ?? null,
            package_count: pkg.package_count ?? null,
            pallet_count: pkg.pallet_count ?? null,
            rent_free_days: pkg.rent_free_days ?? null,
            measured_weight_kg: pkg.measured_weight_kg ?? null,
            measured_length_cm: pkg.measured_length_cm ?? null,
            measured_width_cm: pkg.measured_width_cm ?? null,
            measured_height_cm: pkg.measured_height_cm ?? null,
            receiving_note: pkg.receiving_note ?? null,
            confirmed_at: pkg.confirmed_at ?? null,
          })),
      ),
    [lineSummaries],
  );
  const packageRecords = useMemo(() => {
    const merged = new Map<string, InboundPackageSummary>();
    detailPackages.forEach((pkg) => merged.set(pkg.id, pkg));
    packages.forEach((pkg) => {
      const existing = merged.get(pkg.id);
      merged.set(pkg.id, existing ? { ...existing, ...pkg } : pkg);
    });
    return Array.from(merged.values()).sort(sortInboundPackages);
  }, [detailPackages, packages]);
  const getLineSummary = (lineId: string) => lineSummaries.find((line) => line.line_id === lineId);
  const getRemainingExpectedForLine = (lineId: string, excludePackageId?: string) => {
    const line = getLineSummary(lineId);
    if (!line) return 1;
    const assignedQty = packageRecords
      .filter((pkg) => pkg.order_line_id === lineId && pkg.id !== excludePackageId)
      .reduce((sum, pkg) => sum + Number(pkg.expected_qty || 0), 0);
    return Math.max(1, Number(line.quantity_expected || 0) - assignedQty);
  };
  const formatMeasurementDefault = (value: number | null | undefined, decimals = 2) => {
    if (value == null || !Number.isFinite(Number(value))) return "";
    return Number(value)
      .toFixed(decimals)
      .replace(/\.?0+$/, "");
  };
  const measurementKeyForLabel = (label: ScannedReceivingLabel) => label.package_id || label.label_code;
  const resolveMeasurementDefaults = (
    label: ScannedReceivingLabel,
    pkg: InboundPackageSummary | null,
  ) => {
    const line = getLineSummary(label.line_id);
    const receiveQty = Math.max(0, Number(label.expected_qty || 0) - Number(label.received_qty || 0));
    const lineMeasurementsCanSeed = !line || Number(line.quantity_received || 0) === 0;

    const weight =
      pkg?.measured_weight_kg ??
      (lineMeasurementsCanSeed ? line?.measured_weight_kg : null) ??
      (line?.sku_weight_kg != null ? Number(line.sku_weight_kg) * receiveQty : null);
    const length =
      pkg?.measured_length_cm ??
      (lineMeasurementsCanSeed ? line?.measured_length_cm : null) ??
      line?.sku_length_cm;
    const width =
      pkg?.measured_width_cm ??
      (lineMeasurementsCanSeed ? line?.measured_width_cm : null) ??
      line?.sku_width_cm;
    const height =
      pkg?.measured_height_cm ??
      (lineMeasurementsCanSeed ? line?.measured_height_cm : null) ??
      line?.sku_height_cm;

    return {
      weight: formatMeasurementDefault(weight, 3),
      length: formatMeasurementDefault(length),
      width: formatMeasurementDefault(width),
      height: formatMeasurementDefault(height),
      note: pkg?.receiving_note || (lineMeasurementsCanSeed ? line?.receiving_note || "" : ""),
    };
  };
  const applyMeasurementDefaults = (
    label: ScannedReceivingLabel,
    pkg: InboundPackageSummary | null,
    options: { force?: boolean } = {},
  ) => {
    const defaults = resolveMeasurementDefaults(label, pkg);
    const hasDefaults = Boolean(defaults.weight || defaults.length || defaults.width || defaults.height || defaults.note);
    if (!hasDefaults) return false;

    if (options.force || !measuredWeightKg) setMeasuredWeightKg(defaults.weight);
    if (options.force || !measuredLengthCm) setMeasuredLengthCm(defaults.length);
    if (options.force || !measuredWidthCm) setMeasuredWidthCm(defaults.width);
    if (options.force || !measuredHeightCm) setMeasuredHeightCm(defaults.height);
    if (defaults.note && (options.force || !receivingNote)) setReceivingNote(defaults.note);
    return true;
  };

  const lineEditorLabel = (line: InboundDetailLineSummary) => {
    const parts = [line.sku_code || line.sku_id || "—"];
    if (line.line_number != null) {
      parts.push(t("receivingFlow.lineNumberShort", "Line") + ` ${line.line_number}`);
    }
    parts.push(
      t("receivingFlow.packageEditorLineCapacity", "{assigned}/{expected} assigned", {
        assigned: packageRecords
          .filter((pkg) => pkg.order_line_id === line.line_id)
          .reduce((sum, pkg) => sum + Number(pkg.expected_qty || 0), 0),
        expected: Number(line.quantity_expected || 0),
      }),
    );
    return parts.join(" · ");
  };

  const resetPackageEditor = () => {
    dispatchPackageEditor(initialPackageEditorState);
  };

  const resetReceiptCorrection = () => {
    dispatchCorrection(initialCorrectionState);
  };

  const openReceiptCorrection = (pkg: InboundPackageSummary) => {
    dispatchCorrection({
      packageId: pkg.id,
      receivedQty: String(pkg.received_qty ?? 0),
      damagedQty: String(pkg.damaged_qty ?? 0),
      stagingLocation: pkg.staging_location_id || "",
      packageCount: pkg.package_count != null ? String(pkg.package_count) : "",
      palletCount: pkg.pallet_count != null ? String(pkg.pallet_count) : "",
      rentFreeDays: pkg.rent_free_days != null ? String(pkg.rent_free_days) : "",
      weightKg: formatMeasurementDefault(pkg.measured_weight_kg, 3),
      lengthCm: formatMeasurementDefault(pkg.measured_length_cm),
      widthCm: formatMeasurementDefault(pkg.measured_width_cm),
      heightCm: formatMeasurementDefault(pkg.measured_height_cm),
      note: pkg.receiving_note || "",
      tracking: pkg.external_tracking_number || "",
      carton: pkg.external_carton_mark || "",
      customerCode: pkg.external_customer_barcode || "",
      error: "",
    });
  };

  const openCreatePackageEditor = (options?: {
    lineId?: string;
    splitFrom?: InboundPackageSummary | null;
  }) => {
    const splitFrom = options?.splitFrom || null;
    const lineId = options?.lineId || splitFrom?.order_line_id || lineSummaries[0]?.line_id || "";
    const suggestedQty = splitFrom
      ? getRemainingExpectedForLine(lineId, splitFrom.id)
      : getRemainingExpectedForLine(lineId);
    dispatchPackageEditor({
      mode: "create",
      packageId: "",
      lineId,
      expectedQty: String(suggestedQty),
      type: splitFrom?.package_type || "carton",
      tracking: "",
      carton: "",
      customerCode: "",
      error: "",
    });
  };

  const openEditPackageEditor = (pkg: InboundPackageSummary) => {
    dispatchPackageEditor({
      mode: "edit",
      packageId: pkg.id,
      lineId: pkg.order_line_id,
      expectedQty: String(pkg.expected_qty || ""),
      type: pkg.package_type || "carton",
      tracking: pkg.external_tracking_number || "",
      carton: pkg.external_carton_mark || "",
      customerCode: pkg.external_customer_barcode || "",
      error: "",
    });
  };

  const isPackageClosed = (pkg: InboundPackageSummary) =>
    ["received", "staged", "putaway_pending", "stored"].includes(pkg.status);
  const canCorrectPackageQuantity = (pkg: InboundPackageSummary) =>
    ["received", "staged"].includes(pkg.status);
  const canCorrectPackageMetadata = (pkg: InboundPackageSummary) =>
    ["received", "staged", "putaway_pending", "stored"].includes(pkg.status);

  const pendingPackages = packageRecords.filter((pkg) => !isPackageClosed(pkg));
  const confirmedPackages = packageRecords.filter((pkg) => isPackageClosed(pkg));
  const scannerCodeSuggestions = useMemo(() => {
    const suggestions: ScannerCodeSuggestion[] = [];
    const seen = new Set<string>();
    const addSuggestion = (id: string, label: string, value?: string | null) => {
      const trimmed = value?.trim();
      if (!trimmed) return;
      const normalized = trimmed.toLowerCase();
      if (seen.has(normalized)) return;
      seen.add(normalized);
      suggestions.push({ id, label, value: trimmed });
    };

    packageRecords
      .filter((pkg) => !["received", "staged", "putaway_pending", "stored"].includes(pkg.status))
      .forEach((pkg) => {
        addSuggestion(
          `tracking-${pkg.id}`,
          t("receivingFlow.scannerCodeTracking", "Tracking"),
          pkg.external_tracking_number,
        );
        addSuggestion(`carton-${pkg.id}`, t("receivingFlow.scannerCodeCarton", "Carton"), pkg.external_carton_mark);
        addSuggestion(
          `customer-${pkg.id}`,
          t("receivingFlow.scannerCodeCustomer", "Customer"),
          pkg.external_customer_barcode,
        );
      });

    receivingLabels.filter((label) => label.status !== "received").forEach((label) => {
      addSuggestion(`internal-${label.id}`, t("receivingFlow.scannerCodeInternal", "Internal"), label.label_code);
      addSuggestion(
        `label-tracking-${label.id}`,
        t("receivingFlow.scannerCodeTracking", "Tracking"),
        label.external_tracking_number,
      );
      addSuggestion(
        `label-carton-${label.id}`,
        t("receivingFlow.scannerCodeCarton", "Carton"),
        label.external_carton_mark,
      );
      addSuggestion(
        `label-customer-${label.id}`,
        t("receivingFlow.scannerCodeCustomer", "Customer"),
        label.external_customer_barcode,
      );
    });

    return suggestions.slice(0, 6);
  }, [packageRecords, receivingLabels, t]);
  const scannerPlaceholder = scannerCodeSuggestions[0]
    ? t("receivingFlow.scannerPlaceholderWithCode", "Scan or type {code}", {
        code: scannerCodeSuggestions[0].value,
      })
    : t("receivingFlow.scannerPlaceholder", "Scan barcode or type manually...");

  const packageStatusLabel = (status: string) => {
    switch (status) {
      case "expected":
        return t("receivingFlow.packageStatusExpected", "Ready");
      case "receiving":
        return t("receivingFlow.packageStatusReceiving", "Receiving");
      case "received":
        return t("receivingFlow.packageStatusReceived", "Received");
      case "staged":
        return t("receivingFlow.packageStatusStaged", "Staged");
      case "putaway_pending":
        return t("receivingFlow.packageStatusPutawayPending", "Putaway pending");
      case "stored":
        return t("receivingFlow.packageStatusStored", "Stored");
      default:
        return status;
    }
  };

  const packageStatusTone = (status: string) => {
    switch (status) {
      case "received":
      case "staged":
      case "stored":
        return "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]";
      case "putaway_pending":
        return "border-[#d7d0c4] bg-[#fff6e6] text-[#91621a]";
      case "receiving":
        return "border-[#c9ddf4] bg-[#eff5ff] text-[#24507a]";
      default:
        return "border-[#d7d0c4] bg-white text-[#51606b]";
    }
  };

  const pendingPackageCount = pendingPackages.length;
  const confirmedPackageCount = confirmedPackages.length;
  const putawayPendingPackageCount = packageRecords.filter((pkg) => pkg.status === "putaway_pending").length;
  const mobileQueuePackages = [
    ...pendingPackages,
    ...confirmedPackages.filter((pkg) => pkg.status === "putaway_pending"),
    ...confirmedPackages.filter((pkg) => pkg.status !== "putaway_pending"),
  ];
  const printableLabelCount = receivingLabels.filter((label) => label.status === "received").length;
  const printedLabelCount = receivingLabels.filter((label) => (label.print_count || 0) > 0).length;
  const unprintedLabelCount = Math.max(0, printableLabelCount - printedLabelCount);
  const lastConfirmedLabelNeedsPrint = receivingLabels.some(
    (label) =>
      label.label_code === lastConfirmedLabelCode &&
      label.status === "received" &&
      (label.print_count || 0) <= 0,
  );
  const pendingExternalCodeCount = observedCodes.filter((code) => !code.is_confirmed).length;
  const remainingGoodUnits = receivingLabels.reduce(
    (sum, label) => sum + Math.max(0, label.expected_qty - label.received_qty),
    0,
  );
  const lastReceipt = receivedLines[receivedLines.length - 1] || null;
  const normalizeReceiptQuantityInput = (value: string) => {
    if (!value.trim()) return "";
    return value.replace(/^0+(?=\d)/, "");
  };
  const parseReceiptQuantity = (value: string) => {
    if (!value.trim()) return 0;
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
  };

  const applyActivePackage = (payload: ScannedReceivingLabel) => {
    const activePackage = payload.package_id
      ? packageRecords.find((pkg) => pkg.id === payload.package_id) || null
      : null;
    const activeType = activePackage?.package_type || payload.label_type;
    const usesContainedBoxes = packageTypeUsesContainedBoxes(activeType);
    setScannedLabel(payload);
    setScanError("");
    setPrintError("");
    setReceiptError("");
    setReceiptOfflineNotice("");
    setCurrentQty(String(Math.max(0, payload.expected_qty - payload.received_qty)));
    setDamagedQty("0");
    setHandlingUnitCount("1");
    setHandlingUnitSplitError("");
    setPackageCount(
      usesContainedBoxes && activePackage?.package_count != null ? String(activePackage.package_count) : "",
    );
    setPalletCount(
      usesContainedBoxes
        ? activePackage?.pallet_count != null
          ? String(activePackage.pallet_count)
          : normalizePackageType(activeType) === "pallet"
            ? "1"
            : ""
        : "",
    );
    setRentFreeDays(activePackage?.rent_free_days != null ? String(activePackage.rent_free_days) : "");
    const measurementDefaults = resolveMeasurementDefaults(payload, activePackage);
    setMeasuredWeightKg(measurementDefaults.weight);
    setMeasuredLengthCm(measurementDefaults.length);
    setMeasuredWidthCm(measurementDefaults.width);
    setMeasuredHeightCm(measurementDefaults.height);
    setReceivingNote(measurementDefaults.note);
    setMeasurementDefaultsKey(
      measurementDefaults.weight ||
        measurementDefaults.length ||
        measurementDefaults.width ||
        measurementDefaults.height ||
        measurementDefaults.note
        ? measurementKeyForLabel(payload)
        : "",
    );
    setDraftCodeValue("");
    setDraftCodeType("other");
    setEditingCodeId(null);
    dispatchPackageEditor({ error: "" });
    setMobileReceiptFocus("dock");
    queryClient.invalidateQueries({
      queryKey: payload.package_id
        ? queryKeys.receiving.observedCodes(orderId, payload.package_id)
        : queryKeys.receiving.observedCodes(orderId, payload.label_code),
    });
  };

  const activeReceivingPackage = scannedLabel?.package_id
    ? packageRecords.find((pkg) => pkg.id === scannedLabel.package_id) || null
    : null;
  const activePackageType = activeReceivingPackage?.package_type || scannedLabel?.label_type || null;
  const shouldCaptureHandlingUnitCount = Boolean(scannedLabel) && packageTypeIsSingleHandlingUnit(activePackageType);

  const {
    startMutation,
    receiveMutation,
    scanLabelMutation,
    openPackageMutation,
    addObservedCodeMutation,
    updateObservedCodeMutation,
    deleteObservedCodeMutation,
    createPackageMutation,
    updatePackageMutation,
    splitHandlingUnitsMutation,
    correctPackageMutation,
    deletePackageMutation,
    completeMutation,
    markPrintedMutation,
  } = useReceivingMutations({
    t,
    orderId,
    scannedLabel,
    packageRecords,
    receivingLabels,
    observedCodes,
    activeReceivingPackage,
    shouldCaptureHandlingUnitCount,
    handlingUnitCount,
    printableLabelCount,
    draftCodeValue,
    draftCodeType,
    isPackageClosed,
    packageLookupCode,
    applyActivePackage,
    apiErrorText,
    offlineQueuedText,
    resetPackageEditor,
    resetReceiptCorrection,
    setStep,
    setReceivedLines,
    setScannedLabel,
    setMobileReceiptFocus,
    setScanError,
    setLastAttemptedScanCode,
    setPrintError,
    setReceiptError,
    setReceiptOfflineNotice,
    setLastConfirmedLabelCode,
    setLastConfirmedExternalCount,
    setLastPrintedLabelCount,
    setCurrentQty,
    setDamagedQty,
    setHandlingUnitCount,
    setHandlingUnitSplitError,
    setPackageCount,
    setPalletCount,
    setRentFreeDays,
    setMeasuredWeightKg,
    setMeasuredLengthCm,
    setMeasuredWidthCm,
    setMeasuredHeightCm,
    setReceivingNote,
    setMeasurementDefaultsKey,
    setDraftCodeValue,
    setDraftCodeType,
    setEditingCodeId,
    setPackageEditorError: (value: string) => dispatchPackageEditor({ error: value }),
    setCorrectionError: (value: string) => dispatchCorrection({ error: value }),
  });
  const startPendingOrderId = startMutation.isPending ? ((startMutation.variables as string | undefined) ?? null) : null;

  const completeSummary = completeMutation.data?.data as CompleteReceivingSummary | undefined;

  const refreshReceivingWork = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.receivable() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.labels(orderId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) }),
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.receiving }),
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.putaway }),
    ]);
  };

  const resetReceiptSession = () => {
    setReceivedLines([]);
    setCurrentQty("1");
    setDamagedQty("0");
    setHandlingUnitCount("1");
    setHandlingUnitSplitError("");
    setPackageCount("");
    setPalletCount("");
    setRentFreeDays("");
    setMeasuredWeightKg("");
    setMeasuredLengthCm("");
    setMeasuredWidthCm("");
    setMeasuredHeightCm("");
    setReceivingNote("");
    setMeasurementDefaultsKey("");
    setDraftCodeValue("");
    setDraftCodeType("other");
    setEditingCodeId(null);
    setScannedLabel(null);
    setMobileReceiptFocus("scan");
    setScanError("");
    setLastAttemptedScanCode("");
    setPrintError("");
    setReceiptError("");
    setLastConfirmedLabelCode("");
    setLastConfirmedExternalCount(0);
    setLastPrintedLabelCount(0);
    setActivePackageFocus(null);
    setPackageFocusArmed(false);
    setActiveDrillPackageId("");
    setActivePrintPackageId("");
    setPackageDrillArmed(false);
    setStagingLocationEntry("");
    setStagingLocationEntryError("");
    resetPackageEditor();
    resetReceiptCorrection();
    startMutation.reset();
    receiveMutation.reset();
    scanLabelMutation.reset();
    completeMutation.reset();
    markPrintedMutation.reset();
  };

  const returnToOrderSelection = () => {
    setStep("select");
    setOrderId("");
    setStagingLocation("");
    resetReceiptSession();
  };

  const handleSelectOrder = (order: InboundReceivableOrder) => {
    setOrderId(order.id);
    setStagingLocation("");
    resetReceiptSession();
    if (order.status === "receiving") {
      setStep("scan");
      return;
    }
    startMutation.mutate(order.id);
  };

  const handleScan = (barcode: string, source: "scan" | "photo" | "manual" = "scan") => {
    setLastAttemptedScanCode(barcode);
    setScanError("");
    scanLabelMutation.mutate({ labelCode: barcode, source });
  };

  const applyStagingLocationValue = (value: string) => {
    const entry = value.trim();
    if (!entry) {
      setStagingLocationEntryError(
        t("receivingFlow.stagingManualRequired", "Type or scan a dock/staging code first."),
      );
      return false;
    }
    setStagingLocationEntry(entry);

    const partialMatches = stagingLocations.filter((location: any) =>
      stagingLocationLookupValues(location).some((value) => value.includes(normalizeStagingLookup(entry))),
    );
    const location = findStagingLocationByEntry(entry);

    if (!location) {
      setStagingLocationEntryError(
        partialMatches.length > 1
          ? t("receivingFlow.stagingManualAmbiguous", "{count} matching locations. Use the full barcode.", {
              count: partialMatches.length,
            })
          : t("receivingFlow.stagingManualNotFound", "No matching dock/staging location. Check the code or use the list."),
      );
      return false;
    }

    setStagingLocation(location.id);
    setStagingLocationEntry(stagingLocationCode(location));
    setStagingLocationEntryError("");
    return true;
  };

  const applyStagingLocationEntry = () => applyStagingLocationValue(stagingLocationEntry);

  const handleStagingLocationScan = (barcode: string) => {
    applyStagingLocationValue(barcode);
  };

  const chooseStagingLocation = (locationId: string) => {
    const location = stagingLocations.find((item: any) => item.id === locationId);
    setStagingLocation(locationId);
    setStagingLocationEntry(location ? stagingLocationCode(location) : "");
    setStagingLocationEntryError("");
  };

  const handleSubmitPackageEditor = () => {
    if (!packageEditor.lineId) {
      dispatchPackageEditor({ error: 
        t("receivingFlow.packageLineRequired", "Choose which inbound line this package belongs to."),
       });
      return;
    }
    const expectedQty = Number(packageEditor.expectedQty);
    if (!Number.isFinite(expectedQty) || expectedQty <= 0) {
      dispatchPackageEditor({ error: 
        t("receivingFlow.packageExpectedRequired", "Package expected quantity must be greater than zero."),
       });
      return;
    }

    const payload = {
      line_id: packageEditor.lineId,
      expected_qty: expectedQty,
      package_type: packageEditor.type,
      external_tracking_number: packageEditor.tracking.trim() || undefined,
      external_carton_mark: packageEditor.carton.trim() || undefined,
      external_customer_barcode: packageEditor.customerCode.trim() || undefined,
    };

    if (packageEditor.mode === "edit" && packageEditor.packageId) {
      updatePackageMutation.mutate({
        package_id: packageEditor.packageId,
        ...payload,
      });
      return;
    }

    createPackageMutation.mutate(payload);
  };

  const handleSubmitReceiptCorrection = () => {
    const packageToCorrect = packageRecords.find((pkg) => pkg.id === correction.packageId);
    if (!packageToCorrect) return;
    const parseRequiredNumber = (value: string) => {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : NaN;
    };
    const parseOptionalNumber = (value: string) => {
      if (!value.trim()) return undefined;
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : undefined;
    };
    const receivedQty = parseRequiredNumber(correction.receivedQty);
    const damagedQty = parseRequiredNumber(correction.damagedQty);
    if (!Number.isFinite(receivedQty) || receivedQty < 0 || !Number.isFinite(damagedQty) || damagedQty < 0) {
      dispatchCorrection({ error: 
        t("receivingFlow.correctionQuantityInvalid", "Received and damaged quantities must be zero or greater."),
       });
      return;
    }
    if (damagedQty > receivedQty) {
      dispatchCorrection({ error: 
        t("receivingFlow.correctionDamagedInvalid", "Damaged quantity cannot exceed received quantity."),
       });
      return;
    }
    if (canCorrectPackageQuantity(packageToCorrect) && receivedQty - damagedQty > 0 && !correction.stagingLocation) {
      dispatchCorrection({ error: 
        t("receivingFlow.correctionStagingRequired", "Choose a staging location for corrected good units."),
       });
      return;
    }

    correctPackageMutation.mutate({
      package_id: packageToCorrect.id,
      quantity_received: receivedQty,
      quantity_damaged: damagedQty,
      staging_location_id: correction.stagingLocation || undefined,
      package_count: parseOptionalNumber(correction.packageCount),
      pallet_count: parseOptionalNumber(correction.palletCount),
      rent_free_days: parseOptionalNumber(correction.rentFreeDays),
      measured_weight_kg: parseOptionalNumber(correction.weightKg),
      measured_length_cm: parseOptionalNumber(correction.lengthCm),
      measured_width_cm: parseOptionalNumber(correction.widthCm),
      measured_height_cm: parseOptionalNumber(correction.heightCm),
      receiving_note: correction.note.trim() || undefined,
      external_tracking_number: correction.tracking.trim() || undefined,
      external_carton_mark: correction.carton.trim() || undefined,
      external_customer_barcode: correction.customerCode.trim() || undefined,
    });
  };

  useEffect(() => {
    setOrderId(initialOrderId || "");
    setStagingLocation("");
    resetReceiptSession();
    setActivePackageFocus(initialPackageFocus);
    setPackageFocusArmed(Boolean(initialPackageFocus));
    setActiveDrillPackageId(initialPackageId || "");
    setActivePrintPackageId(initialPrintPackageId || "");
    setPackageDrillArmed(Boolean(initialPackageId || initialPrintPackageId));
    setStep(getInitialReceivingStep(initialOrderStatus));
  }, [initialOrderId, initialOrderStatus, initialPackageFocus, initialPackageId, initialPrintPackageId]);

  useEffect(() => {
    if (!packageDrillArmed || !orderId || step !== "scan") return;
    if (packageEditor.mode || isLoadingPackages || isLoadingReceivingLabels) return;
    if (scanLabelMutation.isPending || openPackageMutation.isPending || receiveMutation.isPending) return;

    if (activePrintPackageId) {
      const matchingPrintedLabel = receivingLabels.find(
        (label) => label.package_id === activePrintPackageId && label.status === "received",
      );
      if (matchingPrintedLabel) {
        confirmedLabelsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      setPackageDrillArmed(false);
      return;
    }

    if (!activeDrillPackageId) {
      setPackageDrillArmed(false);
      return;
    }

    const matchingPackage = packageRecords.find((pkg) => pkg.id === activeDrillPackageId);
    if (!matchingPackage) {
      setPackageDrillArmed(false);
      return;
    }
    if (scannedLabel?.package_id === matchingPackage.id) {
      setPackageDrillArmed(false);
      return;
    }
    if (!isPackageClosed(matchingPackage)) {
      setPackageDrillArmed(false);
      const lookupCode = packageLookupCode(matchingPackage);
      if (lookupCode) {
        scanLabelMutation.mutate({ labelCode: lookupCode, source: "manual" });
        return;
      }
      openPackageMutation.mutate(matchingPackage.id);
      return;
    }

    const matchingPrintedLabel = receivingLabels.find(
      (label) => label.package_id === matchingPackage.id && label.status === "received",
    );
    if (matchingPrintedLabel) {
      confirmedLabelsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    setPackageDrillArmed(false);
  }, [
    activeDrillPackageId,
    activePrintPackageId,
    isLoadingPackages,
    isLoadingReceivingLabels,
    openPackageMutation,
    orderId,
    packageDrillArmed,
    packageEditor.mode,
    packageRecords,
    receiveMutation,
    receivingLabels,
    scanLabelMutation,
    scannedLabel,
    step,
  ]);

  useEffect(() => {
    if (!activePackageFocus || !packageFocusArmed || !orderId || step !== "scan" || scannedLabel) return;
    if (packageEditor.mode || isLoadingPackages || isLoadingReceivingLabels) return;
    if (scanLabelMutation.isPending || openPackageMutation.isPending || receiveMutation.isPending) return;

    if (activePackageFocus === "print_pending") {
      if (printableLabelCount === 0) return;
      confirmedLabelsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      setPackageFocusArmed(false);
      return;
    }

    const matchingPendingPackage =
      activePackageFocus === "prebooked"
        ? pendingPackages.find((pkg) => pkg.package_origin === "prebooked")
        : activePackageFocus === "dock_created"
        ? pendingPackages.find((pkg) => pkg.package_origin === "dock_created")
        : pendingPackages[0];

    if (matchingPendingPackage) {
      setPackageFocusArmed(false);
      const lookupCode = packageLookupCode(matchingPendingPackage);
      if (lookupCode) {
        scanLabelMutation.mutate({ labelCode: lookupCode, source: "manual" });
        return;
      }
      openPackageMutation.mutate(matchingPendingPackage.id);
      return;
    }

    if (printableLabelCount > 0) {
      confirmedLabelsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    setPackageFocusArmed(false);
  }, [
    activePackageFocus,
    isLoadingPackages,
    isLoadingReceivingLabels,
    openPackageMutation,
    orderId,
    packageEditor.mode,
    packageFocusArmed,
    pendingPackages,
    printableLabelCount,
    receiveMutation,
    scanLabelMutation,
    scannedLabel,
    step,
  ]);

  const clearPackageFocus = () => {
    setActivePackageFocus(null);
    setPackageFocusArmed(false);
  };

  const scrollToScanSurface = () => {
    scanSurfaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const scrollToConfirmReceipt = () => {
    confirmReceiptRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const mobileRecentReceiptTitle = () => {
    if (!lastConfirmedLabelCode) return "";
    if (lastReceipt?.package_number != null) {
      return t("receivingFlow.mobileRecentReceiptTitlePackage", "Package {number} confirmed", {
        number: lastReceipt.package_number,
      });
    }
    return t("receivingFlow.mobileRecentReceiptTitleGeneric", "Package confirmed");
  };

  const mobileRecentReceiptActionLabel = () => {
    if (!lastConfirmedLabelCode) return "";
    if (lastConfirmedLabelNeedsPrint) {
      return t("receivingFlow.mobileRecentReceiptActionPrint", "Print this internal label");
    }
    if (scannedLabel) {
      return t("receivingFlow.mobileRecentReceiptActionContinue", "Continue with current package");
    }
    if (pendingPackageCount > 0) {
      return t("receivingFlow.mobileRecentReceiptActionScanNext", "Scan the next package");
    }
    if (putawayPendingPackageCount > 0) {
      return t("receivingFlow.mobileRecentReceiptActionPutaway", "Open putaway next");
    }
    return t("receivingFlow.mobileRecentReceiptActionReview", "Review inbound summary");
  };
  const mobileRecentReceiptNextStep = () => {
    if (!lastConfirmedLabelCode) return "";
    if (lastConfirmedLabelNeedsPrint) {
      return t(
        "receivingFlow.mobileRecentReceiptNextPrint",
        "Next: print the internal label before this package leaves the dock.",
      );
    }
    if (scannedLabel) {
      return scannedLabel.package_number != null
        ? t("receivingFlow.mobileRecentReceiptNextCurrentPackage", "Next: continue Package {number}.", {
            number: scannedLabel.package_number,
          })
        : t("receivingFlow.mobileRecentReceiptNextCurrent", "Next: continue the package already opened.");
    }
    if (pendingPackageCount > 0) {
      return t("receivingFlow.mobileRecentReceiptNextScan", "Next: scan the next package.");
    }
    if (putawayPendingPackageCount > 0) {
      return t("receivingFlow.mobileRecentReceiptNextPutaway", "All packages received. Next: continue to putaway.");
    }
    return t("receivingFlow.mobileRecentReceiptNextReview", "All packages received. Next: review this inbound.");
  };

  const handleMobileRecentReceiptAction = () => {
    if (!lastConfirmedLabelCode) return;
    if (lastConfirmedLabelNeedsPrint) {
      void handlePrintLabels(lastConfirmedLabelCode);
      return;
    }
    if (scannedLabel) {
      scrollToConfirmReceipt();
      return;
    }
    if (pendingPackageCount > 0) {
      setLastConfirmedLabelCode("");
      setLastConfirmedExternalCount(0);
      setMobileReceiptFocus("scan");
      scrollToScanSurface();
      return;
    }
    if (putawayPendingPackageCount > 0) {
      navigate(
        `/putaway?orderId=${encodeURIComponent(orderId)}&orderNumber=${encodeURIComponent(
          selectedOrder?.order_number || "",
        )}&referenceNumber=${encodeURIComponent(selectedOrder?.reference_number || "")}`,
      );
      return;
    }
    setStep("review");
  };

  const normalizedActivePackageType = normalizePackageType(activePackageType);
  const activePackageTypeName = packageTypeLabel(activePackageType, t);
  const activePackageTitle =
    scannedLabel?.package_number != null
      ? t("receivingFlow.packageCardTitle", "Package {number}", {
          number: scannedLabel.package_number,
        })
      : t("receivingFlow.currentPackageFallback", "Current package");
  const activePackageSkuLine = [
    activeReceivingPackage?.sku_code || activeReceivingPackage?.sku_id || scannedLabel?.sku_id || null,
    activeReceivingPackage?.line_number != null
      ? `${t("receivingFlow.lineNumberShort", "Line")} ${activeReceivingPackage.line_number}`
      : null,
  ].filter(Boolean);
  const activePackageExpectedQty = activeReceivingPackage?.expected_qty ?? scannedLabel?.expected_qty ?? "—";
  const shouldCaptureContainedBoxes = packageTypeUsesContainedBoxes(activePackageType);
  const shouldCapturePalletCount = Boolean(scannedLabel) && shouldCaptureContainedBoxes;
  const handlingUnitCountNumber = Number(handlingUnitCount);
  const activePackageExpectedQtyNumber = Number(activeReceivingPackage?.expected_qty ?? scannedLabel?.expected_qty ?? 0);
  const hasMultipleHandlingUnits =
    shouldCaptureHandlingUnitCount &&
    Number.isInteger(handlingUnitCountNumber) &&
    handlingUnitCountNumber > 1;
  const handlingUnitSplitQuantities =
    hasMultipleHandlingUnits &&
    activePackageExpectedQtyNumber >= handlingUnitCountNumber &&
    activePackageExpectedQtyNumber > 0
      ? splitQuantityAcrossUnits(activePackageExpectedQtyNumber, handlingUnitCountNumber)
      : [];
  const canSplitHandlingUnits =
    Boolean(activeReceivingPackage?.id) &&
    hasMultipleHandlingUnits &&
    handlingUnitSplitQuantities.length === handlingUnitCountNumber;
  const containedPackageCountLabel =
    normalizedActivePackageType === "mu"
      ? t("receivingFlow.containedUnitsInMu", "Units inside this MU")
      : normalizedActivePackageType === "pallet"
        ? t("receivingFlow.cartonsOnPallet", "Cartons on this pallet")
        : t("receivingFlow.packageCount", "Contained boxes");
  const containedPackageCountHelp =
    normalizedActivePackageType === "mu"
      ? t("receivingFlow.containedUnitsInMuHelp", "Count the cartons or sellable units grouped inside this master unit.")
      : t("receivingFlow.cartonsOnPalletHelp", "Count the cartons physically stacked on this pallet package.");
  const palletCountLabel =
    normalizedActivePackageType === "pallet"
      ? t("receivingFlow.palletsReceived", "Pallets received")
      : t("receivingFlow.palletCount", "Pallets Quantity");

  useEffect(() => {
    if (!scannedLabel) return;
    const defaultsKey = measurementKeyForLabel(scannedLabel);
    if (measurementDefaultsKey === defaultsKey) return;
    if (applyMeasurementDefaults(scannedLabel, activeReceivingPackage)) {
      setMeasurementDefaultsKey(defaultsKey);
    }
  }, [
    activeReceivingPackage,
    lineSummaries,
    measurementDefaultsKey,
    scannedLabel,
  ]);

  const reviewReceivingBlockedReason = (() => {
    if (receiveMutation.isPending) {
      return t("receivingFlow.reviewBlockedSaving", "Finish saving the current receipt first.");
    }
    if (scannedLabel) {
      return t("receivingFlow.reviewBlockedCurrentPackage", "Confirm the current package before review.");
    }
    if (pendingPackageCount > 0) {
      return t("receivingFlow.reviewBlockedPendingPackages", "{count} packages still need receiving.", {
        count: pendingPackageCount,
      });
    }
    return "";
  })();
  const canReviewReceiving = !reviewReceivingBlockedReason;
  const currentQtyNumber = parseReceiptQuantity(currentQty);
  const damagedQtyNumber = parseReceiptQuantity(damagedQty);
  const confirmReceiptBlockedByStaging = Boolean(scannedLabel) && currentQtyNumber > 0 && !resolvedStagingLocationId;
  const confirmReceiptBlockedByHandlingUnits = Boolean(scannedLabel) && hasMultipleHandlingUnits;
  const canConfirmReceipt =
    Boolean(scannedLabel) &&
    !confirmReceiptBlockedByStaging &&
    !confirmReceiptBlockedByHandlingUnits &&
    !receiveMutation.isPending;
  const receiptPrimaryActionLabel = !scannedLabel
    ? t("receivingFlow.mobileReceiptPrimaryActionScan", "Scan a package first")
    : confirmReceiptBlockedByStaging
    ? t("receivingFlow.mobileReceiptPrimaryActionStaging", "Choose staging to continue")
    : confirmReceiptBlockedByHandlingUnits
    ? t("receivingFlow.mobileReceiptPrimaryActionSplitUnits", "Split handling units first")
    : receiveMutation.isPending
    ? t("receivingFlow.confirmingReceipt", "Confirming receipt...")
    : scannedLabel.package_number != null
      ? t("receivingFlow.confirmReceiptPackageAction", "Confirm Package {number} receipt", {
          number: scannedLabel.package_number,
        })
      : t("receivingFlow.confirmReceiptAction", "Confirm this package receipt");
  const receiptQuantityEntered = Boolean(scannedLabel) && (currentQtyNumber > 0 || damagedQtyNumber > 0);
  const receiptQuantityValidationMessage =
    Boolean(scannedLabel) && damagedQtyNumber > currentQtyNumber
      ? t("receivingFlow.mobileDamagedQtyInvalid", "Damaged quantity cannot exceed the received quantity.")
      : "";
  const showMobileConfirmedState =
    !scannedLabel &&
    Boolean(lastConfirmedLabelCode);
  const mobileEffectiveReceiptFocus: MobileReceiptFocus = showMobileConfirmedState
    ? "confirmed"
    : !scannedLabel
      ? "scan"
      : confirmReceiptBlockedByStaging
        ? "dock"
        : mobileReceiptFocus === "dock"
          ? "dock"
          : mobileReceiptFocus === "confirm"
            ? "confirm"
            : "quantity";
  const mobileReceivingStepItems: MobileFlowStepItem[] = [
    {
      key: "scan",
      number: "1",
      label: t("receivingFlow.mobileStepScan", "Scan"),
      status: scannedLabel || mobileEffectiveReceiptFocus === "confirmed" ? "done" : "active",
    },
    {
      key: "dock",
      number: "2",
      label: t("receivingFlow.mobileStepDock", "Dock"),
      status:
        mobileEffectiveReceiptFocus === "confirmed"
          ? "done"
          : !scannedLabel
            ? "pending"
            : mobileEffectiveReceiptFocus === "dock"
              ? "active"
              : "done",
    },
    {
      key: "quantity",
      number: "3",
      label: t("receivingFlow.mobileStepQuantity", "Qty"),
      status:
        mobileEffectiveReceiptFocus === "confirmed"
          ? "done"
          : !scannedLabel || confirmReceiptBlockedByStaging || mobileEffectiveReceiptFocus === "dock"
            ? "pending"
            : mobileEffectiveReceiptFocus === "confirm"
              ? "done"
              : "active",
    },
    {
      key: "confirm",
      number: "4",
      label: t("receivingFlow.mobileStepConfirm", "Confirm"),
      status: mobileEffectiveReceiptFocus === "confirm" || mobileEffectiveReceiptFocus === "confirmed" ? "active" : "pending",
    },
  ];
  const mobileReceivingStepTitle = mobileEffectiveReceiptFocus === "scan"
    ? t("receivingFlow.mobileStepTitleScan", "Step 1 · Scan or type the package code")
    : mobileEffectiveReceiptFocus === "dock"
      ? t("receivingFlow.mobileStepTitleDock", "Step 2 · Choose dock/staging")
      : mobileEffectiveReceiptFocus === "confirmed"
        ? t("receivingFlow.mobileStepTitleConfirmed", "Step 4 · Package confirmed")
        : mobileEffectiveReceiptFocus === "confirm"
          ? t("receivingFlow.mobileStepTitleConfirm", "Step 4 · Confirm this receipt")
          : confirmReceiptBlockedByHandlingUnits
            ? t("receivingFlow.mobileStepTitleSplit", "Step 3 · Split the physical packages first")
            : t("receivingFlow.mobileStepTitleQuantity", "Step 3 · Check received quantity");
  const mobileReceivingStepHint = mobileEffectiveReceiptFocus === "scan"
    ? t("receivingFlow.mobileStepHintScan", "Use the suggested barcode, scan the label, or type the tracking/carton code.")
    : mobileEffectiveReceiptFocus === "dock"
      ? t("receivingFlow.mobileStepHintDock", "Pick where the package is sitting now. This keeps putaway tasks tied to a real dock or staging spot.")
      : mobileEffectiveReceiptFocus === "confirmed"
        ? lastConfirmedLabelNeedsPrint
          ? t("receivingFlow.mobileStepHintConfirmedPrint", "Receipt is saved. Print the internal label before moving this package away from the dock.")
          : pendingPackageCount > 0
            ? t("receivingFlow.mobileStepHintConfirmedNext", "Receipt is saved. Continue with the next package when you are ready.")
            : putawayPendingPackageCount > 0
              ? t("receivingFlow.mobileStepHintConfirmedPutaway", "Receipt is saved. All packages are ready for putaway.")
              : t("receivingFlow.mobileStepHintConfirmedReview", "Receipt is saved. Review and complete this inbound order.")
        : mobileEffectiveReceiptFocus === "confirm"
          ? t("receivingFlow.mobileStepHintConfirm", "Quantity and dock are ready. Confirm, then move to the next package.")
          : confirmReceiptBlockedByHandlingUnits
            ? t("receivingFlow.mobileStepHintSplit", "This record represents multiple physical units. Split it before receiving so each unit can be tracked.")
            : t("receivingFlow.mobileStepHintQuantity", "Check the received and damaged quantities before confirming.");

  const handleReceiveLine = () => {
    if (!scannedLabel) return;
    const parseOptionalNumber = (value: string) => {
      if (!value.trim()) return undefined;
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : undefined;
    };

    receiveMutation.mutate({
      label_code: scannedLabel.label_code,
      quantity_received: currentQtyNumber,
      quantity_damaged: damagedQtyNumber,
      staging_location_id: resolvedStagingLocationId || undefined,
      package_count: shouldCaptureContainedBoxes ? parseOptionalNumber(packageCount) : 1,
      pallet_count: shouldCapturePalletCount ? parseOptionalNumber(palletCount) : undefined,
      rent_free_days: parseOptionalNumber(rentFreeDays),
      measured_weight_kg: parseOptionalNumber(measuredWeightKg),
      measured_length_cm: parseOptionalNumber(measuredLengthCm),
      measured_width_cm: parseOptionalNumber(measuredWidthCm),
      measured_height_cm: parseOptionalNumber(measuredHeightCm),
      receiving_note: receivingNote.trim() || undefined,
    });
  };

  const handleReceiptPrimaryAction = () => {
    if (!scannedLabel) {
      scrollToScanSurface();
      return;
    }
    if (confirmReceiptBlockedByStaging) {
      focusStagingSelector();
      return;
    }
    if (confirmReceiptBlockedByHandlingUnits) {
      setHandlingUnitSplitError(
        t(
          "receivingFlow.handlingUnitSplitBeforeConfirm",
          "Split these handling units into separate package records before confirming receipt.",
        ),
      );
      return;
    }
    handleReceiveLine();
  };

  const handleMobileDockContinue = () => {
    if (!resolvedStagingLocationId && !applyStagingLocationEntry()) {
      stagingLocationEntryRef.current?.querySelector("input")?.focus();
      return;
    }
    setMobileReceiptFocus("quantity");
  };

  const handleMobileQuantityContinue = () => {
    if (confirmReceiptBlockedByHandlingUnits) {
      setHandlingUnitSplitError(
        t(
          "receivingFlow.handlingUnitSplitBeforeConfirm",
          "Split these handling units into separate package records before confirming receipt.",
        ),
      );
      return;
    }
    if (receiptQuantityValidationMessage) {
      setReceiptError(receiptQuantityValidationMessage);
      return;
    }
    if (!receiptQuantityEntered) {
      setReceiptError(
        t("receivingFlow.mobileQuantityRequired", "Enter received or damaged quantity before confirming."),
      );
      return;
    }
    setReceiptError("");
    setMobileReceiptFocus("confirm");
  };

  const handlePrintLabels = async (labelCode?: string) => {
    if (!selectedOrder || receivingLabels.length === 0 || typeof window === "undefined") return;
    const printableLabels = receivingLabels.filter((label) => label.status === "received");
    const labelsToPrint = labelCode
      ? printableLabels.filter((label) => label.label_code === labelCode)
      : printableLabels;
    if (labelsToPrint.length === 0) return;
    const printWindow = window.open("", "_blank", "width=900,height=700");
    if (!printWindow) return;
    const rows = labelsToPrint
      .map(
        (label) => {
          const packageHeaderParts = [
            label.package_number != null
              ? t("receivingFlow.packageCardTitle", "Package {number}", {
                  number: label.package_number,
                })
              : null,
            label.package_type || label.label_type || null,
          ].filter(Boolean);
          const fieldRows = activeTemplateFields
            .map((field) => {
              const value = printFieldValue(label, field);
              if (value === "—") return "";
              const title = printFieldLabel(field);
              if (labelTemplateSettings?.show_field_labels === false) {
                return `<div style="margin-top:4px;font-size:14px;color:#374151;">${value}</div>`;
              }
              return `<div style="margin-top:4px;font-size:14px;color:#374151;"><strong>${title}:</strong> ${value}</div>`;
            })
            .filter(Boolean)
            .join("");
          return `
          <div style="border:1px solid #d9d1c4;border-radius:12px;padding:16px;margin-bottom:12px;">
            <div style="font-size:12px;letter-spacing:0.18em;color:#6b7280;text-transform:uppercase;">${t("receivingFlow.printLabelHeading", "Receiving label")}</div>
            <div style="font-size:24px;font-weight:700;margin-top:8px;">${label.label_code}</div>
            ${
              packageHeaderParts.length
                ? `<div style="margin-top:8px;display:inline-block;border:1px solid #d7d0c4;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:600;color:#51606b;background:#fcfaf5;">${packageHeaderParts.join(" · ")}</div>`
                : ""
            }
            <div style="margin-top:4px;font-size:14px;color:#374151;"><strong>${t("receivingFlow.labelType", "Label type")}:</strong> ${label.label_type}</div>
            ${fieldRows}
          </div>
        `;
        },
      )
      .join("");
    printWindow.document.write(`
      <html>
        <head>
          <title>${selectedOrder.order_number} labels</title>
        </head>
        <body style="font-family:Arial,sans-serif;padding:24px;">
          <h1 style="font-size:22px;margin:0 0 8px;">${t("receivingFlow.printSheetTitle", "Receiving labels")}</h1>
          <p style="margin:0 0 20px;color:#6b7280;">${selectedOrder.order_number}</p>
          ${rows}
        </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
    await markPrintedMutation.mutateAsync(labelsToPrint.map((label) => label.label_code));
  };

  const matchedByLabel = scannedLabel?.matched_by
    ? scannedLabel.matched_by === "external_tracking_number"
      ? t("receivingFlow.matchedByTracking", "Matched by tracking number")
      : scannedLabel.matched_by === "external_carton_mark"
        ? t("receivingFlow.matchedByCarton", "Matched by carton mark")
        : scannedLabel.matched_by === "external_customer_barcode"
          ? t("receivingFlow.matchedByCustomerBarcode", "Matched by customer barcode")
          : t("receivingFlow.matchedBySystemLabel", "Matched by system label")
    : null;

  const observedCodeTypeLabel = (codeType: string) => {
    switch (codeType) {
      case "tracking_number":
        return t("receivingFlow.detectedCodeTracking", "Tracking Number");
      case "carton_mark":
        return t("receivingFlow.detectedCodeCarton", "Carton Mark");
      case "customer_barcode":
        return t("receivingFlow.detectedCodeCustomerBarcode", "Customer Box Code");
      case "receiving_label":
        return t("receivingFlow.detectedCodeReceivingLabel", "Receiving Label");
      default:
        return t("receivingFlow.detectedCodeOther", "Other code");
    }
  };

  const observedCodeSourceLabel = (source: string) => {
    switch (source) {
      case "photo":
        return t("receivingFlow.codeSourcePhoto", "Photo");
      case "manual":
        return t("receivingFlow.codeSourceManual", "Manual");
      default:
        return t("receivingFlow.codeSourceScan", "Scan");
    }
  };

  const externalCodesForLabel = (label: {
    external_tracking_number?: string | null;
    external_carton_mark?: string | null;
    external_customer_barcode?: string | null;
  }) =>
    [
      label.external_tracking_number
        ? `${t("receivingFlow.externalTrackingShort", "Tracking")}: ${label.external_tracking_number}`
        : null,
      label.external_carton_mark
        ? `${t("receivingFlow.externalCartonShort", "Carton")}: ${label.external_carton_mark}`
        : null,
      label.external_customer_barcode
        ? `${t("receivingFlow.externalCustomerBarcodeShort", "Customer code")}: ${label.external_customer_barcode}`
        : null,
    ].filter(Boolean);

  const activePackageExternalCodes = scannedLabel ? externalCodesForLabel(scannedLabel) : [];

  const activeTemplateFields =
    labelTemplateSettings?.fields?.length
      ? labelTemplateSettings.fields
      : ["order_number", "sku_code", "expected_qty", "tracking_number"];

  const printFieldLabel = (field: string) => {
    switch (field) {
      case "order_number":
        return t("receivingLabelSettings.fieldOrderNumber", "Inbound order");
      case "package_number":
        return t("receivingLabelSettings.fieldPackageNumber", "Package number");
      case "package_type":
        return t("receivingLabelSettings.fieldPackageType", "Package type");
      case "reference_number":
        return t("receivingLabelSettings.fieldReferenceNumber", "Reference");
      case "sku_code":
        return t("receivingLabelSettings.fieldSkuCode", "SKU code");
      case "sku_name":
        return t("receivingLabelSettings.fieldSkuName", "SKU name");
      case "expected_qty":
        return t("receivingLabelSettings.fieldExpectedQty", "Expected qty");
      case "received_qty":
        return t("receivingLabelSettings.fieldReceivedQty", "Received qty");
      case "tracking_number":
        return t("receivingLabelSettings.fieldTrackingNumber", "Tracking number");
      case "carton_mark":
        return t("receivingLabelSettings.fieldCartonMark", "Carton mark");
      case "customer_barcode":
        return t("receivingLabelSettings.fieldCustomerBarcode", "Customer box code");
      case "package_count":
        return t("receivingLabelSettings.fieldPackageCount", "Number of boxes");
      case "pallet_count":
        return t("receivingLabelSettings.fieldPalletCount", "Pallets quantity");
      case "weight":
        return t("receivingLabelSettings.fieldWeight", "Weight");
      case "dimensions":
        return t("receivingLabelSettings.fieldDimensions", "Dimensions");
      case "rent_free_days":
        return t("receivingLabelSettings.fieldRentFreeDays", "Rent-free days");
      case "receiving_note":
        return t("receivingLabelSettings.fieldReceivingNote", "Receiving note");
      default:
        return field;
    }
  };

  const activeTemplateFieldLabels = activeTemplateFields.map((field) => ({
    field,
    label: printFieldLabel(field),
  }));
  const templateFieldLabelsShown = labelTemplateSettings?.show_field_labels ?? true;

  const printFieldValue = (label: ReceivingLabelSummary, field: string) => {
    switch (field) {
      case "order_number":
        return selectedOrder?.order_number || "—";
      case "package_number":
        return label.package_number != null ? String(label.package_number) : "—";
      case "package_type":
        return label.package_type || label.label_type || "—";
      case "reference_number":
        return label.reference_number || selectedOrder?.reference_number || "—";
      case "sku_code":
        return label.sku_code || "—";
      case "sku_name":
        return label.sku_name || "—";
      case "expected_qty":
        return String(label.expected_qty ?? "—");
      case "received_qty":
        return String(label.received_qty ?? "—");
      case "tracking_number":
        return label.external_tracking_number || "—";
      case "carton_mark":
        return label.external_carton_mark || "—";
      case "customer_barcode":
        return label.external_customer_barcode || "—";
      case "package_count":
        return label.package_count != null ? String(label.package_count) : "—";
      case "pallet_count":
        return label.pallet_count != null ? String(label.pallet_count) : "—";
      case "weight":
        return label.measured_weight_kg != null ? `${label.measured_weight_kg} kg` : "—";
      case "dimensions": {
        const parts = [label.measured_length_cm, label.measured_width_cm, label.measured_height_cm]
          .filter((value) => value != null)
          .map((value) => String(value));
        return parts.length === 3 ? `${parts.join(" × ")} cm` : "—";
      }
      case "rent_free_days":
        return label.rent_free_days != null ? String(label.rent_free_days) : "—";
      case "receiving_note":
        return label.receiving_note || "—";
      default:
        return "—";
    }
  };

  const focusStagingSelector = () => {
    if (typeof document === "undefined") return;
    document.getElementById("receiving-staging-selector")?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => stagingLocationEntryRef.current?.querySelector("input")?.focus(), 200);
  };

  const openNextPendingPackage = (ignoredCode = "") => {
    const normalizedIgnoredCode = ignoredCode.trim().toLowerCase();
    const nextPendingPackageWithCode = pendingPackages.find((pkg) => {
      const lookupCode = packageLookupCode(pkg);
      return lookupCode && lookupCode.trim().toLowerCase() !== normalizedIgnoredCode;
    });
    setStep("scan");
    if (nextPendingPackageWithCode) {
      scanLabelMutation.mutate({ labelCode: packageLookupCode(nextPendingPackageWithCode), source: "manual" });
      return true;
    }

    const nextPendingPackage = pendingPackages.find((pkg) => pkg.id !== scannedLabel?.package_id);
    if (nextPendingPackage) {
      openPackageMutation.mutate(nextPendingPackage.id);
      return true;
    }

    const nextPendingLabel = receivingLabels.find(
      (label) => label.status !== "received" && label.label_code.trim().toLowerCase() !== normalizedIgnoredCode,
    );
    if (nextPendingLabel) {
      scanLabelMutation.mutate({ labelCode: nextPendingLabel.label_code, source: "manual" });
      return true;
    }

    return false;
  };

  const focusReceiptStagingRecovery = () => {
    if (scannedLabel) {
      focusStagingSelector();
      return;
    }

    const packageNeedingStaging = confirmedPackages.find((pkg) => {
      const goodQty = Number(pkg.received_qty || 0) - Number(pkg.damaged_qty || 0);
      if (goodQty <= 0) return false;
      if (!pkg.staging_location_id) return true;
      return !stagingLocations.some((location: any) => location.id === pkg.staging_location_id);
    });

    if (packageNeedingStaging) {
      openReceiptCorrection(packageNeedingStaging);
    }
    setStep("scan");
    window.setTimeout(() => {
      const correctionPanel = document.getElementById("receiving-receipt-correction");
      correctionPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
      correctionPanel?.querySelector("select")?.focus();
      if (!correctionPanel) focusStagingSelector();
    }, 200);
  };

  const getRecoveryState = (message: string, source: "scan" | "receipt" | "complete", code = ""): ReceivingRecoveryState | null => {
    const lower = message.toLowerCase();

    if (source === "scan") {
      if (lower.includes("already been received")) {
        return {
          code: "scan_already_received",
          title: t("receivingFlow.recoveryAlreadyReceivedTitle", "This code is already closed out"),
          body: t(
            "receivingFlow.recoveryAlreadyReceivedBody",
            "This package is already received. Skip this code and continue with the next open package; if nothing is left, review the inbound summary.",
          ),
          actions: ["continue_next", "review_inbound", "scan_again"] as RecoveryAction[],
        };
      }
      if (lower.includes("start receiving")) {
        return {
          code: "scan_order_not_open",
          title: t("receivingFlow.recoveryNotOpenTitle", "This inbound order is not open for receiving"),
          body: t("receivingFlow.recoveryNotOpenBody", "Go back to the work queue, open the inbound order, then return straight to scanning."),
          actions: ["back_to_orders"] as RecoveryAction[],
        };
      }
      if (lower.includes("does not match") || lower.includes("not found")) {
        if (packageRecords.length === 0) {
          return {
            code: "scan_no_package_match",
            title: t("receivingFlow.recoveryNoPackageMatchTitle", "Create a package before scanning this code"),
            body: t(
              "receivingFlow.recoveryNoPackageMatchBody",
              "Tracking numbers, carton marks, and customer barcodes only match package records that already exist. Add the first package and save that code on it, or scan a printed internal receiving label.",
            ),
            actions: ["add_package", "clear_scan", "back_to_orders"] as RecoveryAction[],
          };
        }
        return {
          code: "scan_no_match",
          title: t("receivingFlow.recoveryNoMatchTitle", "This scanned code did not match the current inbound"),
          body: t("receivingFlow.recoveryNoMatchBody", "Try another label, tracking number, carton mark, or customer barcode. If the freight belongs to another inbound order, switch back to the queue first."),
          actions: ["clear_scan", "back_to_orders"] as RecoveryAction[],
        };
      }
    }

    if (source === "receipt") {
      if (lower.includes("staging location")) {
        return {
          code: "receipt_staging_required",
          title: t("receivingFlow.recoveryNeedStagingTitle", "Pick a staging location first"),
          body: t("receivingFlow.recoveryNeedStagingBody", "Good units need a real dock or staging location before this receipt can be confirmed."),
          actions: ["focus_staging"] as RecoveryAction[],
        };
      }
      if (lower.includes("damaged quantity")) {
        return {
          code: "receipt_damaged_quantity",
          title: t("receivingFlow.recoveryDamagedQtyTitle", "Damaged units cannot exceed the received quantity"),
          body: t("receivingFlow.recoveryDamagedQtyBody", "Adjust the good and damaged counts so they match what actually reached the dock."),
          actions: ["scan_again"] as RecoveryAction[],
        };
      }
      if (lower.includes("at least one") || lower.includes("nothing received")) {
        return {
          code: "receipt_empty_quantity",
          title: t("receivingFlow.recoveryNothingReceivedTitle", "Enter what actually arrived"),
          body: t("receivingFlow.recoveryNothingReceivedBody", "Confirm at least one good or damaged unit before trying to close this receipt."),
          actions: ["scan_again"] as RecoveryAction[],
        };
      }
    }

    if (source === "complete") {
      if (code === "open_packages_remain" || lower.includes("still open") || lower.includes("finish receiving every expected package")) {
        return {
          code: code || "open_packages_remain",
          title: t("receivingFlow.recoveryCompleteOpenPackagesTitle", "Packages still need receiving"),
          body: t("receivingFlow.recoveryCompleteOpenPackagesBody", "Open the next package, confirm what arrived, then complete receiving again."),
          actions: ["open_next_package", "review_inbound", "back_to_orders"] as RecoveryAction[],
        };
      }
      if (
        code === "staging_location_required" ||
        lower.includes("staging location") ||
        lower.includes("missing source") ||
        lower.includes("no longer exists")
      ) {
        return {
          code: code || "staging_location_required",
          title: t("receivingFlow.recoveryCompleteStagingTitle", "Dock or staging needs review"),
          body: t("receivingFlow.recoveryCompleteStagingBody", "Correct the package dock/staging source, then complete receiving again."),
          actions: ["focus_staging", "review_receipts", "refresh_order", "back_to_orders"] as RecoveryAction[],
        };
      }
      if (code === "order_not_receiving" || lower.includes("currently")) {
        return {
          code: code || "order_not_receiving",
          title: t("receivingFlow.recoveryCompleteStaleStatusTitle", "Inbound status changed"),
          body: t("receivingFlow.recoveryCompleteStaleStatusBody", "Refresh the inbound status. If another station already released it, go back to the queue."),
          actions: ["refresh_order", "back_to_orders"] as RecoveryAction[],
        };
      }
      return {
        code: code || "complete_failed",
        title: t("receivingFlow.recoveryCompleteGenericTitle", "Complete receiving needs another check"),
        body: t("receivingFlow.recoveryCompleteGenericBody", "Review the inbound summary, refresh the latest status, or return to the work queue."),
        actions: ["review_inbound", "refresh_order", "back_to_orders"] as RecoveryAction[],
      };
    }

    return null;
  };

  const activeScanError =
    scanError ||
    (scanLabelMutation.isError
      ? apiErrorText(
          scanLabelMutation.error,
          t("receivingFlow.scanNotMatched", "This scanned code does not match the current inbound order."),
        )
      : "");
  const scanRecovery = activeScanError ? getRecoveryState(activeScanError, "scan") : null;
  const receiptRecovery = receiptError ? getRecoveryState(receiptError, "receipt") : null;
  const completeErrorText = completeMutation.isError
    ? isOfflineMutationQueuedError(completeMutation.error)
      ? offlineQueuedText()
      : apiErrorText(
          completeMutation.error,
          t("receivingFlow.completeError", "Receiving could not be completed. Review the inbound order and try again."),
        )
    : "";
  const completeRecovery = completeErrorText
    ? getRecoveryState(completeErrorText, "complete", apiErrorCode(completeMutation.error))
    : null;

  const runRecoveryAction = (action: RecoveryAction) => {
    switch (action) {
      case "back_to_orders":
        returnToOrderSelection();
        break;
      case "clear_scan":
        scanLabelMutation.reset();
        setScannedLabel(null);
        setScanError("");
        setLastAttemptedScanCode("");
        setReceiptError("");
        setReceiptOfflineNotice("");
        setCurrentQty("1");
        setDamagedQty("0");
        setMeasurementDefaultsKey("");
        break;
      case "continue_next": {
        const ignoredCode = lastAttemptedScanCode.trim().toLowerCase();
        scanLabelMutation.reset();
        setScannedLabel(null);
        setScanError("");
        setLastAttemptedScanCode("");
        setReceiptError("");
        setReceiptOfflineNotice("");
        setMobileReceiptFocus("scan");

        if (openNextPendingPackage(ignoredCode)) {
          break;
        }

        setStep("review");
        break;
      }
      case "review_receipts":
        setStep("scan");
        window.setTimeout(() => {
          document.getElementById("receiving-received-lines")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 200);
        break;
      case "review_inbound":
        scanLabelMutation.reset();
        setScannedLabel(null);
        setScanError("");
        setLastAttemptedScanCode("");
        setReceiptError("");
        setReceiptOfflineNotice("");
        completeMutation.reset();
        setStep("review");
        break;
      case "focus_staging":
        focusReceiptStagingRecovery();
        break;
      case "scan_again":
        scanLabelMutation.reset();
        setScanError("");
        setLastAttemptedScanCode("");
        setReceiptError("");
        setReceiptOfflineNotice("");
        break;
      case "add_package":
        setScanError("");
        setLastAttemptedScanCode("");
        setReceiptError("");
        setReceiptOfflineNotice("");
        openCreatePackageEditor();
        break;
      case "open_next_package":
        setScannedLabel(null);
        setScanError("");
        setLastAttemptedScanCode("");
        setReceiptError("");
        setReceiptOfflineNotice("");
        setMobileReceiptFocus("scan");
        completeMutation.reset();
        if (!openNextPendingPackage()) {
          setStep("scan");
          window.setTimeout(() => scrollToScanSurface(), 200);
        }
        break;
      case "refresh_order":
        setScanError("");
        setReceiptError("");
        setReceiptOfflineNotice("");
        completeMutation.reset();
        void refreshReceivingWork();
        break;
    }
  };

  // ─── Step: Select Order ───
  if (step === "select") {
    return (
      <SelectStep
        t={t}
        orders={orders}
        activeReceivingOrders={activeReceivingOrders}
        readyToOpenOrders={readyToOpenOrders}
        startPending={startMutation.isPending}
        startPendingOrderId={startPendingOrderId}
        onSelectOrder={handleSelectOrder}
      />
    );
  }

  // ─── Step: Prepare Receiving ───
  if (step === "prepare" && selectedOrder) {
    return (
      <PrepareStep
        t={t}
        order={selectedOrder}
        startPending={startMutation.isPending}
        printableLabelCount={printableLabelCount}
        printError={printError}
        onBack={returnToOrderSelection}
        onStartReceiving={() => startMutation.mutate(selectedOrder.id)}
        onPrintLabels={() => void handlePrintLabels()}
      />
    );
  }

  // ─── Step: Scan & Receive ───
  if (step === "scan") {
    return (
      <div className="space-y-4">
        <div className="hidden md:block">
          <ReceivingFlowProgress currentStage="scan" t={t} />
        </div>
        <MobileFlowGuide
          eyebrow={t("receivingFlow.mobileActiveOrderEyebrow", "Active inbound")}
          contextTitle={selectedOrder?.order_number || t("receivingFlow.mobileFocusFallbackTitle", "Receiving")}
          title={mobileReceivingStepTitle}
          hint={mobileReceivingStepHint}
          steps={mobileReceivingStepItems}
          onBack={returnToOrderSelection}
          backLabel={t("receivingFlow.mobileBackShort", "Back")}
          compact
        />

        {receiptOfflineNotice ? (
          <div className="rounded-2xl border border-[#b9d8c6] bg-[#edf8f1] px-4 py-3 shadow md:hidden">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#2f7648]">
                  {t("receivingFlow.mobileQueuedReceiptEyebrow", "Queued receipt")}
                </p>
                <p className="mt-1 text-sm font-semibold text-[#13212c]">
                  {t("receivingFlow.mobileQueuedReceiptTitle", "Saved for automatic sync")}
                </p>
                <p className="mt-1 text-xs leading-5 text-[#1b5f38]">{receiptOfflineNotice}</p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  setReceiptOfflineNotice("");
                  setMobileReceiptFocus("scan");
                  scrollToScanSurface();
                }}
                className="rounded-xl bg-[#13212c] px-3 py-2 text-xs font-semibold text-white"
              >
                {t("receivingFlow.mobileQueuedReceiptScanNext", "Scan next package")}
              </button>
              <button
                type="button"
                onClick={returnToOrderSelection}
                className="rounded-xl border border-[#28543b]/20 bg-white px-3 py-2 text-xs font-semibold text-[#163424]"
              >
                {t("receivingFlow.mobileQueuedReceiptBack", "Back to queue")}
              </button>
            </div>
          </div>
        ) : null}

        {scannedLabel ? (
          <div className="rounded-2xl border border-[#e3ddd2] bg-white px-4 py-3 shadow md:hidden">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("receivingFlow.mobileCurrentPackageEyebrow", "Current package")}
                </p>
                <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">{activePackageTitle}</p>
                <p className="mt-1 truncate text-xs leading-5 text-[#61717d]">
                  {activePackageSkuLine.length ? activePackageSkuLine.join(" · ") : selectedOrder?.order_number || "—"}
                </p>
              </div>
              <span className="shrink-0 rounded-full border border-[#d7d0c4] bg-[#fcfaf5] px-3 py-1 text-xs font-medium text-[#51606b]">
                {t("receivingFlow.labelRemaining", "Still to receive")}: {scannedLabel.remaining_qty}
              </span>
            </div>
          </div>
        ) : null}

        {lastConfirmedLabelCode ? (
          <div
            className="rounded-2xl border border-[#c8dfd1] bg-[#eef8f0] px-4 py-3 shadow md:hidden"
            data-testid="receiving-mobile-success-next-step"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#4f7b61]">
                  {t("receivingFlow.mobileRecentReceiptEyebrow", "Just confirmed")}
                </p>
                <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">{mobileRecentReceiptTitle()}</p>
                <p className="mt-1 text-xs leading-5 text-[#28543b]">{mobileRecentReceiptNextStep()}</p>
              </div>
              <button
                type="button"
                onClick={handleMobileRecentReceiptAction}
                className="shrink-0 rounded-xl border border-[#28543b]/20 bg-white px-3 py-2 text-xs font-medium text-[#163424]"
              >
                {mobileRecentReceiptActionLabel()}
              </button>
            </div>
          </div>
        ) : null}

        <div className="hidden rounded-2xl bg-white p-5 shadow md:block">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <button
                type="button"
                onClick={returnToOrderSelection}
                className="mb-4 inline-flex items-center gap-2 rounded-full border border-[#13212c]/12 bg-[#13212c] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#243545]"
              >
                <ArrowLeft size={16} />
                {t("receivingFlow.prepareBack", "Back to inbound list")}
              </button>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
                {t("receivingFlow.liveReceivingEyebrow", "Receiving")}
              </p>
              <h2 className="mt-2 text-lg font-semibold text-[#13212c]">
                {t("receivingFlow.step2Title", "Scan and confirm what is physically at the dock")}
              </h2>
            </div>
            <div className="flex flex-col items-end gap-2">
              <button
                type="button"
                onClick={() => {
                  if (!canReviewReceiving) return;
                  setStep("review");
                }}
                disabled={!canReviewReceiving}
                className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-[#cbd5e1] disabled:text-[#51606b]"
              >
                {t("receivingFlow.reviewReceivingAction", "Review receiving")} →
              </button>
              {reviewReceivingBlockedReason ? (
                <p className="max-w-[15rem] text-right text-xs leading-5 text-[#61717d]">
                  {reviewReceivingBlockedReason}
                </p>
              ) : null}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
              {t("receivingFlow.prepareOrderLabel", "Inbound order")}: {selectedOrder?.order_number || "—"}
            </span>
            <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
              {t("receivingFlow.stagingLocation", "Staging Location")}:{" "}
              {stagingLocations.find((location: any) => location.id === stagingLocation)?.barcode ||
                (scannedLabel
                  ? t("receivingFlow.stagingPending", "Pick before confirming receipt")
                  : t("receivingFlow.stagingDeferred", "Choose after the first scan"))}
            </span>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            <ProcessSignal
              label={t("receivingFlow.processExternalCodes", "External codes first")}
              value={String(pendingExternalCodeCount)}
              detail={t("receivingFlow.processExternalCodesDetail", "Pending dock codes before confirmation")}
            />
            <ProcessSignal
              label={t("receivingFlow.processInternalLabels", "Internal labels after confirm")}
              value={String(printableLabelCount)}
              detail={t("receivingFlow.processInternalLabelsDetail", "Warehouse labels issued from confirmed receipts")}
            />
            <ProcessSignal
              label={t("receivingFlow.processPrintQueue", "Print queue")}
              value={String(unprintedLabelCount)}
              detail={t("receivingFlow.processPrintQueueDetail", "Internal labels still waiting for print")}
            />
          </div>

          {lastConfirmedLabelCode ? (
            <div className="mt-4 hidden rounded-2xl border border-[#c8dfd1] bg-[#eef8f0] px-4 py-3 md:block">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#4f7b61]">
                    {t("receivingFlow.internalLabelIssuedEyebrow", "Internal label issued")}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[#163424]">
                    {t("receivingFlow.internalLabelIssuedBody", "Confirmed receipt created warehouse label {label}.", {
                      label: lastConfirmedLabelCode,
                    })}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {printableLabelCount > 0 ? (
                    <button
                      type="button"
                      onClick={() => void handlePrintLabels(lastConfirmedLabelCode)}
                      className="rounded-xl border border-[#28543b]/20 bg-white px-4 py-2 text-sm font-medium text-[#163424]"
                    >
                      {t("receivingFlow.printLatestInternalLabelAction", "Print this internal label")}
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="hidden rounded-2xl bg-white p-4 shadow md:block">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("receivingFlow.packageQueueEyebrow", "Package queue")}
                </p>
                <span className="rounded-full border border-[#d7d0c4] bg-[#fcfaf5] px-3 py-1 text-[11px] font-medium text-[#51606b]">
                  {t("receivingFlow.packageQueueOpen", "{count} open", { count: pendingPackageCount })}
                </span>
              </div>
            <div className="flex flex-wrap items-center gap-2">
              {activePackageFocus ? (
                <button
                  type="button"
                  onClick={clearPackageFocus}
                  className="rounded-xl border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                >
                  {t("receivingFlow.packageFocusClearAction", "Clear focus")}
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => openCreatePackageEditor()}
                className="rounded-xl border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
              >
                {t("receivingFlow.packageAddAction", "Add package")}
              </button>
              {scannedLabel?.package_id ? (
                <button
                  type="button"
                  onClick={() =>
                    openCreatePackageEditor({
                      lineId: scannedLabel.line_id,
                      splitFrom: packageRecords.find((pkg) => pkg.id === scannedLabel.package_id) || null,
                    })
                  }
                  className="rounded-xl border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                >
                  {t("receivingFlow.packageSplitAction", "Split another package")}
                </button>
              ) : null}
            </div>
          </div>

          {packageRecords.length === 0 ? (
            <div className="mt-3 rounded-xl border border-dashed border-[#d8d1c5] bg-[#f7f3ec] px-3 py-3 text-sm text-[#61717d]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span>
                  {t(
                    "receivingFlow.packageQueueEmpty",
                    "No package records exist yet. Add the first package and save its tracking, carton, or customer code there before scanning an external freight code. A printed internal receiving label can still be scanned.",
                  )}
                </span>
                <button
                  type="button"
                  onClick={() => openCreatePackageEditor()}
                  className="rounded-xl border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                >
                  {t("receivingFlow.packageAddFirstAction", "Add the first package")}
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {packageRecords.map((pkg) => {
                const lookupCode = packageLookupCode(pkg);
                const isActivePackage = scannedLabel?.package_id === pkg.id;
                const isHighlightedPackage = activeDrillPackageId === pkg.id;
                const packageExternalCodes = externalCodesForLabel({
                  external_tracking_number: pkg.external_tracking_number,
                  external_carton_mark: pkg.external_carton_mark,
                  external_customer_barcode: pkg.external_customer_barcode,
                });

                return (
                  <div
                    key={pkg.id}
                    className={`rounded-2xl border p-3 ${
                      isActivePackage ? "border-[#13212c] bg-[#f7f4ee]" : "border-[#e3ddd2] bg-[#fcfaf5]"
                    } ${
                      !isActivePackage && isHighlightedPackage ? "ring-2 ring-[#4977c8]/35" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">
                          {t("receivingFlow.packageCardTitle", "Package {number}", {
                            number: pkg.package_number,
                          })}
                        </p>
                        <p className="mt-1 text-xs text-[#61717d]">
                          {pkg.sku_code || pkg.sku_id || "—"}
                          {pkg.line_number ? ` · ${t("receivingFlow.lineNumberShort", "Line")} ${pkg.line_number}` : ""}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-[#d7d0c4] bg-white px-2.5 py-1 text-[11px] font-medium text-[#51606b]">
                          {packageOriginLabel(pkg.package_origin, t)}
                        </span>
                        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${packageStatusTone(pkg.status)}`}>
                          {packageStatusLabel(pkg.status)}
                        </span>
                      </div>
                    </div>

                    {isActivePackage ? (
                      <div className="mt-3 grid gap-2 sm:grid-cols-3">
                        <div className="rounded-xl border border-[#e3ddd2] bg-white px-3 py-2">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7f8d98]">
                            {t("receivingFlow.labelExpected", "Expected")}
                          </p>
                          <p className="mt-1 text-sm font-semibold text-[#13212c]">{pkg.expected_qty}</p>
                        </div>
                        <label className="rounded-xl border border-[#c9ddf4] bg-white px-3 py-2">
                          <span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#416f9c]">
                            {t("receivingFlow.packageCardReceiveNow", "Receive now")}
                          </span>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={0}
                            value={currentQty}
                            onChange={(e) => setCurrentQty(normalizeReceiptQuantityInput(e.target.value))}
                            onFocus={(e) => e.currentTarget.select()}
                            disabled={receiveMutation.isPending}
                            className="mt-1 w-full border-0 bg-transparent p-0 text-sm font-semibold text-[#13212c] outline-none focus:ring-0 disabled:opacity-55"
                            aria-label={t("receivingFlow.packageCardReceiveNow", "Receive now")}
                          />
                        </label>
                        <label className="rounded-xl border border-[#f0c8bd] bg-white px-3 py-2">
                          <span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#9b452a]">
                            {t("receivingFlow.damagedQty", "Damaged")}
                          </span>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={0}
                            value={damagedQty}
                            onChange={(e) => setDamagedQty(normalizeReceiptQuantityInput(e.target.value))}
                            onFocus={(e) => e.currentTarget.select()}
                            disabled={receiveMutation.isPending}
                            className="mt-1 w-full border-0 bg-transparent p-0 text-sm font-semibold text-[#13212c] outline-none focus:ring-0 disabled:opacity-55"
                            aria-label={t("receivingFlow.damagedQty", "Damaged")}
                          />
                        </label>
                      </div>
                    ) : (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                          {t("receivingFlow.labelExpected", "Expected")}: {pkg.expected_qty}
                        </span>
                        <span className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                          {t("receivingFlow.labelAlreadyReceived", "Already received")}: {pkg.received_qty}
                        </span>
                        <span className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                          {t("receivingFlow.damagedQty", "Damaged")}: {pkg.damaged_qty}
                        </span>
                      </div>
                    )}

                    {packageExternalCodes.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {packageExternalCodes.slice(0, 2).map((code) => (
                          <span
                            key={code}
                            className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]"
                          >
                            {code}
                          </span>
                        ))}
                      </div>
                    ) : null}

                    <div className="mt-3 flex flex-wrap gap-2">
                      {!isPackageClosed(pkg) ? (
                        <button
                          type="button"
                          data-receiving-open-package-code={lookupCode || undefined}
                          onClick={() => {
                            if (lookupCode) {
                              handleScan(lookupCode, "manual");
                              return;
                            }
                            openPackageMutation.mutate(pkg.id);
                          }}
                          className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                        >
                          {isActivePackage
                            ? t("receivingFlow.packageQueueFocused", "Active package")
                            : t("receivingFlow.packageQueueOpenAction", "Open package")}
                        </button>
                      ) : null}
                      {!isPackageClosed(pkg) ? (
                        <button
                          type="button"
                          onClick={() => openCreatePackageEditor({ lineId: pkg.order_line_id, splitFrom: pkg })}
                          className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                        >
                          {t("receivingFlow.packageSplitActionShort", "Split")}
                        </button>
                      ) : null}
                      {!isPackageClosed(pkg) ? (
                        <button
                          type="button"
                          onClick={() => openEditPackageEditor(pkg)}
                          className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                        >
                          {t("receivingFlow.packageEditAction", "Edit")}
                        </button>
                      ) : null}
                      {canCorrectPackageMetadata(pkg) ? (
                        <button
                          type="button"
                          onClick={() => openReceiptCorrection(pkg)}
                          className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                        >
                          {t("receivingFlow.correctReceiptAction", "Correct receipt")}
                        </button>
                      ) : null}
                      {!isPackageClosed(pkg) ? (
                        <button
                          type="button"
                          onClick={() => deletePackageMutation.mutate(pkg.id)}
                          disabled={deletePackageMutation.isPending}
                          className="rounded-xl border border-[#f0c8bd] bg-white px-3 py-1.5 text-xs font-medium text-[#9b452a] disabled:opacity-45"
                        >
                          {t("receivingFlow.packageDeleteAction", "Remove")}
                        </button>
                      ) : null}
                      {pkg.label_sequence ? (
                        <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                          {t("receivingFlow.packageQueueLabelSequence", "Internal slot {sequence}", {
                            sequence: pkg.label_sequence,
                          })}
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <PackageEditorPanel
          t={t}
          packageEditor={packageEditor}
          dispatchPackageEditor={dispatchPackageEditor}
          lineSummaries={lineSummaries}
          lineEditorLabel={lineEditorLabel}
          submitting={createPackageMutation.isPending || updatePackageMutation.isPending || openPackageMutation.isPending}
          onSubmit={handleSubmitPackageEditor}
          onCancel={resetPackageEditor}
        />

        <ReceiptCorrectionPanel
          t={t}
          correction={correction}
          dispatchCorrection={dispatchCorrection}
          packageRecords={packageRecords}
          stagingLocations={stagingLocations}
          canCorrectPackageQuantity={canCorrectPackageQuantity}
          saving={correctPackageMutation.isPending}
          onSubmit={handleSubmitReceiptCorrection}
          onCancel={resetReceiptCorrection}
        />

        <div
          ref={scanSurfaceRef}
          className={`rounded-2xl bg-white p-4 shadow ${
            scannedLabel || mobileEffectiveReceiptFocus === "confirmed" ? "hidden md:block" : ""
          }`}
        >
          {!isLoadingPackages && packageRecords.length === 0 ? (
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3 border-l-4 border-[#f0cf9d] bg-[#fff8ec] px-3 py-2 text-sm text-[#6f6248]">
              <div className="max-w-2xl">
                <p className="font-semibold text-[#13212c]">
                  {t("receivingFlow.scanNoPackageTitle", "Add a package before scanning external codes")}
                </p>
                <p className="mt-1 leading-6">
                  {t(
                    "receivingFlow.scanNoPackageBody",
                    "Manual tracking numbers, carton marks, and customer barcodes only work after they are saved on a package record. Use Add package first, or scan a printed internal receiving label.",
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={() => openCreatePackageEditor()}
                className="rounded-xl border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-semibold text-[#13212c]"
              >
                {t("receivingFlow.packageAddFirstAction", "Add the first package")}
              </button>
            </div>
          ) : null}
          <BarcodeScanner
            onScan={handleScan}
            context="receiving"
            placeholder={scannerPlaceholder}
            suggestedCodes={scannerCodeSuggestions.map((code) => ({ label: code.label, value: code.value }))}
          />
          {activeScanError ? (
            <div className="mt-3 space-y-3">
              <div className="rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-3 text-sm text-[#9b452a]">
                <p className="font-semibold text-[#7f321d]">
                  {t("receivingFlow.scanFailedTitle", "Scan did not match this inbound")}
                </p>
                {lastAttemptedScanCode ? (
                  <p className="mt-1 break-all font-mono text-xs text-[#9b452a]">{lastAttemptedScanCode}</p>
                ) : null}
                <p className="mt-2">{activeScanError}</p>
                {!scanRecovery ? (
                  <p className="mt-2 text-xs leading-5 text-[#7f5d4c]">
                    {t(
                      "receivingFlow.scanFailedBody",
                      "The last code was checked but could not be used for this order. Review the message below, add a package code if needed, or scan a printed internal receiving label.",
                    )}
                  </p>
                ) : null}
              </div>
              {scanRecovery ? (
                <RecoveryPanel
                  code={scanRecovery.code}
                  title={scanRecovery.title}
                  body={scanRecovery.body}
                  actions={scanRecovery.actions}
                  onAction={runRecoveryAction}
                  t={t}
                />
              ) : null}
            </div>
          ) : null}
        </div>

        {scannedLabel ? (
          <details className="hidden rounded-2xl border border-[#e3ddd2] bg-white p-3 shadow md:hidden">
            <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
              {t("receivingFlow.mobileScanAnotherToggle", "Scan another code")}
            </summary>
            <div className="mt-3">
              <BarcodeScanner
                onScan={handleScan}
                context="receiving"
                placeholder={scannerPlaceholder}
                suggestedCodes={scannerCodeSuggestions.map((code) => ({ label: code.label, value: code.value }))}
              />
            </div>
          </details>
        ) : null}

        {scannedLabel ? (() => {
          const scannedLabelExternalCodes = externalCodesForLabel(scannedLabel);
          const shouldOpenCapturedCodes =
            Boolean(editingCodeId) ||
            Boolean(draftCodeValue.trim()) ||
            observedCodes.some((code) => !code.is_confirmed);
          return (
          <div
            className={`rounded-lg bg-white p-4 shadow space-y-3 ${
              mobileEffectiveReceiptFocus === "dock" ? "" : "hidden md:block"
            }`}
          >
            <div className="hidden items-start justify-between gap-3 md:flex">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("receivingFlow.labelMatched", "Receiving code matched")}
                </p>
                <h3 className="mt-2 text-base font-semibold text-[#13212c]">{scannedLabel.label_code}</h3>
                {matchedByLabel ? (
                  <p className="mt-2 inline-flex items-center rounded-full border border-[#d7d0c4] bg-[#f8f4ec] px-3 py-1 text-xs font-medium text-[#51606b]">
                    {matchedByLabel}
                    {scannedLabel?.scanned_code && scannedLabel.scanned_code !== scannedLabel.label_code
                      ? ` · ${scannedLabel.scanned_code}`
                      : ""}
                  </p>
                ) : null}
              </div>
            </div>
            <div
              className={`rounded-2xl bg-white p-3 md:hidden ${
                mobileEffectiveReceiptFocus === "dock" ? "" : "hidden"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-[#13212c]">
                  {t("receivingFlow.mobileDockStagingLabel", "Dock / staging")}
                </p>
                <span className="shrink-0 rounded-full border border-[#d7d0c4] bg-[#fcfaf5] px-3 py-1 text-xs font-medium text-[#51606b]">
                  {t("receivingFlow.packageCardTitle", "Package {number}", {
                    number: scannedLabel.package_number || 1,
                  })}
                </span>
              </div>
              <div className="mt-3 space-y-3">
                  <p className="rounded-xl border border-[#ead9b8] bg-[#fff9ed] px-3 py-2 text-xs font-medium leading-5 text-[#6f4c12]">
                    {t(
                      "receivingFlow.mobileStagingRequiredHint",
                      "Step 3 is locked until this package has a valid dock/staging location.",
                    )}
                  </p>
                  <div ref={stagingLocationEntryRef}>
                    <BarcodeScanner
                      onScan={handleStagingLocationScan}
                      context="receiving-staging"
                      placeholder={t("receivingFlow.stagingManualPlaceholder", "Scan or type dock/staging code")}
                      suggestedCodes={stagingScannerSuggestions}
                      manualHintTitle={t("receivingFlow.stagingScannerHintTitle", "Dock/staging code")}
                      manualHintBody={t(
                        "receivingFlow.stagingScannerHintBody",
                        "Scan or type the dock/staging barcode. Use the list only when the location label cannot be scanned.",
                      )}
                      deviceHint={t(
                        "receivingFlow.stagingScannerDeviceHint",
                        "Use Scan to open the phone camera, type a dock/staging code, or Read photo if the browser supports photo decoding.",
                      )}
                    />
                  </div>
                  {stagingLocationEntryError ? (
                    <p className="rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-xs text-[#9b452a]">
                      {stagingLocationEntryError}
                    </p>
                  ) : null}
                  <details className="rounded-xl border border-[#e3ddd2] bg-[#fcfaf5] px-3 py-2">
                    <summary className="cursor-pointer list-none text-xs font-semibold text-[#51606b]">
                      {t("receivingFlow.stagingListFallback", "Or choose from list")}
                    </summary>
                    <select
                      value={stagingLocation}
                      onChange={(e) => chooseStagingLocation(e.target.value)}
                      className="mt-2 w-full rounded-xl border border-[#cbd8e3] bg-white px-3 py-3 text-sm text-[#13212c]"
                    >
                      <option value="">{t("receivingFlow.chooseStagingLocation", "Choose staging location")}</option>
                      {stagingLocations.map((location: any) => (
                        <option key={location.id} value={location.id}>
                          {stagingLocationLabel(location)}
                        </option>
                      ))}
                    </select>
                  </details>
                  {resolvedStagingLocationId ? (
                    <>
                      <div
                        aria-live="polite"
                        className="rounded-xl border border-[#c8dfd1] bg-[#eef8f0] px-3 py-3 text-xs leading-5 text-[#28543b]"
                      >
                        <p className="font-semibold">
                          {t("receivingFlow.mobileStagingConfirmed", "Dock/staging confirmed")}
                        </p>
                        <p className="mt-1 font-medium">
                          {t("receivingFlow.mobileSelectedStaging", "Selected dock/staging")}:{" "}
                          {selectedStagingLocation ? stagingLocationCode(selectedStagingLocation) : stagingLocation}
                        </p>
                        <p className="mt-1">
                          {t(
                            "receivingFlow.mobileStagingConfirmedHint",
                            "This package will move to quantity check next.",
                          )}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={handleMobileDockContinue}
                        className="w-full rounded-xl bg-[#13212c] px-4 py-3 text-sm font-semibold text-white"
                      >
                        {t("receivingFlow.mobileGoToQuantity", "Continue to quantity")}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      disabled
                      className="w-full rounded-xl bg-[#aeb7bf] px-4 py-3 text-sm font-semibold text-white"
                    >
                      {t("receivingFlow.mobileChooseStagingToContinue", "Choose dock")}
                    </button>
                  )}
                </div>
            </div>

            <div className="hidden rounded-2xl border border-[#e3ddd2] bg-[#f8f4ec] p-3 md:block">
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                  {t("receivingFlow.packageCardTitle", "Package {number}", {
                    number: scannedLabel.package_number || 1,
                  })}
                </span>
                <span className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                  {t("receivingFlow.labelRemaining", "Still to receive")}: {scannedLabel.remaining_qty}
                </span>
                <span className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                  {t("receivingFlow.detectedCodeLabel", "Detected code")}: {scannedLabel.scanned_code || scannedLabel.label_code}
                </span>
              </div>
            </div>
            {scannedLabelExternalCodes.length > 0 ? (
              <div className="hidden rounded-2xl border border-[#e3ddd2] bg-[#f8f4ec] p-3 md:block">
                <div className="flex flex-wrap gap-2">
                  {scannedLabelExternalCodes.map((code) => (
                    <span
                      key={code}
                      className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]"
                    >
                      {code}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
            <details
              open={shouldOpenCapturedCodes}
              className="hidden rounded-2xl border border-[#e3ddd2] bg-white p-3 md:block"
            >
              <summary className="cursor-pointer list-none">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("receivingFlow.capturedCodesEyebrow", "Extra external labels")}
                  </p>
                  <span className="rounded-full border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#51606b]">
                    {observedCodes.length}
                  </span>
                </div>
              </summary>

              <div className="mt-3 space-y-3">
                {observedCodes.length > 0 ? (
                  <div className="space-y-2">
                    {observedCodes.map((code) => (
                      <div
                        key={code.id}
                        className="rounded-xl border border-[#e3ddd2] bg-[#fbf8f2] px-3 py-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="break-all text-sm font-semibold text-[#13212c]">{code.code_value}</p>
                            <p className="mt-1 text-xs text-[#61717d]">
                              {observedCodeTypeLabel(code.code_type)} · {observedCodeSourceLabel(code.source)}
                            </p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {code.is_primary ? (
                                <span className="rounded-full border border-[#c8dfd1] bg-[#eef8f0] px-2.5 py-1 text-[11px] font-medium text-[#28543b]">
                                  {t("receivingFlow.primaryCode", "Primary")}
                                </span>
                              ) : null}
                              {code.is_confirmed ? (
                                <span className="rounded-full border border-[#c8dfd1] bg-[#eef8f0] px-2.5 py-1 text-[11px] font-medium text-[#28543b]">
                                  {t("receivingFlow.codeConfirmedState", "Saved to internal label")}
                                </span>
                              ) : (
                                <span className="rounded-full border border-[#d7d0c4] bg-white px-2.5 py-1 text-[11px] font-medium text-[#51606b]">
                                  {t("receivingFlow.codePendingState", "Pending confirm")}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setEditingCodeId(code.id);
                                setDraftCodeValue(code.code_value);
                                setDraftCodeType(code.code_type);
                              }}
                              disabled={code.is_confirmed}
                              className="rounded-xl border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#13212c] disabled:opacity-45"
                            >
                              {t("receivingFlow.editCodeAction", "Edit")}
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteObservedCodeMutation.mutate(code.id)}
                              disabled={code.is_confirmed || deleteObservedCodeMutation.isPending}
                              className="rounded-xl border border-[#f0c8bd] px-3 py-1 text-xs font-medium text-[#9b452a] disabled:opacity-45"
                            >
                              {t("receivingFlow.deleteCodeAction", "Delete")}
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-[#d8d1c5] bg-[#f7f3ec] px-3 py-2 text-sm text-[#61717d]">
                    {t("receivingFlow.capturedCodesEmpty", "No external codes have been captured for this package yet. Scan another visible code or add one manually below.")}
                  </div>
                )}

                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px_auto]">
                  <input
                    type="text"
                    value={draftCodeValue}
                    onChange={(e) => setDraftCodeValue(e.target.value)}
                    placeholder={t("receivingFlow.addCodePlaceholder", "Add another visible code")}
                    className="w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                  />
                  <select
                    value={draftCodeType}
                    onChange={(e) => setDraftCodeType(e.target.value)}
                    className="w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                  >
                    <option value="other">{t("receivingFlow.detectedCodeOther", "Other code")}</option>
                    <option value="tracking_number">{t("receivingFlow.detectedCodeTracking", "Tracking Number")}</option>
                    <option value="carton_mark">{t("receivingFlow.detectedCodeCarton", "Carton Mark")}</option>
                    <option value="customer_barcode">{t("receivingFlow.detectedCodeCustomerBarcode", "Customer Box Code")}</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      if (!draftCodeValue.trim()) return;
                      if (editingCodeId) {
                        const current = observedCodes.find((code) => code.id === editingCodeId);
                        updateObservedCodeMutation.mutate({
                          codeId: editingCodeId,
                          codeValue: draftCodeValue,
                          codeType: draftCodeType,
                          isPrimary: current?.is_primary || false,
                        });
                        return;
                      }
                      addObservedCodeMutation.mutate();
                    }}
                    disabled={
                      !draftCodeValue.trim() ||
                      addObservedCodeMutation.isPending ||
                      updateObservedCodeMutation.isPending
                    }
                    className="rounded-xl bg-[#13212c] px-4 py-2 text-sm font-medium text-white disabled:opacity-45"
                  >
                    {editingCodeId
                      ? t("receivingFlow.saveCodeAction", "Save code")
                      : t("receivingFlow.addCodeAction", "Add code")}
                  </button>
                </div>
                {editingCodeId ? (
                  <button
                    type="button"
                    onClick={() => {
                      setEditingCodeId(null);
                      setDraftCodeValue("");
                      setDraftCodeType("other");
                    }}
                    className="text-xs font-medium text-[#51606b]"
                  >
                    {t("receivingFlow.cancelCodeEditAction", "Cancel code edit")}
                  </button>
                ) : null}
              </div>
            </details>
            <details className="rounded-2xl border border-[#e3ddd2] bg-[#fcfaf5] p-3 md:hidden">
              <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                {t("receivingFlow.mobilePackageMoreToggle", "More package info")}
              </summary>
              <div className="mt-3 space-y-3">
                <div className="rounded-2xl border border-[#e3ddd2] bg-white p-3">
                  <p className="break-all text-sm font-semibold text-[#13212c]">
                    {scannedLabel.scanned_code || scannedLabel.label_code}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="rounded-full border border-[#e3ddd2] bg-[#fcfaf5] px-3 py-1 text-[11px] font-medium text-[#51606b]">
                      {t("receivingFlow.labelExpected", "Expected")}: {scannedLabel.expected_qty}
                    </span>
                    <span className="rounded-full border border-[#e3ddd2] bg-[#fcfaf5] px-3 py-1 text-[11px] font-medium text-[#51606b]">
                      {t("receivingFlow.labelAlreadyReceived", "Already received")}: {scannedLabel.received_qty}
                    </span>
                  </div>
                  {scannedLabelExternalCodes.length > 0 ? (
                    <div className="mt-3 space-y-1">
                      {scannedLabelExternalCodes.map((code) => (
                        <p key={code} className="text-xs text-[#51606b]">
                          {code}
                        </p>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm font-medium text-[#13212c]">
                    {t("receivingFlow.mobileCapturedCodesToggle", "Extra external labels")}
                  </div>
                  <span className="rounded-full border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#51606b]">
                    {observedCodes.length}
                  </span>
                </div>
                {observedCodes.length > 0 ? (
                  <div className="space-y-2">
                    {observedCodes.map((code) => (
                      <div key={code.id} className="rounded-xl border border-[#e3ddd2] bg-white px-3 py-3">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="break-all text-sm font-semibold text-[#13212c]">{code.code_value}</p>
                            <p className="mt-1 text-xs text-[#61717d]">
                              {observedCodeTypeLabel(code.code_type)} · {observedCodeSourceLabel(code.source)}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setEditingCodeId(code.id);
                                setDraftCodeValue(code.code_value);
                                setDraftCodeType(code.code_type);
                              }}
                              disabled={code.is_confirmed}
                              className="rounded-xl border border-[#d7d0c4] px-3 py-1 text-xs font-medium text-[#13212c] disabled:opacity-45"
                            >
                              {t("receivingFlow.editCodeAction", "Edit")}
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteObservedCodeMutation.mutate(code.id)}
                              disabled={code.is_confirmed || deleteObservedCodeMutation.isPending}
                              className="rounded-xl border border-[#f0c8bd] px-3 py-1 text-xs font-medium text-[#9b452a] disabled:opacity-45"
                            >
                              {t("receivingFlow.deleteCodeAction", "Delete")}
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-[#d8d1c5] bg-white px-3 py-2 text-sm text-[#61717d]">
                    {t("receivingFlow.capturedCodesEmpty", "No external codes have been captured for this package yet. Scan another visible code or add one manually below.")}
                  </div>
                )}
                <div className="grid gap-3">
                  <input
                    type="text"
                    value={draftCodeValue}
                    onChange={(e) => setDraftCodeValue(e.target.value)}
                    placeholder={t("receivingFlow.addCodePlaceholder", "Add another visible code")}
                    className="w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                  />
                  <select
                    value={draftCodeType}
                    onChange={(e) => setDraftCodeType(e.target.value)}
                    className="w-full rounded-xl border border-[#d7dfe5] bg-white px-3 py-2 text-sm text-[#13212c]"
                  >
                    <option value="other">{t("receivingFlow.detectedCodeOther", "Other code")}</option>
                    <option value="tracking_number">{t("receivingFlow.detectedCodeTracking", "Tracking Number")}</option>
                    <option value="carton_mark">{t("receivingFlow.detectedCodeCarton", "Carton Mark")}</option>
                    <option value="customer_barcode">{t("receivingFlow.detectedCodeCustomerBarcode", "Customer Box Code")}</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      if (!draftCodeValue.trim()) return;
                      if (editingCodeId) {
                        const current = observedCodes.find((code) => code.id === editingCodeId);
                        updateObservedCodeMutation.mutate({
                          codeId: editingCodeId,
                          codeValue: draftCodeValue,
                          codeType: draftCodeType,
                          isPrimary: current?.is_primary || false,
                        });
                        return;
                      }
                      addObservedCodeMutation.mutate();
                    }}
                    disabled={
                      !draftCodeValue.trim() ||
                      addObservedCodeMutation.isPending ||
                      updateObservedCodeMutation.isPending
                    }
                    className="rounded-xl bg-[#13212c] px-4 py-2 text-sm font-medium text-white disabled:opacity-45"
                  >
                    {editingCodeId
                      ? t("receivingFlow.saveCodeAction", "Save code")
                      : t("receivingFlow.addCodeAction", "Add code")}
                  </button>
                  {editingCodeId ? (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingCodeId(null);
                        setDraftCodeValue("");
                        setDraftCodeType("other");
                      }}
                      className="text-xs font-medium text-[#51606b]"
                    >
                      {t("receivingFlow.cancelCodeEditAction", "Cancel code edit")}
                    </button>
                  ) : null}
                </div>
              </div>
            </details>
          </div>
        )})() : null}

        {/* Quick receive form */}
        <div
          ref={confirmReceiptRef}
          id="receiving-staging-selector"
          className={`rounded-2xl bg-white p-4 shadow space-y-4 ${
            scannedLabel
              ? mobileEffectiveReceiptFocus === "dock"
                ? "hidden md:block"
                : ""
              : "hidden border border-dashed border-[#d8d1c5] md:block"
          }`}
        >
            <div className="space-y-2">
              <div className="md:hidden">
                {scannedLabel ? (
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-sm font-semibold text-[#13212c]">{activePackageTitle}</p>
                    {resolvedStagingLocationId ? (
                      <span className="shrink-0 rounded-full border border-[#c8dfd1] bg-[#eef8f0] px-3 py-1 text-xs font-medium text-[#28543b]">
                        {selectedStagingLocation ? stagingLocationCode(selectedStagingLocation) : stagingLocation}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="hidden md:block">
                <h3 className="text-sm font-medium text-gray-700">
                  {scannedLabel
                    ? t("receivingFlow.confirmingPackageHeading", "Confirming {name}", {
                        name: activePackageTitle,
                      })
                    : t("receivingFlow.recordReceipt", "Confirm Receipt")}
                </h3>
              </div>
            </div>
            {scannedLabel ? (
              <div className="hidden rounded-2xl border border-[#e3ddd2] bg-[#fcfaf5] p-3 md:block">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">
                      {t("receivingFlow.currentPackageContext", "Current package")}
                    </p>
                    <p className="mt-1 text-sm font-semibold text-[#13212c]">{activePackageTitle}</p>
                    <p className="mt-1 text-xs leading-5 text-[#61717d]">
                      {activePackageSkuLine.length ? activePackageSkuLine.join(" · ") : scannedLabel.label_code}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                      {activePackageTypeName}
                    </span>
                    <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                      {packageStatusLabel(scannedLabel.package_status || scannedLabel.status)}
                    </span>
                  </div>
                </div>
                {activePackageExternalCodes.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {activePackageExternalCodes.map((code) => (
                      <span
                        key={code}
                        className="rounded-full border border-[#e3ddd2] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]"
                      >
                        {code}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            <div className="hidden rounded-2xl border border-[#e3ddd2] bg-[#f8f4ec] p-3 md:block">
              <div className="flex items-center justify-between gap-3">
                <label className="block text-xs font-medium uppercase tracking-[0.16em] text-[#7f8d98] mb-2">
                  {t("receivingFlow.stagingLocation", "Staging Location")}
                </label>
                {scannedLabel ? (
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                      resolvedStagingLocationId
                        ? "bg-[#eef8f0] text-[#28543b]"
                        : "bg-[#fff6e6] text-[#91621a]"
                    }`}
                  >
                    {resolvedStagingLocationId
                      ? t("receivingFlow.mobileStagingReady", "Staging ready")
                      : t("receivingFlow.mobileStagingPending", "Still required")}
                  </span>
                ) : null}
              </div>
              <select
                value={stagingLocation}
                onChange={(e) => chooseStagingLocation(e.target.value)}
                disabled={!scannedLabel}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
              >
                <option value="">{t("receivingFlow.chooseStagingLocation", "Choose staging location")}</option>
                {stagingLocations.map((location: any) => (
                  <option key={location.id} value={location.id}>
                    {stagingLocationLabel(location)}
                  </option>
                ))}
              </select>
            </div>
            {scannedLabel && mobileEffectiveReceiptFocus === "quantity" ? (
              <div className="rounded-2xl border border-[#e3ddd2] bg-[#fbf8f2] p-3 md:hidden">
                <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                  {t("receivingFlow.quantityEyebrow", "Receipt quantity")}
                </p>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  <div className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-2">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-[#7f8d98]">
                      {t("receivingFlow.expectedSkuQtyShort", "Expected")}
                    </p>
                    <p className="mt-1 text-base font-semibold text-[#13212c]">{activePackageExpectedQty}</p>
                  </div>
                  <label className="rounded-xl border border-[#c9ddf4] bg-white px-3 py-2">
                    <span className="text-[10px] uppercase tracking-[0.14em] text-[#24507a]">
                      {t("receivingFlow.receiveSkuQtyShort", "Receive")}
                    </span>
                    <input
                      type="number"
                      value={currentQty}
                      onChange={(e) => {
                        setCurrentQty(normalizeReceiptQuantityInput(e.target.value));
                        setReceiptError("");
                      }}
                      onFocus={(e) => e.currentTarget.select()}
                      min={0}
                      disabled={!scannedLabel}
                      aria-label={t("receivingFlow.receiveSkuQty", "Receive SKU qty")}
                      className="mt-1 w-full border-0 bg-transparent p-0 text-base font-semibold text-[#13212c] outline-none"
                    />
                  </label>
                  <label className="rounded-xl border border-[#f0c8bd] bg-white px-3 py-2">
                    <span className="text-[10px] uppercase tracking-[0.14em] text-[#9b452a]">
                      {t("receivingFlow.damagedSkuQtyShort", "Damaged")}
                    </span>
                    <input
                      type="number"
                      value={damagedQty}
                      onChange={(e) => {
                        setDamagedQty(normalizeReceiptQuantityInput(e.target.value));
                        setReceiptError("");
                      }}
                      onFocus={(e) => e.currentTarget.select()}
                      min={0}
                      disabled={!scannedLabel}
                      aria-label={t("receivingFlow.damagedSkuQty", "Damaged SKU qty")}
                      className="mt-1 w-full border-0 bg-transparent p-0 text-base font-semibold text-[#13212c] outline-none"
                    />
                  </label>
                </div>

                <div
                  aria-live="polite"
                  className={`mt-3 rounded-xl border px-3 py-3 text-xs leading-5 ${
                    receiptQuantityValidationMessage
                      ? "border-[#f2c2b4] bg-[#fff1eb] text-[#9b452a]"
                      : receiptQuantityEntered
                      ? "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]"
                      : "border-[#ead9b8] bg-[#fff9ed] text-[#6f4c12]"
                  }`}
                >
                  {receiptQuantityValidationMessage ? (
                    <p className="font-semibold">{receiptQuantityValidationMessage}</p>
                  ) : receiptQuantityEntered ? (
                    <>
                      <p className="font-semibold">
                        {t("receivingFlow.mobileQuantityReady", "Quantity ready for confirmation")}
                      </p>
                      <p className="mt-1">
                        {t("receivingFlow.mobileQuantityReadySummary", "Receiving {received}; damaged {damaged}.", {
                          received: String(currentQtyNumber),
                          damaged: String(damagedQtyNumber),
                        })}
                      </p>
                    </>
                  ) : (
                    <p className="font-semibold">
                      {t("receivingFlow.mobileQuantityMissing", "Enter received or damaged quantity to continue.")}
                    </p>
                  )}
                </div>

                <details className="mt-3 rounded-xl border border-[#e3ddd2] bg-white px-3 py-3">
                  <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                    {t("receivingFlow.mobileReceiptDetailsToggle", "More fields")}
                  </summary>
                  <div className="mt-3 space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.packageTypeField", "Package type")}
                        </label>
                        <div className="mt-1 flex min-h-10 items-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-[#13212c]">
                          {activePackageTypeName}
                        </div>
                      </div>
                      {shouldCaptureHandlingUnitCount ? (
                        <div>
                          <label className="text-xs text-gray-500">
                            {t("receivingFlow.handlingUnitCount", "Handling units")}
                          </label>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={1}
                            step={1}
                            value={handlingUnitCount}
                            onChange={(e) => {
                              setHandlingUnitCount(e.target.value);
                              setHandlingUnitSplitError("");
                            }}
                            disabled={!scannedLabel || splitHandlingUnitsMutation.isPending}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                      ) : null}
                      {shouldCaptureContainedBoxes ? (
                        <div>
                          <label className="text-xs text-gray-500">{containedPackageCountLabel}</label>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={0}
                            value={packageCount}
                            onChange={(e) => setPackageCount(e.target.value)}
                            disabled={!scannedLabel}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                      ) : null}
                      {shouldCapturePalletCount ? (
                        <div>
                          <label className="text-xs text-gray-500">{palletCountLabel}</label>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={0}
                            value={palletCount}
                            onChange={(e) => setPalletCount(e.target.value)}
                            disabled={!scannedLabel}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                      ) : null}
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.rentFreeDays", "Rent-free period (days)")}
                        </label>
                        <input
                          type="number"
                          inputMode="numeric"
                          min={0}
                          value={rentFreeDays}
                          onChange={(e) => setRentFreeDays(e.target.value)}
                          disabled={!scannedLabel}
                          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                        />
                      </div>
                    </div>
                    {hasMultipleHandlingUnits ? (
                      <div className="rounded-xl border border-[#f1d8a8] bg-[#fff9ed] p-3">
                        <p className="text-sm font-semibold text-[#6f4c12]">
                          {t("receivingFlow.handlingUnitSplitTitle", "Track separate units as separate packages")}
                        </p>
                        <button
                          type="button"
                          onClick={() => splitHandlingUnitsMutation.mutate()}
                          disabled={!canSplitHandlingUnits || splitHandlingUnitsMutation.isPending}
                          className="mt-3 rounded-xl bg-[#13212c] px-4 py-2 text-xs font-semibold text-white disabled:opacity-45"
                        >
                          {splitHandlingUnitsMutation.isPending
                            ? t("receivingFlow.handlingUnitSplitWorking", "Splitting...")
                            : t("receivingFlow.handlingUnitSplitAction", "Create {count} {type} packages", {
                                count: handlingUnitCountNumber,
                                type: activePackageTypeName,
                              })}
                        </button>
                      </div>
                    ) : null}
                    {handlingUnitSplitError ? (
                      <p className="rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-xs text-[#9b452a]">
                        {handlingUnitSplitError}
                      </p>
                    ) : null}
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.grossWeightKg", "Gross weight (kg)")}
                        </label>
                        <input
                          type="number"
                          inputMode="decimal"
                          min={0}
                          step="0.001"
                          value={measuredWeightKg}
                          onChange={(e) => setMeasuredWeightKg(e.target.value)}
                          disabled={!scannedLabel || hasMultipleHandlingUnits}
                          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                        />
                      </div>
                      <div className="grid grid-cols-3 gap-2 sm:col-span-2">
                        <div>
                          <label className="text-xs text-gray-500">{t("receivingFlow.outerLengthCm", "Outer L (cm)")}</label>
                          <input
                            type="number"
                            inputMode="decimal"
                            min={0}
                            step="0.01"
                            value={measuredLengthCm}
                            onChange={(e) => setMeasuredLengthCm(e.target.value)}
                            disabled={!scannedLabel || hasMultipleHandlingUnits}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">{t("receivingFlow.outerWidthCm", "Outer W (cm)")}</label>
                          <input
                            type="number"
                            inputMode="decimal"
                            min={0}
                            step="0.01"
                            value={measuredWidthCm}
                            onChange={(e) => setMeasuredWidthCm(e.target.value)}
                            disabled={!scannedLabel || hasMultipleHandlingUnits}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">{t("receivingFlow.outerHeightCm", "Outer H (cm)")}</label>
                          <input
                            type="number"
                            inputMode="decimal"
                            min={0}
                            step="0.01"
                            value={measuredHeightCm}
                            onChange={(e) => setMeasuredHeightCm(e.target.value)}
                            disabled={!scannedLabel || hasMultipleHandlingUnits}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.receivingNote", "Receiving note")}
                      </label>
                      <textarea
                        value={receivingNote}
                        onChange={(e) => setReceivingNote(e.target.value)}
                        disabled={!scannedLabel}
                        rows={3}
                        className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                      />
                    </div>
                  </div>
                </details>
              </div>
            ) : null}
            {scannedLabel && mobileEffectiveReceiptFocus === "confirm" ? (
              <div className="rounded-2xl bg-white p-3 md:hidden">
                <div className="space-y-2">
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-xl border border-[#d7d0c4] bg-[#fcfaf5] px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.14em] text-[#7f8d98]">
                        {t("receivingFlow.expectedSkuQtyShort", "Expected")}
                      </p>
                      <p className="mt-1 text-base font-semibold text-[#13212c]">{activePackageExpectedQty}</p>
                    </div>
                    <div className="rounded-xl border border-[#c9ddf4] bg-[#f3f8fb] px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.14em] text-[#24507a]">
                        {t("receivingFlow.receiveSkuQtyShort", "Receive")}
                      </p>
                      <p className="mt-1 text-base font-semibold text-[#13212c]">{currentQty}</p>
                    </div>
                    <div className="rounded-xl border border-[#f0c8bd] bg-[#fff8f4] px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.14em] text-[#9b452a]">
                        {t("receivingFlow.damagedSkuQtyShort", "Damaged")}
                      </p>
                      <p className="mt-1 text-base font-semibold text-[#13212c]">{damagedQty}</p>
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setMobileReceiptFocus("quantity")}
                  className="mt-3 rounded-xl border border-[#d7d0c4] bg-white px-3 py-2 text-xs font-semibold text-[#13212c]"
                >
                  {t("receivingFlow.mobileEditQuantityAction", "Edit quantity")}
                </button>
              </div>
            ) : null}
            <div className="hidden rounded-2xl border border-[#e3ddd2] bg-[#fbf8f2] p-4 md:block">
              <div className="grid gap-4 xl:grid-cols-[minmax(280px,0.85fr)_minmax(0,1.55fr)]">
                <section className="space-y-3 border-b border-[#13212c]/8 pb-4 xl:border-b-0 xl:border-r xl:pb-0 xl:pr-4">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                      {t("receivingFlow.quantityEyebrow", "Receipt quantity")}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[#61717d]">
                      {t(
                        "receivingFlow.quantityHelp",
                        "These fields count SKU units inside the current package, not cartons or crates.",
                      )}
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.expectedSkuQty", "Expected SKU qty")}
                      </label>
                      <div className="mt-1 flex min-h-10 items-center rounded-lg border border-[#d7d0c4] bg-white px-3 py-2 text-sm font-semibold text-[#13212c]">
                        {activePackageExpectedQty}
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.receiveSkuQty", "Receive SKU qty")}
                      </label>
                      <input
                        type="number"
                        value={currentQty}
                        onChange={(e) => setCurrentQty(normalizeReceiptQuantityInput(e.target.value))}
                        onFocus={(e) => e.currentTarget.select()}
                        min={0}
                        disabled={!scannedLabel}
                        aria-label={t("receivingFlow.receiveSkuQty", "Receive SKU qty")}
                        className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.damagedSkuQty", "Damaged SKU qty")}
                      </label>
                      <input
                        type="number"
                        value={damagedQty}
                        onChange={(e) => setDamagedQty(normalizeReceiptQuantityInput(e.target.value))}
                        onFocus={(e) => e.currentTarget.select()}
                        min={0}
                        disabled={!scannedLabel}
                        aria-label={t("receivingFlow.damagedSkuQty", "Damaged SKU qty")}
                        className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                      />
                    </div>
                  </div>
                </section>

                <div className="grid gap-4 2xl:grid-cols-2">
                  <section className="space-y-3">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                        {t("receivingFlow.handlingUnitsEyebrow", "Handling units")}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[#61717d]">
                        {t(
                          "receivingFlow.handlingUnitsHelp",
                          "Use this for physical cartons, crates, pallets, or master units. Each separate carton or crate should become its own package record.",
                        )}
                      </p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.packageTypeField", "Package type")}
                        </label>
                        <div className="mt-1 flex min-h-10 items-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-[#13212c]">
                          {activePackageTypeName}
                        </div>
                      </div>
                      {shouldCaptureHandlingUnitCount ? (
                        <div>
                          <label className="text-xs text-gray-500">
                            {t("receivingFlow.handlingUnitCount", "Handling units")}
                          </label>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={1}
                            step={1}
                            value={handlingUnitCount}
                            onChange={(e) => {
                              setHandlingUnitCount(e.target.value);
                              setHandlingUnitSplitError("");
                            }}
                            disabled={!scannedLabel || splitHandlingUnitsMutation.isPending}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                      ) : null}
                      {!scannedLabel || shouldCaptureContainedBoxes ? (
                        <div>
                          <label className="text-xs text-gray-500">{containedPackageCountLabel}</label>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={0}
                            value={packageCount}
                            onChange={(e) => setPackageCount(e.target.value)}
                            disabled={!scannedLabel}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                          {scannedLabel ? (
                            <p className="mt-1 text-xs leading-5 text-[#61717d]">{containedPackageCountHelp}</p>
                          ) : null}
                        </div>
                      ) : null}
                      {shouldCapturePalletCount ? (
                        <div>
                          <label className="text-xs text-gray-500">{palletCountLabel}</label>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={0}
                            value={palletCount}
                            onChange={(e) => setPalletCount(e.target.value)}
                            disabled={!scannedLabel}
                            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                          />
                        </div>
                      ) : null}
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.rentFreeDays", "Rent-free period (days)")}
                        </label>
                        <input
                          type="number"
                          inputMode="numeric"
                          min={0}
                          value={rentFreeDays}
                          onChange={(e) => setRentFreeDays(e.target.value)}
                          disabled={!scannedLabel}
                          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                        />
                      </div>
                    </div>
                    {hasMultipleHandlingUnits ? (
                      <div className="rounded-xl border border-[#f1d8a8] bg-[#fff9ed] p-3">
                        <p className="text-sm font-semibold text-[#6f4c12]">
                          {t("receivingFlow.handlingUnitSplitTitle", "Track separate units as separate packages")}
                        </p>
                        <p className="mt-1 text-xs leading-5 text-[#7a633b]">
                          {handlingUnitSplitQuantities.length
                            ? t(
                                "receivingFlow.handlingUnitSplitBody",
                                "This will keep the current package and create {count} more package records. Planned SKU qty per package: {plan}.",
                                {
                                  count: handlingUnitSplitQuantities.length - 1,
                                  plan: handlingUnitSplitQuantities.join(" / "),
                                },
                              )
                            : t(
                                "receivingFlow.handlingUnitSplitInvalid",
                                "Automatic split needs at least one expected SKU unit per handling unit.",
                              )}
                        </p>
                        <button
                          type="button"
                          onClick={() => splitHandlingUnitsMutation.mutate()}
                          disabled={!canSplitHandlingUnits || splitHandlingUnitsMutation.isPending}
                          className="mt-3 rounded-xl bg-[#13212c] px-4 py-2 text-xs font-semibold text-white disabled:opacity-45"
                        >
                          {splitHandlingUnitsMutation.isPending
                            ? t("receivingFlow.handlingUnitSplitWorking", "Splitting...")
                            : t("receivingFlow.handlingUnitSplitAction", "Create {count} {type} packages", {
                                count: handlingUnitCountNumber,
                                type: activePackageTypeName,
                              })}
                        </button>
                      </div>
                    ) : null}
                    {handlingUnitSplitError ? (
                      <p className="rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-xs text-[#9b452a]">
                        {handlingUnitSplitError}
                      </p>
                    ) : null}
                  </section>

                  <section className="space-y-3 2xl:col-span-2">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                        {t("receivingFlow.measurementsEyebrow", "Physical measurements")}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[#61717d]">
                        {t(
                          "receivingFlow.measurementsDefaultHelp",
                          "Defaults come from saved package, order, or SKU data when available. These values describe the current package.",
                        )}
                      </p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.grossWeightKg", "Gross weight (kg)")}
                        </label>
                        <input
                          type="number"
                          inputMode="decimal"
                          min={0}
                          step="0.001"
                          value={measuredWeightKg}
                          onChange={(e) => setMeasuredWeightKg(e.target.value)}
                          disabled={!scannedLabel || hasMultipleHandlingUnits}
                          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                        />
                      </div>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.outerLengthCm", "Outer L (cm)")}
                        </label>
                        <input
                          type="number"
                          inputMode="decimal"
                          min={0}
                          step="0.01"
                          value={measuredLengthCm}
                          onChange={(e) => setMeasuredLengthCm(e.target.value)}
                          disabled={!scannedLabel || hasMultipleHandlingUnits}
                          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.outerWidthCm", "Outer W (cm)")}
                        </label>
                        <input
                          type="number"
                          inputMode="decimal"
                          min={0}
                          step="0.01"
                          value={measuredWidthCm}
                          onChange={(e) => setMeasuredWidthCm(e.target.value)}
                          disabled={!scannedLabel || hasMultipleHandlingUnits}
                          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">
                          {t("receivingFlow.outerHeightCm", "Outer H (cm)")}
                        </label>
                        <input
                          type="number"
                          inputMode="decimal"
                          min={0}
                          step="0.01"
                          value={measuredHeightCm}
                          onChange={(e) => setMeasuredHeightCm(e.target.value)}
                          disabled={!scannedLabel || hasMultipleHandlingUnits}
                          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                        />
                      </div>
                    </div>
                    {hasMultipleHandlingUnits ? (
                      <p className="rounded-xl border border-[#d6e2ef] bg-[#f4f8fb] px-3 py-2 text-xs leading-5 text-[#51606b]">
                        {t(
                          "receivingFlow.measurementsSplitFirst",
                          "Split first, then record weight and outer dimensions on each package.",
                        )}
                      </p>
                    ) : null}
                    <div>
                      <label className="text-xs text-gray-500">
                        {t("receivingFlow.receivingNote", "Receiving note")}
                      </label>
                      <textarea
                        value={receivingNote}
                        onChange={(e) => setReceivingNote(e.target.value)}
                        disabled={!scannedLabel}
                        rows={3}
                        className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                      />
                    </div>
                  </section>
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={
                mobileEffectiveReceiptFocus === "quantity" ? handleMobileQuantityContinue : handleReceiptPrimaryAction
              }
              disabled={receiveMutation.isPending}
              className="w-full rounded-xl bg-[#13212c] px-5 py-3 text-sm font-medium text-white disabled:opacity-45 md:hidden"
            >
              {mobileEffectiveReceiptFocus === "quantity"
                ? t("receivingFlow.mobileContinueToConfirmAction", "Continue to confirm")
                : canConfirmReceipt
                  ? t("receivingFlow.mobileConfirmStepAction", "Step 4 · Confirm receipt")
                  : receiptPrimaryActionLabel}
            </button>
            <button
              type="button"
              onClick={handleReceiptPrimaryAction}
              disabled={receiveMutation.isPending}
              className="hidden rounded-xl bg-[#13212c] px-5 py-2 text-sm font-medium text-white disabled:opacity-45 md:inline-flex"
            >
              {receiptPrimaryActionLabel}
            </button>
            {receiptOfflineNotice ? (
              <p className="rounded-xl border border-[#b9d8c6] bg-[#edf8f1] px-3 py-2 text-sm text-[#1b5f38]">
                {receiptOfflineNotice}
              </p>
            ) : null}
            {receiptError ? (
              <div className="space-y-3">
                <p className="rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-sm text-[#9b452a]">
                  {receiptError}
                </p>
                {receiptRecovery ? (
                  <RecoveryPanel
                    code={receiptRecovery.code}
                    title={receiptRecovery.title}
                    body={receiptRecovery.body}
                    actions={receiptRecovery.actions}
                    onAction={runRecoveryAction}
                    t={t}
                  />
                ) : null}
              </div>
            ) : null}
        </div>

        <ConfirmedLabelsPanel
          t={t}
          confirmedLabelsRef={confirmedLabelsRef}
          receivingLabels={receivingLabels}
          printableLabelCount={printableLabelCount}
          unprintedLabelCount={unprintedLabelCount}
          printedLabelCount={printedLabelCount}
          lastPrintedLabelCount={lastPrintedLabelCount}
          activeTemplateFieldLabels={activeTemplateFieldLabels}
          templateFieldLabelsShown={templateFieldLabelsShown}
          activePrintPackageId={activePrintPackageId}
          scannedLabel={scannedLabel}
          externalCodesForLabel={externalCodesForLabel}
          onEditTemplate={() => navigate("/receiving-label-settings")}
          onPrintLabels={(labelCode) => void handlePrintLabels(labelCode)}
        />
        {printError ? (
          <p className="rounded-xl border border-[#f2c2b4] bg-[#fff1eb] px-3 py-2 text-sm text-[#9b452a]">
            {printError}
          </p>
        ) : null}

        <details className={`rounded-2xl border border-[#e3ddd2] bg-white p-3 shadow md:hidden ${scannedLabel ? "hidden" : ""}`}>
          <summary className="cursor-pointer list-none">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-[#13212c]">
                {t("receivingFlow.mobileOtherPackagesToggle", "Other packages")}
              </span>
              <span className="rounded-full border border-[#d7d0c4] bg-[#fcfaf5] px-3 py-1 text-xs font-medium text-[#51606b]">
                {t("receivingFlow.packageQueueOpen", "{count} open", { count: pendingPackageCount })}
              </span>
            </div>
          </summary>
          <div className="mt-3 space-y-3">
            <button
              type="button"
              onClick={() => openCreatePackageEditor()}
              className="rounded-xl border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
            >
              {t("receivingFlow.packageAddAction", "Add package")}
            </button>
              {mobileQueuePackages.length === 0 ? (
                <p className="rounded-xl border border-dashed border-[#d8d1c5] bg-[#f7f3ec] px-3 py-2 text-sm text-[#61717d]">
                  {t(
                    "receivingFlow.packageQueueEmpty",
                    "No package records exist yet. Add the first package and save its tracking, carton, or customer code there before scanning an external freight code. A printed internal receiving label can still be scanned.",
                  )}
                </p>
              ) : (
                mobileQueuePackages.map((pkg) => {
                  const lookupCode = packageLookupCode(pkg);
                  const packageExternalCodes = externalCodesForLabel({
                    external_tracking_number: pkg.external_tracking_number,
                    external_carton_mark: pkg.external_carton_mark,
                    external_customer_barcode: pkg.external_customer_barcode,
                  });
                  const primaryExternalCode = packageExternalCodes[0] || t("receivingFlow.mobileQueueNoCode", "No external code yet");
                  return (
                    <div key={pkg.id} className="rounded-2xl border border-[#e3ddd2] bg-white p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[#13212c]">
                            {t("receivingFlow.packageCardTitle", "Package {number}", {
                              number: pkg.package_number,
                            })}
                          </p>
                          <p className="mt-1 text-xs text-[#61717d]">
                            {(pkg.sku_code || pkg.sku_id || "—") +
                              (pkg.line_number ? ` · ${t("receivingFlow.lineNumberShort", "Line")} ${pkg.line_number}` : "")}
                          </p>
                          <p className="mt-2 text-xs text-[#61717d]">{primaryExternalCode}</p>
                        </div>
                        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${packageStatusTone(pkg.status)}`}>
                          {packageStatusLabel(pkg.status)}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {!isPackageClosed(pkg) ? (
                          <button
                            type="button"
                            data-receiving-open-package-code={lookupCode || undefined}
                            onClick={() => {
                              if (lookupCode) {
                                handleScan(lookupCode, "manual");
                                return;
                              }
                              openPackageMutation.mutate(pkg.id);
                            }}
                            className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                          >
                            {t("receivingFlow.packageQueueOpenAction", "Open package")}
                          </button>
                        ) : null}
                        {!isPackageClosed(pkg) ? (
                          <button
                            type="button"
                            onClick={() => openEditPackageEditor(pkg)}
                            className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                          >
                            {t("receivingFlow.packageEditAction", "Edit")}
                          </button>
                        ) : null}
                        {!isPackageClosed(pkg) ? (
                          <button
                            type="button"
                            onClick={() => openCreatePackageEditor({ lineId: pkg.order_line_id, splitFrom: pkg })}
                            className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                          >
                            {t("receivingFlow.packageSplitActionShort", "Split")}
                          </button>
                        ) : null}
                        {canCorrectPackageMetadata(pkg) ? (
                          <button
                            type="button"
                            onClick={() => openReceiptCorrection(pkg)}
                            className="rounded-xl border border-[#d7d0c4] bg-white px-3 py-1.5 text-xs font-medium text-[#13212c]"
                          >
                            {t("receivingFlow.correctReceiptAction", "Correct receipt")}
                          </button>
                        ) : null}
                        {!isPackageClosed(pkg) ? (
                          <button
                            type="button"
                            onClick={() => deletePackageMutation.mutate(pkg.id)}
                            disabled={deletePackageMutation.isPending}
                            className="rounded-xl border border-[#f0c8bd] bg-white px-3 py-1.5 text-xs font-medium text-[#9b452a] disabled:opacity-45"
                          >
                            {t("receivingFlow.packageDeleteAction", "Remove")}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </details>

        {/* Already received */}
        <ReceivedLinesPanel t={t} receivedLines={receivedLines} hasActiveLabel={Boolean(scannedLabel)} />
      </div>
    );
  }

  // ─── Step: Review ───
  if (step === "review") {
    return (
      <ReviewStep
        t={t}
        receivedLines={receivedLines}
        completeErrorText={completeErrorText}
        completeRecovery={completeRecovery}
        completePending={completeMutation.isPending}
        onBackToScanning={() => {
          completeMutation.reset();
          setStep("scan");
        }}
        onComplete={() => completeMutation.mutate()}
        onRecoveryAction={runRecoveryAction}
      />
    );
  }

  // ─── Step: Done ───
  return (
    <DoneStep
      t={t}
      completeSummary={completeSummary}
      onGoToPutaway={() => {
        if (typeof window !== "undefined") {
          window.sessionStorage.setItem("putaway.sourceInboundOrderId", orderId);
        }
        navigate("/putaway");
      }}
      onReceiveAnother={returnToOrderSelection}
    />
  );
}
