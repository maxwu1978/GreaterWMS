/**
 * Mutation layer for the interactive receiving workflow.
 *
 * Every useMutation block was moved verbatim from ReceivingFlow.tsx — no
 * behavior change. The component supplies the state values, setters, and
 * helpers each mutation callback needs through an explicit context object.
 */

import type { Dispatch, SetStateAction } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/api/queryKeys";
import {
  addCapturedReceivingCode,
  createReceivingPackage,
  updateCapturedReceivingCode,
  correctReceivingPackage,
  deleteCapturedReceivingCode,
  deleteReceivingPackage,
  markReceivingLabelsPrinted,
  openReceivingPackage,
  scanReceivingLabel,
  updateReceivingPackage,
} from "../../shared/api/receiving";
import { workbenchSummaryKeys } from "../../shared/api/workbenchSummaries";
import { requestWithOutbox } from "../../shared/offline/mutations";
import { isOfflineMutationQueuedError } from "../../shared/offline/outbox";
import {
  splitQuantityAcrossUnits,
  type CompleteReceivingSummary,
  type InboundPackageSummary,
  type MobileReceiptFocus,
  type ObservedReceivingCode,
  type ReceivedLine,
  type ReceivingLabelSummary,
  type ScannedReceivingLabel,
} from "./receivingFlowUtils";

export type ReceivingStep = "select" | "prepare" | "scan" | "review" | "done";

export interface ReceivingMutationsContext {
  t: (key: string, fallback?: string, vars?: Record<string, string | number>) => string;
  orderId: string;
  scannedLabel: ScannedReceivingLabel | null;
  packageRecords: InboundPackageSummary[];
  receivingLabels: ReceivingLabelSummary[];
  observedCodes: ObservedReceivingCode[];
  activeReceivingPackage: InboundPackageSummary | null;
  shouldCaptureHandlingUnitCount: boolean;
  handlingUnitCount: string;
  printableLabelCount: number;
  draftCodeValue: string;
  draftCodeType: string;
  isPackageClosed: (pkg: InboundPackageSummary) => boolean;
  packageLookupCode: (pkg: InboundPackageSummary) => string;
  applyActivePackage: (payload: ScannedReceivingLabel) => void;
  apiErrorText: (error: any, fallback: string) => string;
  offlineQueuedText: () => string;
  resetPackageEditor: () => void;
  resetReceiptCorrection: () => void;
  setStep: (step: ReceivingStep) => void;
  setReceivedLines: Dispatch<SetStateAction<ReceivedLine[]>>;
  setScannedLabel: (label: ScannedReceivingLabel | null) => void;
  setMobileReceiptFocus: (focus: MobileReceiptFocus) => void;
  setScanError: (value: string) => void;
  setLastAttemptedScanCode: (value: string) => void;
  setPrintError: (value: string) => void;
  setReceiptError: (value: string) => void;
  setReceiptOfflineNotice: (value: string) => void;
  setLastConfirmedLabelCode: (value: string) => void;
  setLastConfirmedExternalCount: (value: number) => void;
  setLastPrintedLabelCount: (value: number) => void;
  setCurrentQty: (value: string) => void;
  setDamagedQty: (value: string) => void;
  setHandlingUnitCount: (value: string) => void;
  setHandlingUnitSplitError: (value: string) => void;
  setPackageCount: (value: string) => void;
  setPalletCount: (value: string) => void;
  setRentFreeDays: (value: string) => void;
  setMeasuredWeightKg: (value: string) => void;
  setMeasuredLengthCm: (value: string) => void;
  setMeasuredWidthCm: (value: string) => void;
  setMeasuredHeightCm: (value: string) => void;
  setReceivingNote: (value: string) => void;
  setMeasurementDefaultsKey: (value: string) => void;
  setDraftCodeValue: (value: string) => void;
  setDraftCodeType: (value: string) => void;
  setEditingCodeId: (value: string | null) => void;
  setPackageEditorError: (value: string) => void;
  setCorrectionError: (value: string) => void;
}

export function useReceivingMutations(ctx: ReceivingMutationsContext) {
  const {
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
    setPackageEditorError,
    setCorrectionError,
  } = ctx;
  const queryClient = useQueryClient();

  // Start receiving
  const startMutation = useMutation({
    mutationFn: (id: string) =>
      requestWithOutbox<any>({
        url: `/receiving/inbound/${id}/start-receiving`,
        scope: "receiving.start",
        description: `Start receiving ${id}`,
      }),
    onSuccess: () => setStep("scan"),
  });

  // Receive line
  const receiveMutation = useMutation({
    mutationFn: (data: any) => {
      if (scannedLabel?.package_id) {
        return requestWithOutbox<any>({
          url: `/receiving/inbound/${orderId}/packages/${scannedLabel.package_id}/receive`,
          data,
          scope: "receiving.package.receive",
          description: `Receive package ${scannedLabel.package_id}`,
        });
      }
      return requestWithOutbox<any>({
        url: `/receiving/inbound/${orderId}/receive-label`,
        data,
        scope: "receiving.label.receive",
        description: `Receive label for inbound ${orderId}`,
      });
    },
    onSuccess: (resp) => {
      const closedLabelCode = resp.data?.label_code as string | undefined;
      const closedPackageId = resp.data?.package_id as string | undefined;
      const capturedCodes = Array.isArray(resp.data?.captured_codes) ? resp.data.captured_codes : [];
      const nextPendingPackage = packageRecords.find(
        (pkg) => pkg.id !== closedPackageId && !isPackageClosed(pkg) && !!packageLookupCode(pkg),
      );
      const nextPendingLabel = receivingLabels.find(
        (label) => label.label_code !== closedLabelCode && label.status !== "received",
      );
      setReceivedLines((prev) => [...prev, resp.data]);
      setLastConfirmedLabelCode(closedLabelCode || "");
      setLastConfirmedExternalCount(capturedCodes.length);
      setLastPrintedLabelCount(0);
      setScannedLabel(null);
      setMobileReceiptFocus("scan");
      setScanError("");
      setReceiptError("");
      setReceiptOfflineNotice("");
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.labels(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.observedCodes(orderId, closedLabelCode) });
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

      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });

      if (nextPendingPackage) {
        scanLabelMutation.mutate({ labelCode: packageLookupCode(nextPendingPackage), source: "manual" });
      } else if (nextPendingLabel) {
        scanLabelMutation.mutate({ labelCode: nextPendingLabel.label_code, source: "manual" });
      }
    },
    onError: (error: any) => {
      if (isOfflineMutationQueuedError(error)) {
        setScannedLabel(null);
        setMobileReceiptFocus("scan");
        setScanError("");
        setReceiptError("");
        setReceiptOfflineNotice(offlineQueuedText());
        setCurrentQty("1");
        setDamagedQty("0");
        return;
      }
      setReceiptOfflineNotice("");
      setReceiptError(
        apiErrorText(
          error,
          t("receivingFlow.receiveError", "The system could not confirm this label receipt. Please review the quantities and try again."),
        ),
      );
    },
  });

  const scanLabelMutation = useMutation({
    mutationFn: ({ labelCode, source }: { labelCode: string; source?: "scan" | "photo" | "manual" }) =>
      scanReceivingLabel(orderId, { label_code: labelCode, source: source || "scan" }),
    onSuccess: (resp) => {
      const matchedLabel = resp.data as ScannedReceivingLabel;
      setLastAttemptedScanCode("");
      applyActivePackage(matchedLabel);
    },
    onError: (error: any) => {
      setScannedLabel(null);
      setScanError(
        apiErrorText(
          error,
          t("receivingFlow.scanNotMatched", "This scanned code does not match the current inbound order."),
        ),
      );
    },
  });

  const openPackageMutation = useMutation({
    mutationFn: (packageId: string) => openReceivingPackage(orderId, packageId),
    onSuccess: (resp) => {
      applyActivePackage(resp.data as ScannedReceivingLabel);
    },
    onError: (error: any) => {
      setPackageEditorError(
        apiErrorText(
          error,
          t("receivingFlow.packageOpenError", "The package could not be opened right now. Please try again."),
        ),
      );
    },
  });

  const addObservedCodeMutation = useMutation({
    mutationFn: async () => {
      if (!scannedLabel) throw new Error("No active receiving label");
      return addCapturedReceivingCode(orderId, {
        label_code: scannedLabel.label_code,
        package_id: scannedLabel.package_id,
        code_value: draftCodeValue,
        code_type: draftCodeType,
        source: "manual",
        is_primary: observedCodes.length === 0,
      });
    },
    onSuccess: () => {
      setDraftCodeValue("");
      setDraftCodeType("other");
      queryClient.invalidateQueries({
        queryKey: queryKeys.receiving.observedCodes(orderId, scannedLabel?.package_id || scannedLabel?.label_code),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
    },
  });

  const updateObservedCodeMutation = useMutation({
    mutationFn: async ({ codeId, codeValue, codeType, isPrimary }: { codeId: string; codeValue: string; codeType: string; isPrimary: boolean }) =>
      updateCapturedReceivingCode(orderId, codeId, {
        code_value: codeValue,
        code_type: codeType,
        is_primary: isPrimary,
      }),
    onSuccess: () => {
      setDraftCodeValue("");
      setDraftCodeType("other");
      setEditingCodeId(null);
      queryClient.invalidateQueries({
        queryKey: queryKeys.receiving.observedCodes(orderId, scannedLabel?.package_id || scannedLabel?.label_code),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
    },
  });

  const deleteObservedCodeMutation = useMutation({
    mutationFn: async (codeId: string) => deleteCapturedReceivingCode(orderId, codeId),
    onSuccess: () => {
      setDraftCodeValue("");
      setDraftCodeType("other");
      setEditingCodeId(null);
      queryClient.invalidateQueries({
        queryKey: queryKeys.receiving.observedCodes(orderId, scannedLabel?.package_id || scannedLabel?.label_code),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
    },
  });

  const createPackageMutation = useMutation({
    mutationFn: (payload: {
      line_id: string;
      expected_qty: number;
      package_type: string;
      external_tracking_number?: string;
      external_carton_mark?: string;
      external_customer_barcode?: string;
    }) => createReceivingPackage(orderId, payload),
    onSuccess: async (created) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
      resetPackageEditor();
      await openPackageMutation.mutateAsync(created.id);
    },
    onError: (error: any) => {
      setPackageEditorError(
        apiErrorText(
          error,
          t("receivingFlow.packageSaveError", "The package could not be saved. Please review the values and try again."),
        ),
      );
    },
  });

  const updatePackageMutation = useMutation({
    mutationFn: (payload: {
      package_id: string;
      expected_qty: number;
      package_type: string;
      external_tracking_number?: string;
      external_carton_mark?: string;
      external_customer_barcode?: string;
    }) =>
      updateReceivingPackage(orderId, payload.package_id, {
        expected_qty: payload.expected_qty,
        package_type: payload.package_type,
        external_tracking_number: payload.external_tracking_number,
        external_carton_mark: payload.external_carton_mark,
        external_customer_barcode: payload.external_customer_barcode,
      }).then((r) => r.data as { id: string }),
    onSuccess: async (updated) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
      resetPackageEditor();
      if (scannedLabel?.package_id === updated.id) {
        await openPackageMutation.mutateAsync(updated.id);
      }
    },
    onError: (error: any) => {
      setPackageEditorError(
        apiErrorText(
          error,
          t("receivingFlow.packageSaveError", "The package could not be saved. Please review the values and try again."),
        ),
      );
    },
  });

  const splitHandlingUnitsMutation = useMutation({
    mutationFn: async () => {
      if (!activeReceivingPackage || !shouldCaptureHandlingUnitCount) {
        throw new Error(
          t("receivingFlow.handlingUnitSplitUnavailable", "Open a carton or crate package before splitting handling units."),
        );
      }
      const unitCount = Math.floor(Number(handlingUnitCount));
      const totalQty = Number(activeReceivingPackage.expected_qty || scannedLabel?.expected_qty || 0);
      if (!Number.isInteger(unitCount) || unitCount <= 1) {
        throw new Error(
          t("receivingFlow.handlingUnitSplitCountRequired", "Enter more than one handling unit before splitting."),
        );
      }
      if (!Number.isFinite(totalQty) || totalQty < unitCount) {
        throw new Error(
          t(
            "receivingFlow.handlingUnitSplitTooMany",
            "Automatic split needs at least one expected SKU unit per handling unit.",
          ),
        );
      }
      const quantities = splitQuantityAcrossUnits(totalQty, unitCount);
      if (quantities.some((qty) => qty <= 0)) {
        throw new Error(
          t(
            "receivingFlow.handlingUnitSplitTooMany",
            "Automatic split needs at least one expected SKU unit per handling unit.",
          ),
        );
      }

      await updateReceivingPackage(orderId, activeReceivingPackage.id, {
        expected_qty: quantities[0],
        package_type: activeReceivingPackage.package_type,
        external_tracking_number: activeReceivingPackage.external_tracking_number || undefined,
        external_carton_mark: activeReceivingPackage.external_carton_mark || undefined,
        external_customer_barcode: activeReceivingPackage.external_customer_barcode || undefined,
      });

      for (const expectedQty of quantities.slice(1)) {
        await createReceivingPackage(orderId, {
          line_id: activeReceivingPackage.order_line_id,
          expected_qty: expectedQty,
          package_type: activeReceivingPackage.package_type,
        });
      }

      return { packageId: activeReceivingPackage.id, firstQty: quantities[0], createdCount: quantities.length - 1 };
    },
    onSuccess: async ({ packageId, firstQty }) => {
      setHandlingUnitCount("1");
      setHandlingUnitSplitError("");
      setCurrentQty(String(firstQty));
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
      await openPackageMutation.mutateAsync(packageId);
      setReceiptError("");
    },
    onError: (error: any) => {
      setHandlingUnitSplitError(
        apiErrorText(
          error,
          t("receivingFlow.handlingUnitSplitError", "The package could not be split right now."),
        ),
      );
    },
  });

  const correctPackageMutation = useMutation({
    mutationFn: (payload: {
      package_id: string;
      quantity_received: number;
      quantity_damaged: number;
      staging_location_id?: string;
      package_count?: number;
      pallet_count?: number;
      rent_free_days?: number;
      measured_weight_kg?: number;
      measured_length_cm?: number;
      measured_width_cm?: number;
      measured_height_cm?: number;
      receiving_note?: string;
      external_tracking_number?: string;
      external_carton_mark?: string;
      external_customer_barcode?: string;
    }) =>
      correctReceivingPackage(orderId, payload.package_id, {
        quantity_received: payload.quantity_received,
        quantity_damaged: payload.quantity_damaged,
        staging_location_id: payload.staging_location_id,
        package_count: payload.package_count,
        pallet_count: payload.pallet_count,
        rent_free_days: payload.rent_free_days,
        measured_weight_kg: payload.measured_weight_kg,
        measured_length_cm: payload.measured_length_cm,
        measured_width_cm: payload.measured_width_cm,
        measured_height_cm: payload.measured_height_cm,
        receiving_note: payload.receiving_note,
        external_tracking_number: payload.external_tracking_number,
        external_carton_mark: payload.external_carton_mark,
        external_customer_barcode: payload.external_customer_barcode,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.labels(orderId) });
      resetReceiptCorrection();
    },
    onError: (error: any) => {
      setCorrectionError(
        apiErrorText(
          error,
          t("receivingFlow.correctionSaveError", "The receipt correction could not be saved."),
        ),
      );
    },
  });

  const deletePackageMutation = useMutation({
    mutationFn: (packageId: string) => deleteReceivingPackage(orderId, packageId),
    onSuccess: (_data, packageId) => {
      if (scannedLabel?.package_id === packageId) {
        setScannedLabel(null);
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.packages(orderId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
      setPackageEditorError("");
    },
    onError: (error: any) => {
      setPackageEditorError(
        apiErrorText(
          error,
          t("receivingFlow.packageDeleteError", "The package could not be removed right now."),
        ),
      );
    },
  });

  // Complete receiving
  const completeMutation = useMutation({
    mutationFn: () =>
      requestWithOutbox<CompleteReceivingSummary>({
        url: `/receiving/inbound/${orderId}/complete`,
        scope: "receiving.complete",
        description: `Complete receiving ${orderId}`,
      }),
    onSuccess: () => {
      setStep("done");
      window.sessionStorage.removeItem("receiving.lastActiveOrder");
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.receivable() });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.putaway() });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventory.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventory.summary() });
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.receiving });
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.putaway });
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.inventory });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.inventoryPending() });
    },
  });

  const markPrintedMutation = useMutation({
    mutationFn: (labelCodes?: string[]) =>
      markReceivingLabelsPrinted(orderId, {
        label_codes: labelCodes?.length ? labelCodes : undefined,
      }),
    onSuccess: (_data, labelCodes) => {
      setPrintError("");
      const count = Array.isArray(labelCodes) ? labelCodes.length : printableLabelCount;
      setLastPrintedLabelCount(count);
      queryClient.invalidateQueries({ queryKey: queryKeys.receiving.labels(orderId) });
    },
    onError: (error: any) => {
      setPrintError(
        apiErrorText(
          error,
          t("receivingFlow.printError", "The system could not record this label print. Please try again."),
        ),
      );
    },
  });

  return {
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
  };
}
