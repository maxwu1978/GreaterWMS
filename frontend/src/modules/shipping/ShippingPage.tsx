import { useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, ArrowRight } from "lucide-react";
import { queryKeys } from "../../shared/api/queryKeys";
import { fetchClients } from "../../shared/api/clients";
import { fetchOutboundOrderDetail, fetchPackingSlipPdf } from "../../shared/api/outboundOrders";
import { fetchSetupProgress } from "../../shared/api/setup";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { requestWithOutbox } from "../../shared/offline/mutations";
import { isOfflineMutationQueuedError } from "../../shared/offline/outbox";
import {
  fetchOutboundOrderListPage,
  ORDER_LIST_BATCH_SIZE,
} from "../../shared/api/orderLists";
import DataTable from "../../shared/components/DataTable";
import ActionButton from "../../shared/components/ActionButton";
import Eyebrow from "../../shared/components/Eyebrow";
import StatusBadge from "../../shared/components/StatusBadge";
import TaskCard from "../../shared/components/TaskCard";
import { type MobileFlowStepItem } from "../../shared/components/MobileFlowGuide";
import WorkflowRecoveryPanel from "../../shared/components/WorkflowRecoveryPanel";
import BarcodeScanner from "../../scanner/BarcodeScanner";
import { useI18n } from "../../shared/i18n";
import UpstreamActionLink from "../../shared/components/UpstreamActionLink";
import { checklistHref } from "../../shared/utils/checklistHref";

type PackingDraft = {
  quantity: number;
  skuConfirmed: boolean;
};

type PackingScanIssue = "already_confirmed" | "not_in_order" | "no_picked_qty" | null;
type RecoveryAction =
  | "scanNextSku"
  | "resetPackCheck"
  | "finishPickingFirst"
  | "enterTracking"
  | "backToShippingList"
  | "refreshOrder";
type RecoveryPrompt = {
  tone: "warning" | "error" | "info";
  title: string;
  body: string;
  actionLabel: string;
  action: RecoveryAction;
};

export default function ShippingPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedOrder, setSelectedOrder] = useState<any>(null);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [carrierDraft, setCarrierDraft] = useState("");
  const [trackingDraft, setTrackingDraft] = useState("");
  const [serviceLevelDraft, setServiceLevelDraft] = useState("");
  const [shippingCostDraft, setShippingCostDraft] = useState("");
  const [packingDrafts, setPackingDrafts] = useState<Record<string, PackingDraft>>({});
  const [packingScanError, setPackingScanError] = useState<string | null>(null);
  const [packingScanFeedback, setPackingScanFeedback] = useState<string | null>(null);
  const [trackingScanFeedback, setTrackingScanFeedback] = useState<string | null>(null);
  const [shippingSortField, setShippingSortField] = useState("order_number");
  const [shippingSortDirection, setShippingSortDirection] = useState<"asc" | "desc">("desc");
  const [packingScanIssue, setPackingScanIssue] = useState<PackingScanIssue>(null);
  const [apiRecoveryPrompt, setApiRecoveryPrompt] = useState<RecoveryPrompt | null>(null);
  const [mobileHandoffReview, setMobileHandoffReview] = useState(false);
  const mobileCarrierInputRef = useRef<HTMLInputElement | null>(null);
  const mobileTrackingInputRef = useRef<HTMLInputElement | null>(null);
  const desktopCarrierInputRef = useRef<HTMLInputElement | null>(null);
  const desktopTrackingInputRef = useRef<HTMLInputElement | null>(null);
  const shippingOrderStatuses = ["picked", "packing", "packed"];
  const offlineQueuedText = () =>
    t("offline.mutationQueued", "Saved offline. It will sync automatically when the connection is back.");
  const serverShippingSortField = ["order_number", "status", "shipping_readiness", "client_id", "carrier", "tracking_number"].includes(shippingSortField)
    ? shippingSortField
    : "created_at";

  const {
    data: orderPages,
    isLoading,
    fetchNextPage: fetchNextOrderBatch,
    hasNextPage: hasMoreOrderBatches,
    isFetchingNextPage: isFetchingNextOrderBatch,
  } = useInfiniteQuery({
    queryKey: queryKeys.shipping.orders({ statuses: shippingOrderStatuses.join(","), sortBy: serverShippingSortField, sortDirection: shippingSortDirection }),
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      fetchOutboundOrderListPage({
        offset: Number(pageParam || 0),
        limit: ORDER_LIST_BATCH_SIZE,
        statuses: shippingOrderStatuses,
        sortBy: serverShippingSortField,
        sortDirection: shippingSortDirection,
      }),
    getNextPageParam: (lastPage) => lastPage.nextOffset,
  });
  const orderRows = useMemo(
    () => orderPages?.pages.flatMap((page) => page.items) || [],
    [orderPages],
  );
  const orders = useMemo(
    () => orderRows.filter((row: any) => ["picked", "packing", "packed"].includes(row.status)),
    [orderRows]
  );
  const pickedOrders = useMemo(() => orders.filter((row: any) => row.status === "picked").length, [orders]);
  const packingOrders = useMemo(() => orders.filter((row: any) => row.status === "packing").length, [orders]);
  const packedOrders = useMemo(() => orders.filter((row: any) => row.status === "packed").length, [orders]);

  const { data: setupProgress } = useQuery({
    queryKey: queryKeys.setup.progressFor("shipping"),
    queryFn: fetchSetupProgress,
  });
  const { data: clientsData } = useQuery({
    queryKey: queryKeys.clients.list("shipping"),
    queryFn: () => fetchClients(),
  });
  const { data: selectedOrderDetail, isLoading: detailLoading } = useQuery({
    queryKey: queryKeys.shipping.orderDetail(selectedOrder?.id),
    enabled: !!selectedOrder?.id,
    queryFn: () => fetchOutboundOrderDetail(selectedOrder.id),
  });

  const setupSteps = setupProgress?.steps || [];
  const missingRequiredSteps = useMemo(
    () => setupSteps.filter((step: any) => ["warehouse", "locations", "client", "skus"].includes(step.name) && !step.done),
    [setupSteps]
  );
  const shippingReady = missingRequiredSteps.length === 0;
  const clients = clientsData?.items || [];
  const clientMap = useMemo(
    () => new Map(clients.map((client: any) => [client.id, `${client.code ? `${client.code} · ` : ""}${client.name}`])),
    [clients]
  );

  useEffect(() => {
    if (!selectedOrderDetail) return;
    setCarrierDraft(selectedOrderDetail.carrier || "");
    setTrackingDraft(selectedOrderDetail.tracking_number || "");
    setServiceLevelDraft(selectedOrderDetail.service_level || "");
    setShippingCostDraft(
      selectedOrderDetail.shipping_cost !== null && selectedOrderDetail.shipping_cost !== undefined
        ? String(selectedOrderDetail.shipping_cost)
        : ""
    );
    setPackingDrafts({});
    setPackingScanError(null);
    setPackingScanFeedback(null);
    setTrackingScanFeedback(null);
    setFeedback(null);
    setPackingScanIssue(null);
    setApiRecoveryPrompt(null);
    setMobileHandoffReview(false);
  }, [selectedOrderDetail?.id]);

  const refreshShippingViews = async (orderId?: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.shipping.orders() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.shipping.orderDetail(orderId || selectedOrder?.id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.list() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.pick() }),
    ]);
    await Promise.all([
      queryClient.refetchQueries({ queryKey: queryKeys.shipping.orders() }),
      orderId || selectedOrder?.id
        ? queryClient.refetchQueries({ queryKey: queryKeys.shipping.orderDetail(orderId || selectedOrder?.id) })
        : Promise.resolve(),
    ]);
  };

  const removeShippedOrderFromWorkbench = (orderId?: string) => {
    if (!orderId) return;
    queryClient.setQueriesData({ queryKey: queryKeys.shipping.orders() }, (current: any) => {
      if (Array.isArray(current)) {
        return current.filter((order: any) => order.id !== orderId);
      }
      if (current?.pages) {
        return {
          ...current,
          pages: current.pages.map((page: any) => ({
            ...page,
            items: Array.isArray(page.items)
              ? page.items.filter((order: any) => order.id !== orderId)
              : page.items,
          })),
        };
      }
      return current;
    });
    queryClient.removeQueries({ queryKey: queryKeys.shipping.orderDetail(orderId) });
  };

  const resetPackCheck = () => {
    setPackingDrafts({});
    setPackingScanError(null);
    setPackingScanFeedback(null);
    setPackingScanIssue(null);
    setApiRecoveryPrompt(null);
  };

  const getErrorText = (error: any, fallback: string) => {
    if (!error?.response && error?.message) return error.message;
    return getApiErrorMessage(error, fallback);
  };

  const apiFailureRecovery = (error: any, phase: "pack" | "ship"): RecoveryPrompt => {
    const detail = getErrorText(
      error,
      phase === "pack"
        ? t("shipping.packError", "Packing confirmation failed.")
        : t("shipping.shipError", "Shipment confirmation failed.")
    );
    const lowerDetail = detail.toLowerCase();
    const status = error?.response?.status;
    const currentStatusMatch = lowerDetail.match(/currently\s+([a-z_]+)/);
    const currentApiStatus = currentStatusMatch?.[1] || "";

    if (phase === "ship" && (lowerDetail.includes("carrier") || lowerDetail.includes("tracking"))) {
      return {
        tone: "warning",
        title: t("shipping.recoveryTrackingTitle", "Carrier handoff is missing tracking details"),
        body: detail,
        actionLabel: t("shipping.recoveryEnterCarrierTrackingAction", "Enter carrier or tracking"),
        action: "enterTracking",
      };
    }

    if (phase === "pack" && lowerDetail.includes("scan or select each picked sku")) {
      return {
        tone: "info",
        title: t("shipping.recoveryContinuePackTitle", "Continue the pack check"),
        body: detail,
        actionLabel: t("shipping.recoveryScanNextSkuAction", "Scan next SKU"),
        action: "scanNextSku",
      };
    }

    if (phase === "pack" && lowerDetail.includes("packed quantity must match")) {
      return {
        tone: "warning",
        title: t("shipping.recoveryQuantityMismatchTitle", "Packed quantity does not match picked work"),
        body: detail,
        actionLabel: t("shipping.recoveryResetPackAction", "Reset pack check"),
        action: "resetPackCheck",
      };
    }

    if (status === 409 || lowerDetail.includes("currently")) {
      if (["pending", "allocated", "picking"].includes(currentApiStatus) || (!currentApiStatus && (lowerDetail.includes("picking") || lowerDetail.includes("allocated")))) {
        return {
          tone: "warning",
          title: t("shipping.recoveryFinishPickingTitle", "This order is not ready for shipping"),
          body: detail,
          actionLabel: t("shipping.recoveryFinishPickingAction", "Finish picking first"),
          action: "finishPickingFirst",
        };
      }
      if (currentApiStatus === "shipped" || currentApiStatus.includes("cancel") || (!currentApiStatus && (lowerDetail.includes("shipped") || lowerDetail.includes("cancel")))) {
        return {
          tone: "info",
          title: t("shipping.recoveryOrderLeftQueueTitle", "This order already left the shipping queue"),
          body: detail,
          actionLabel: t("shipping.recoveryBackToListAction", "Back to shipping list"),
          action: "backToShippingList",
        };
      }
      return {
        tone: "warning",
        title: t("shipping.recoveryStaleOrderTitle", "Order state changed"),
        body: detail,
        actionLabel: t("shipping.recoveryRefreshOrderAction", "Refresh order"),
        action: "refreshOrder",
      };
    }

    return {
      tone: "error",
      title: t("shipping.recoveryApiFailureTitle", "Shipping action did not finish"),
      body: detail,
      actionLabel: t("shipping.recoveryRefreshOrderAction", "Refresh order"),
      action: "refreshOrder",
    };
  };

  const packVerifyRecovery = (errors: any[]): RecoveryPrompt => {
    const mismatch = errors.find((entry) => entry?.error === "quantity_mismatch");
    const unknownSku = errors.find((entry) => entry?.error === "not_in_order");
    if (mismatch) {
      const line = (selectedOrderDetail?.lines || []).find((entry: any) => entry.sku_id === mismatch.sku_id);
      return {
        tone: "warning",
        title: t("shipping.recoveryQuantityMismatchTitle", "Packed quantity does not match picked work"),
        body: t(
          "shipping.recoveryQuantityMismatchBody",
          "{sku} expected {expected} picked but packing sent {scanned}. Reset the pack check and scan the order again.",
          {
            sku: line?.sku_code || mismatch.sku_id || t("common.sku", "SKU"),
            expected: String(mismatch.expected ?? "0"),
            scanned: String(mismatch.scanned ?? "0"),
          }
        ),
        actionLabel: t("shipping.recoveryResetPackAction", "Reset pack check"),
        action: "resetPackCheck",
      };
    }
    return {
      tone: "warning",
      title: unknownSku
        ? t("shipping.recoveryWrongSkuTitle", "A packed SKU is not on this order")
        : t("shipping.recoveryPackVerifyFailedTitle", "Pack check needs another pass"),
      body: t("shipping.recoveryPackVerifyFailedBody", "Reset the pack check, compare the box to the order lines, then scan the picked SKUs again."),
      actionLabel: t("shipping.recoveryResetPackAction", "Reset pack check"),
      action: "resetPackCheck",
    };
  };

  const packMutation = useMutation({
    mutationFn: async () => {
      if (!selectedOrderDetail?.id) throw new Error("No order selected");
      const orderLines = selectedOrderDetail.lines || [];
      const unconfirmedLine = orderLines.find(
        (line: any) => Number(line.quantity_picked || 0) > 0 && !packingDrafts[line.sku_id]?.skuConfirmed
      );
      if (unconfirmedLine) {
        throw new Error(
          t("shipping.packScanIncomplete", "Scan or select each picked SKU once before confirming packing.")
        );
      }
      const quantityMismatchLine = orderLines.find(
        (line: any) => Number(packingDrafts[line.sku_id]?.quantity ?? line.quantity_picked ?? 0) !== Number(line.quantity_picked || 0)
      );
      if (quantityMismatchLine) {
        throw new Error(
          t("shipping.packQuantityMismatch", "Packed quantity must match the picked quantity before confirming packing.")
        );
      }
      const scannedItems = orderLines.map((line: any) => ({
        sku_id: line.sku_id,
        quantity: Number(packingDrafts[line.sku_id]?.quantity ?? line.quantity_picked ?? 0),
      }));
      return requestWithOutbox<any>({
        url: "/fulfillment/pack/verify",
        scope: "shipping.pack",
        description: `Confirm packing ${selectedOrderDetail.id}`,
        data: {
          order_id: selectedOrderDetail.id,
          scanned_items: scannedItems,
        },
      });
    },
    onSuccess: async (response) => {
      const result = response?.data || {};
      if (result.verified === false) {
        const errors = Array.isArray(result.errors) ? result.errors : [];
        const recovery = packVerifyRecovery(errors);
        setFeedback({ tone: "error", text: recovery.body });
        setApiRecoveryPrompt(recovery);
        return;
      }
      setFeedback({
        tone: "success",
        text: t(
          "shipping.packSuccess",
          "Packing confirmed. Next: capture carrier and tracking for handoff.",
        ),
      });
      setPackingDrafts({});
      setPackingScanError(null);
      setPackingScanFeedback(null);
      setPackingScanIssue(null);
      setApiRecoveryPrompt(null);
      setMobileHandoffReview(false);
      await refreshShippingViews(selectedOrderDetail?.id);
    },
    onError: (error: any) => {
      if (isOfflineMutationQueuedError(error)) {
        setFeedback({ tone: "success", text: offlineQueuedText() });
        setApiRecoveryPrompt(null);
        return;
      }
      const recovery = apiFailureRecovery(error, "pack");
      setFeedback({ tone: "error", text: recovery.body });
      setApiRecoveryPrompt(recovery);
    },
  });

  const shipMutation = useMutation({
    mutationFn: async () => {
      if (!selectedOrderDetail?.id) throw new Error("No order selected");
      if (!carrierDraft.trim()) throw new Error(t("shipping.enterCarrier", "Enter a carrier before shipping."));
      if (!trackingDraft.trim()) throw new Error(t("shipping.enterTracking", "Enter a tracking number before shipping."));
      return requestWithOutbox<any>({
        url: "/fulfillment/ship/confirm",
        scope: "shipping.ship",
        description: `Confirm shipment ${selectedOrderDetail.id}`,
        data: {
          order_id: selectedOrderDetail.id,
          carrier: carrierDraft.trim(),
          tracking_number: trackingDraft.trim(),
          service_level: serviceLevelDraft.trim() || null,
          shipping_cost: shippingCostDraft.trim() ? Number(shippingCostDraft) : null,
        },
      });
    },
    onSuccess: async () => {
      const shippedOrderNumber = selectedOrderDetail?.order_number || selectedOrder?.order_number || "";
      const shippedOrderId = selectedOrderDetail?.id || selectedOrder?.id;
      setSelectedOrder(null);
      removeShippedOrderFromWorkbench(shippedOrderId);
      setFeedback({
        tone: "success",
        text: shippedOrderNumber
          ? t("shipping.shipSuccessWithOrder", "{order} shipped. Next: open the next shipping order or return to the dashboard.", { order: shippedOrderNumber })
          : t("shipping.shipSuccess", "Shipment confirmed. Next: open the next shipping order or return to the dashboard."),
      });
      setApiRecoveryPrompt(null);
      setMobileHandoffReview(false);
      await refreshShippingViews(shippedOrderId);
      removeShippedOrderFromWorkbench(shippedOrderId);
    },
    onError: (error: any) => {
      if (isOfflineMutationQueuedError(error)) {
        setFeedback({ tone: "success", text: offlineQueuedText() });
        setApiRecoveryPrompt(null);
        return;
      }
      const recovery = apiFailureRecovery(error, "ship");
      setFeedback({ tone: "error", text: recovery.body });
      setApiRecoveryPrompt(recovery);
    },
  });

  const packingSlipMutation = useMutation({
    mutationFn: async () => {
      if (!selectedOrderDetail?.id) throw new Error("No order selected");
      const orderNumber = selectedOrderDetail.order_number || selectedOrder?.order_number || selectedOrderDetail.id;
      const response = await fetchPackingSlipPdf(selectedOrderDetail.id);
      return { response, orderNumber };
    },
    onSuccess: ({ response, orderNumber }) => {
      const blobUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      const safeOrderNumber = String(orderNumber).replace(/[^a-z0-9_-]/gi, "-");
      link.href = blobUrl;
      link.download = `packing-slip-${safeOrderNumber}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(blobUrl);
      setFeedback({
        tone: "success",
        text: t("shipping.packingSlipDownloaded", "Packing slip downloaded for the selected order."),
      });
    },
    onError: (error: any) => {
      setFeedback({
        tone: "error",
        text: getApiErrorMessage(error, t("shipping.packingSlipError", "Could not download the packing slip PDF.")),
      });
    },
  });

  const selectedStatus = selectedOrderDetail?.status || selectedOrder?.status || "";
  const lines = selectedOrderDetail?.lines || [];
  const packReady = lines.length > 0 && lines.every((line: any) => line.quantity_picked === line.quantity_ordered);
  const isPacked = selectedStatus === "packed";
  const totalPickedToPack = lines.reduce((sum: number, line: any) => sum + Number(line.quantity_picked || 0), 0);
  const packCheckLineTotal = lines.filter((line: any) => Number(line.quantity_picked || 0) > 0).length;
  const packCheckConfirmedLines = isPacked
    ? packCheckLineTotal
    : lines.filter((line: any) => Number(line.quantity_picked || 0) > 0 && packingDrafts[line.sku_id]?.skuConfirmed).length;
  const getPackedDraftQuantity = (line: any) =>
    isPacked ? Number(line.quantity_picked || 0) : Number(packingDrafts[line.sku_id]?.quantity ?? line.quantity_picked ?? 0);
  const totalPackedDraft = isPacked
    ? totalPickedToPack
    : lines.reduce((sum: number, line: any) => sum + getPackedDraftQuantity(line), 0);
  const packingLinesRemaining = Math.max(0, packCheckLineTotal - packCheckConfirmedLines);
  const packingQuantityMismatch =
    packReady && lines.some((line: any) => getPackedDraftQuantity(line) !== Number(line.quantity_picked || 0));
  const packingCheckComplete = packReady && packCheckLineTotal > 0 && packingLinesRemaining === 0 && !packingQuantityMismatch;
  const canConfirmPack = ["picked", "packing"].includes(selectedStatus) && packingCheckComplete && !packMutation.isPending;
  const canConfirmShip = isPacked && carrierDraft.trim() && trackingDraft.trim() && !shipMutation.isPending;
  const mobileHandoffCaptureComplete = isPacked && Boolean(carrierDraft.trim()) && Boolean(trackingDraft.trim());
  const recoveryPrompt: RecoveryPrompt | null = apiRecoveryPrompt
    ? apiRecoveryPrompt
    : selectedOrder && !isPacked && !packReady
      ? {
          tone: "warning",
          title: t("shipping.recoveryFinishPickingTitle", "This order is not ready for shipping"),
          body: t("shipping.recoveryFinishPickingBody", "Some lines still have no picked quantity. Finish upstream picking before packing this order."),
          actionLabel: t("shipping.recoveryFinishPickingAction", "Finish picking first"),
          action: "finishPickingFirst",
        }
      : selectedOrder && !isPacked && packingScanIssue === "already_confirmed"
        ? {
            tone: "info",
            title: t("shipping.recoveryAlreadyScannedTitle", "That SKU line is already confirmed"),
            body: t("shipping.recoveryAlreadyScannedBody", "Leave this line checked and continue with the next unconfirmed SKU."),
            actionLabel: t("shipping.recoveryScanNextSkuAction", "Scan next SKU"),
            action: "scanNextSku",
          }
        : selectedOrder && !isPacked && (packingScanIssue === "not_in_order" || packingScanIssue === "no_picked_qty")
          ? {
              tone: "warning",
              title:
                packingScanIssue === "not_in_order"
                  ? t("shipping.recoveryWrongSkuTitle", "A packed SKU is not on this order")
                  : t("shipping.recoveryNoPickedQtyTitle", "This SKU has no picked quantity"),
              body: t("shipping.recoveryWrongSkuBody", "Set the item aside, reset the pack check, and scan only the picked SKUs for this order."),
              actionLabel: t("shipping.recoveryResetPackAction", "Reset pack check"),
              action: "resetPackCheck",
            }
            : selectedOrder && !isPacked && packingQuantityMismatch
              ? {
                  tone: "warning",
                  title: t("shipping.recoveryQuantityMismatchTitle", "Packed quantity does not match picked work"),
                  body: t("shipping.recoveryQuantityMismatchLocalBody", "Packed quantities must match the picked quantities before the order can move to carrier handoff."),
                  actionLabel: t("shipping.recoveryResetPackAction", "Reset pack check"),
                  action: "resetPackCheck",
                }
              : null;
  const packingSuggestedCodes = lines
    .filter((line: any) => Number(line.quantity_picked || 0) > 0 && !packingDrafts[line.sku_id]?.skuConfirmed)
    .map((line: any) => ({
      label: line.sku_code || line.sku_id,
      value: line.sku_barcode || line.sku_code || line.sku_id,
    }));
  const shippingMobileSteps: MobileFlowStepItem[] = [
    {
      key: "pack",
      number: "1",
      label: t("shipping.packStepShort", "Pack check"),
      status: isPacked ? "done" : "active",
    },
    {
      key: "handoff",
      number: "2",
      label: t("shipping.carrierStepShort", "Carrier handoff"),
      status: isPacked ? "active" : "pending",
    },
  ];
  const shippingMobileTitle = !isPacked
    ? t("shipping.mobileStepTitlePack", "Step 1 · Check packed SKUs")
    : mobileHandoffReview
      ? t("shipping.mobileStepTitleCarrierReview", "Step 2 · Confirm carrier handoff")
      : t("shipping.mobileStepTitleCarrierCapture", "Step 2 · Capture carrier and tracking");
  const shippingMobileHint = !isPacked
    ? t("shipping.mobilePackStepHint", "Scan each picked SKU once. Confirm packing appears after every line is checked.")
    : mobileHandoffReview
      ? t("shipping.mobileCarrierReviewHint", "Review the captured carrier truth, then confirm the shipment handoff.")
      : t("shipping.mobileCarrierCaptureHint", "Capture carrier and tracking first. Documents and service details stay in secondary details.");
  const shippingWorkflowSteps = [
    {
      step: "01",
      title: t("shipping.workflowPackTitle", "Pack picked items"),
      body: t("shipping.workflowPackBody", "Start with orders that have completed picking and scan each SKU once before confirming quantities."),
      active: !selectedOrder || selectedStatus === "picked" || selectedStatus === "packing",
    },
    {
      step: "02",
      title: t("shipping.workflowDocumentsTitle", "Prepare documents"),
      body: t("shipping.workflowDocumentsBody", "Download the packing slip from the same order lines before carrier handoff."),
      active: !!selectedOrder,
    },
    {
      step: "03",
      title: t("shipping.workflowCarrierTitle", "Confirm carrier"),
      body: t("shipping.workflowCarrierBody", "Record carrier and tracking once the packed order is ready to leave."),
      active: selectedStatus === "packed",
    },
    {
      step: "04",
      title: t("shipping.workflowCompleteTitle", "Complete shipment"),
      body: t("shipping.workflowCompleteBody", "Confirm shipment so client-facing status and tracking are updated."),
      active: false,
    },
  ];

  const normalizePackingCode = (value: string) => value.trim().toLowerCase().replace(/\s+/g, "");
  const focusPackingScanner = () => {
    if (typeof document === "undefined") return;
    const isDesktop = window.matchMedia("(min-width: 768px)").matches;
    const target =
      (isDesktop
        ? document.getElementById("shipping-pack-scanner-desktop")
        : document.getElementById("shipping-pack-scanner-mobile")) ||
      document.getElementById("shipping-pack-scanner-desktop") ||
      document.getElementById("shipping-pack-scanner-mobile");
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const handleRecoveryAction = async (action: RecoveryAction) => {
    if (action === "scanNextSku") {
      setPackingScanError(null);
      setPackingScanIssue(null);
      setApiRecoveryPrompt(null);
      window.setTimeout(focusPackingScanner, 0);
      return;
    }
    if (action === "resetPackCheck") {
      resetPackCheck();
      return;
    }
    if (action === "finishPickingFirst") {
      window.location.assign("/picking");
      return;
    }
    if (action === "enterTracking") {
      setApiRecoveryPrompt(null);
      const isDesktop = window.matchMedia("(min-width: 768px)").matches;
      if (!carrierDraft.trim()) {
        (isDesktop ? desktopCarrierInputRef.current : mobileCarrierInputRef.current)?.focus();
        return;
      }
      (isDesktop ? desktopTrackingInputRef.current : mobileTrackingInputRef.current)?.focus();
      return;
    }
    if (action === "backToShippingList") {
      const orderId = selectedOrderDetail?.id || selectedOrder?.id;
      setSelectedOrder(null);
      removeShippedOrderFromWorkbench(orderId);
      await refreshShippingViews(orderId);
      return;
    }
    await refreshShippingViews(selectedOrderDetail?.id || selectedOrder?.id);
    setApiRecoveryPrompt(null);
  };

  const handlePackingScan = (code: string) => {
    const normalized = normalizePackingCode(code);
    const matchedLine = lines.find((line: any) =>
      [line.sku_barcode, line.sku_code, line.sku_id]
        .filter(Boolean)
        .some((candidate) => normalizePackingCode(String(candidate)) === normalized)
    );

    if (!matchedLine) {
      setPackingScanError(t("shipping.packScanNotInOrder", "This SKU is not part of the selected outbound order."));
      setPackingScanFeedback(null);
      setPackingScanIssue("not_in_order");
      setApiRecoveryPrompt(null);
      return;
    }

    const targetQty = Number(matchedLine.quantity_picked || 0);
    if (targetQty <= 0) {
      setPackingScanError(t("shipping.packScanNoPickedQty", "This SKU has no picked quantity to pack."));
      setPackingScanFeedback(null);
      setPackingScanIssue("no_picked_qty");
      setApiRecoveryPrompt(null);
      return;
    }
    if (packingDrafts[matchedLine.sku_id]?.skuConfirmed) {
      setPackingScanError(t("shipping.packScanAlreadyComplete", "This SKU line is already confirmed. Adjust the packed quantity if needed."));
      setPackingScanFeedback(null);
      setPackingScanIssue("already_confirmed");
      setApiRecoveryPrompt(null);
      return;
    }

    setPackingDrafts((current) => ({
      ...current,
      [matchedLine.sku_id]: {
        quantity: targetQty,
        skuConfirmed: true,
      },
    }));
    setPackingScanError(null);
    setPackingScanIssue(null);
    setApiRecoveryPrompt(null);
    setPackingScanFeedback(
      t("shipping.packScanLineConfirmed", "{sku} checked. Continue with the next SKU.", {
        sku: matchedLine.sku_code || matchedLine.sku_id,
      })
    );
  };

  const handlePackedQuantityChange = (line: any, value: string) => {
    const parsed = value === "" ? 0 : Math.max(0, Math.floor(Number(value) || 0));
    setApiRecoveryPrompt(null);
    setPackingDrafts((current) => ({
      ...current,
      [line.sku_id]: {
        quantity: parsed,
        skuConfirmed: Boolean(current[line.sku_id]?.skuConfirmed),
      },
    }));
  };

  const handleTrackingScan = (code: string) => {
    const normalized = code.trim();
    if (!normalized) return;
    setTrackingDraft(normalized);
    setApiRecoveryPrompt(null);
    setMobileHandoffReview(false);
    setTrackingScanFeedback(t("shipping.trackingScanCaptured", "Tracking captured from scan."));
  };

  const continueMobileHandoff = () => {
    if (!carrierDraft.trim()) {
      mobileCarrierInputRef.current?.focus();
      return;
    }
    if (!trackingDraft.trim()) {
      mobileTrackingInputRef.current?.focus();
      return;
    }
    setMobileHandoffReview(true);
  };

  const shippingReadinessContent = (row: any) => {
    const hasCarrier = Boolean(String(row.carrier || "").trim());
    const hasTracking = Boolean(String(row.tracking_number || "").trim());
    const config =
      row.status === "packed" && hasCarrier && hasTracking
        ? {
            label: t("shipping.readinessReadyToShip", "Ready to ship"),
            meta: t("shipping.readinessReadyToShipMeta", "Carrier and tracking set"),
            className: "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]",
          }
        : row.status === "packed"
          ? {
              label: t("shipping.readinessCarrierNeeded", "Carrier info needed"),
              meta: t("shipping.readinessCarrierNeededMeta", "Add carrier and tracking"),
              className: "border-[#e6c06a]/55 bg-[#fff8e8] text-[#8a5b00]",
            }
          : row.status === "packing"
            ? {
                label: t("shipping.readinessPacking", "Packing in progress"),
                meta: t("shipping.readinessPackingMeta", "Finish pack verification"),
                className: "border-[#8db6ff]/45 bg-[#eef5ff] text-[#245da8]",
              }
            : {
                label: t("shipping.readinessReadyToPack", "Ready to pack"),
                meta: t("shipping.readinessReadyToPackMeta", "Picked work complete"),
                className: "border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d]",
              };

    return (
      <div className="flex flex-col gap-1">
        <span
          className={`inline-flex w-fit items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] ${config.className}`}
        >
          {config.label}
        </span>
        <span className="text-[11px] leading-4 text-[#7f8d98]">{config.meta}</span>
      </div>
    );
  };

  const compareRows = (
    left: { row: any; index: number },
    right: { row: any; index: number },
    getComparable: (row: any) => string | number,
    direction: "asc" | "desc"
  ) => {
    const modifier = direction === "asc" ? 1 : -1;
    const leftValue = getComparable(left.row);
    const rightValue = getComparable(right.row);
    if (typeof leftValue === "number" || typeof rightValue === "number") {
      const delta = Number(leftValue || 0) - Number(rightValue || 0);
      return delta === 0 ? left.index - right.index : delta * modifier;
    }
    const delta = String(leftValue || "").localeCompare(String(rightValue || ""), undefined, {
      numeric: true,
      sensitivity: "base",
    });
    return delta === 0 ? left.index - right.index : delta * modifier;
  };

  const shippingReadinessSortRank = (row: any) => {
    if (row.status === "packed" && row.carrier && row.tracking_number) return 10;
    if (row.status === "packed") return 20;
    if (row.status === "packing") return 30;
    if (row.status === "picked") return 40;
    return 90;
  };

  const getShippingComparable = (row: any) => {
    if (shippingSortField === "client_id") return clientMap.get(row.client_id) || row.client_id || "";
    if (shippingSortField === "shipping_readiness") return shippingReadinessSortRank(row);
    return row?.[shippingSortField] ?? "";
  };

  const sortedOrders = useMemo(
    () =>
      orders
        .map((row: any, index: number) => ({ row, index }))
        .sort((left, right) => compareRows(left, right, getShippingComparable, shippingSortDirection))
        .map(({ row }) => row),
    [orders, shippingSortField, shippingSortDirection, clientMap]
  );

  const handleShippingHeaderClick = (key: string) => {
    if (!["order_number", "status", "shipping_readiness", "client_id", "carrier", "tracking_number"].includes(key)) return;
    if (shippingSortField === key) {
      setShippingSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setShippingSortField(key);
    setShippingSortDirection("asc");
  };

  const mobileShippingActionLabel = (order: any) => {
    if (order.status === "picked") return t("shipping.packWorkTitle", "Confirm packed SKUs and quantities");
    if (order.status === "packing") return t("shipping.workflowPackTitle", "Pack picked items");
    if (order.status === "packed") return t("shipping.shipStepTitle", "Confirm carrier handoff and tracking");
    return t("shipping.reviewOrder", "Review order");
  };
  const shippingMobilePath =
    ["picked", "packing"].includes(sortedOrders[0]?.status || "")
      ? "pack"
      : sortedOrders[0]?.status === "packed"
        ? "handoff"
        : sortedOrders[0]
          ? "exception"
          : "pack";

  const columns = [
    {
      key: "__row_number",
      header: t("common.rowNumber", "No."),
      className: "w-[72px] text-[#7f8d98]",
      render: (_row: any, index: number) => index + 1,
    },
    { key: "order_number", header: t("common.orderNumber", "Order #"), sortable: true },
    {
      key: "status",
      header: t("common.status", "Status"),
      sortable: true,
      render: (row: any) => <StatusBadge status={row.status} />,
    },
    {
      key: "shipping_readiness",
      header: t("shipping.shippingReadiness", "Shipping readiness"),
      sortable: true,
      render: shippingReadinessContent,
    },
    {
      key: "client_id",
      header: t("common.client", "Client"),
      sortable: true,
      render: (row: any) => clientMap.get(row.client_id) || row.client_id,
    },
    { key: "carrier", header: t("shipping.carrier", "Carrier"), sortable: true },
    { key: "tracking_number", header: t("shipping.trackingNumber", "Tracking #"), sortable: true },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Eyebrow className="text-xs tracking-[0.24em]">{t("shipping.eyebrow", "Dispatch control")}</Eyebrow>
          <h1 className="mt-2 text-2xl font-semibold text-[#13212c] md:text-3xl md:tracking-[-0.04em]">{t("shipping.title", "Shipping")}</h1>
        </div>
        <div className="hidden shrink-0 flex-wrap items-center gap-3 md:flex">
          <UpstreamActionLink to="/picking" label={t("shipping.openPickingQueue", "Open picking queue")} />
        </div>
      </div>

      {!shippingReady && (
        <ReadinessGate
          eyebrow={t("shipping.readinessEyebrow", "Shipping readiness gate")}
          title={t("shipping.readinessTitle", "Finish warehouse and item setup before dispatch becomes a live promise")}
          body={t(
            "shipping.readinessBody",
            "Shipping only works when warehouse structure, storage locations, client accounts, and SKU master data are already trustworthy. Otherwise labels, tracking, and dispatch status turn into guesswork instead of customer truth."
          )}
          nextLabel={t("shipping.readinessNext", "Next recommended step:")}
          steps={missingRequiredSteps}
          t={t}
        />
      )}

      {shippingReady ? (
        <>
        <section
          className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/88 p-4 shadow-[0_16px_34px_rgba(19,33,44,0.06)] md:hidden"
          data-testid="shipping-mobile-next-action"
          data-shipping-path={shippingMobilePath}
        >
          <TaskCard
            label={t("shipping.mobileNextActionLabel", "Next action")}
            title={
              sortedOrders[0]
                ? mobileShippingActionLabel(sortedOrders[0])
                : t("shipping.mobileNoShippingWorkTitle", "No shipping action")}
            meta={
              sortedOrders[0]
                ? sortedOrders[0].order_number
                : t("shipping.mobileNoShippingWorkMeta", "Dispatch work is caught up.")
            }
            selected={sortedOrders.length > 0}
            tone={sortedOrders.length > 0 ? "neutral" : "success"}
            onClick={sortedOrders[0] ? () => setSelectedOrder(sortedOrders[0]) : undefined}
            action={
              sortedOrders.length > 0 ? (
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#24507a] text-white">
                  <ArrowRight size={15} />
                </span>
              ) : null
            }
          />
          <details
            className="mt-3 rounded-[1rem] border border-[#13212c]/8 bg-[#fffdfa] px-3 py-2"
            data-testid="shipping-mobile-queue-counts"
          >
            <summary className="cursor-pointer list-none text-xs font-semibold text-[#51606b]">
              {t("shipping.mobileQueueCounts", "View counts")}
            </summary>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fbf8f2] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#7f8d98]">{t("shipping.mobilePickedShort", "Picked")}</p>
                <p className="mt-1 text-lg font-semibold text-[#13212c]">{pickedOrders}</p>
              </div>
              <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fbf8f2] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#7f8d98]">{t("shipping.mobilePackingShort", "Packing")}</p>
                <p className="mt-1 text-lg font-semibold text-[#13212c]">{packingOrders}</p>
              </div>
              <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fff7e8] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#8a6511]">{t("shipping.mobilePackedShort", "Packed")}</p>
                <p className="mt-1 text-lg font-semibold text-[#13212c]">{packedOrders}</p>
              </div>
            </div>
          </details>
        </section>

        <section className="hidden rounded-[2rem] border border-[#13212c]/10 bg-white/84 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] md:block">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <Eyebrow className="tracking-[0.22em]">{t("shipping.workbenchEyebrow", "Shipping queue")}</Eyebrow>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-[#13212c]">
                {t("shipping.workbenchTitle", "Review picked orders, pack them, then confirm carrier handoff")}
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {sortedOrders.length > 0 ? (
                <ActionButton
                  onClick={() => setSelectedOrder(sortedOrders[0])}
                  className="text-[11px]"
                >
                  {t("shipping.openNextOrder", "Open next order")}
                </ActionButton>
              ) : null}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
              {t("shipping.readyOrdersChip", "{count} dispatch-ready orders", { count: orders.length })}
            </span>
            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("shipping.pickedOrdersChip", "{count} picked", { count: pickedOrders })}
            </span>
            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("shipping.packingOrdersChip", "{count} packing", { count: packingOrders })}
            </span>
            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("shipping.packedOrdersChip", "{count} packed", { count: packedOrders })}
            </span>
          </div>
          <div className="mt-5 hidden gap-3 md:grid md:grid-cols-2 xl:grid-cols-4">
            {shippingWorkflowSteps.map((step) => (
              <div
                key={step.step}
                className={`rounded-[1.15rem] border px-4 py-4 ${
                  step.active
                    ? "border-[#13212c]/18 bg-[#fffdfa] shadow-[0_10px_28px_rgba(19,33,44,0.06)]"
                    : "border-[#13212c]/8 bg-[#f7f4ee]"
                }`}
              >
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("shipping.workflowStep", "Step")} {step.step}
                </p>
                <p className="mt-2 text-sm font-semibold text-[#13212c]">{step.title}</p>
                <p className="mt-1.5 text-xs leading-5 text-[#61717d]">{step.body}</p>
              </div>
            ))}
          </div>
        </section>
        </>
      ) : null}

      {feedback ? (
        <div
          className={`rounded-[1.2rem] border px-4 py-3 text-sm ${
            feedback.tone === "success"
              ? "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
              : "border-[#e4c1b8] bg-[#fff1ed] text-[#8f3627]"
          }`}
          data-testid={feedback.tone === "success" ? "shipping-success-next-step" : undefined}
        >
          {feedback.text}
        </div>
      ) : null}

      {selectedOrder && shippingReady && (
        <div className="space-y-4" id="shipping-flow">
          <section className="max-w-full overflow-hidden rounded-2xl border border-[#13212c]/8 bg-white p-3 shadow md:hidden">
            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setSelectedOrder(null)}
                className="inline-flex min-h-[44px] shrink-0 items-center gap-1 rounded-full border border-[#13212c]/10 bg-[#fbf8f2] px-3 py-2 text-xs font-semibold text-[#13212c]"
              >
                <ArrowLeft size={14} />
                {t("shipping.backToShippingListShort", "Back")}
              </button>
              <p className="min-w-0 truncate text-xs font-semibold text-[#51606b]">
                {selectedOrder.order_number || t("shipping.shippingOrderFallback", "Shipping order")}
              </p>
            </div>

            <div className="mt-3 grid min-w-0 gap-1.5" style={{ gridTemplateColumns: `repeat(${shippingMobileSteps.length}, minmax(0, 1fr))` }}>
              {shippingMobileSteps.map((step) => (
                <div
                  key={step.key}
                  aria-current={step.status === "active" ? "step" : undefined}
                  className={`flex min-w-0 items-center justify-center gap-1 rounded-full border px-2 py-1.5 text-center text-[11px] font-semibold ${
                    step.status === "done"
                      ? "border-[#c8dfd1] bg-[#eef8f0] text-[#28543b]"
                      : step.status === "active"
                        ? "border-[#24507a]/20 bg-[#24507a] text-white"
                        : "border-[#e3ddd2] bg-[#fcfaf5] text-[#7f8d98]"
                  }`}
                >
                  <span className="sr-only">{step.label}</span>
                  <span className="shrink-0">{step.status === "done" ? "✓" : step.number}</span>
                  {step.status === "active" ? <span className="min-w-0 truncate">{step.label}</span> : null}
                </div>
              ))}
            </div>

            <div className="mt-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("shipping.currentOrderEyebrow", "Current shipping order")}
              </p>
              <p className="mt-1 text-base font-semibold leading-snug text-[#13212c]">{shippingMobileTitle}</p>
              <p className="mt-1 text-xs leading-5 text-[#51606b]">{shippingMobileHint}</p>
            </div>
          </section>

          {recoveryPrompt ? (
            <RecoveryPanel
              prompt={recoveryPrompt}
              onAction={() => handleRecoveryAction(recoveryPrompt.action)}
              onEscape={() => handleRecoveryAction("backToShippingList")}
              escapeLabel={t("shipping.recoveryBackToListAction", "Back to shipping list")}
              className="md:hidden"
            />
          ) : null}

          {!recoveryPrompt ? (
          <section
            className="rounded-2xl bg-white p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:hidden"
            data-testid="shipping-mobile-active-task"
            data-shipping-path={recoveryPrompt ? "exception" : !isPacked ? "pack" : "handoff"}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Eyebrow className="tracking-[0.22em]">{t("shipping.mobileCurrentActionEyebrow", "Current action")}</Eyebrow>
                <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
                  {!isPacked
                    ? t("shipping.packWorkTitle", "Confirm packed SKUs and quantities")
                    : t("shipping.shipStepTitle", "Confirm carrier handoff and tracking")}
                </h3>
              </div>
              {selectedStatus ? <StatusBadge status={selectedStatus} /> : null}
            </div>

            <div
              className="mt-4 grid grid-cols-3 gap-2 rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] p-2"
              data-testid="shipping-mobile-current-object"
            >
              <ShippingMiniStat
                label={t("shipping.mobileObjectOrder", "Order")}
                value={selectedOrderDetail?.order_number || selectedOrder?.order_number || "—"}
              />
              <ShippingMiniStat
                label={t("shipping.mobileObjectStep", "Step")}
                value={!isPacked ? t("shipping.mobileObjectStepPack", "Pack") : t("shipping.mobileObjectStepHandoff", "Handoff")}
              />
              <ShippingMiniStat
                label={t("shipping.mobileObjectLines", "Lines")}
                value={`${packCheckConfirmedLines}/${packCheckLineTotal}`}
              />
            </div>

            {!isPacked ? (
              <>
                <div className="mt-4 flex flex-wrap gap-2">
                  <span
                    className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                      packingCheckComplete
                        ? "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
                        : packCheckConfirmedLines > 0
                          ? "border-[#e6c06a]/55 bg-[#fff8e8] text-[#8a5b00]"
                          : "border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d]"
                    }`}
                  >
                    {packingCheckComplete
                      ? t("shipping.packingScanCompleteChip", "Pack check complete")
                      : t("shipping.packingScanProgressChip", "SKU check {checked}/{total}", {
                          checked: packCheckConfirmedLines,
                          total: packCheckLineTotal,
                        })}
                  </span>
                </div>

                {packReady ? (
                  <div id="shipping-pack-scanner-mobile" className="mt-5 space-y-3">
                    <BarcodeScanner
                      context="packing"
                      onScan={handlePackingScan}
                      placeholder={t("shipping.packScanPlaceholder", "Scan SKU to check the packed line...")}
                      suggestedCodes={packingSuggestedCodes}
                      manualHintTitle={t("shipping.packScanHintTitle", "SKU check")}
                      manualHintBody={t("shipping.packScanHintBody", "Scan each picked SKU once. Packed quantity defaults to the picked quantity and can be adjusted in the table.")}
                      deviceHint={t("shipping.packScanDeviceHint", "Use a scanner gun, type the SKU, or press a suggested SKU chip to confirm that SKU line.")}
                    />
                    {packingScanFeedback ? (
                      <p className="rounded-[0.9rem] border border-[#9ed4b7] bg-[#edf8f1] px-3 py-2 text-xs font-medium text-[#1b5f38]">
                        {packingScanFeedback}
                      </p>
                    ) : null}
                    {packingScanError ? (
                      <p className="rounded-[0.9rem] border border-[#e4c1b8] bg-[#fff1ed] px-3 py-2 text-xs font-medium text-[#8f3627]">
                        {packingScanError}
                      </p>
                    ) : null}
                    {packingCheckComplete ? (
                      <div className="space-y-3 rounded-[1rem] border border-[#9ed4b7] bg-[#edf8f1] p-3">
                        <p className="text-sm font-semibold text-[#1b5f38]">
                          {t("shipping.mobilePackReadyTitle", "All picked SKUs are checked")}
                        </p>
                        <ShippingMiniStat
                          label={t("shipping.packingQuantityTotalShort", "Packed")}
                          value={`${totalPackedDraft}/${totalPickedToPack}`}
                        />
                        <ActionButton
                          onClick={() => packMutation.mutate()}
                          disabled={!canConfirmPack}
                          data-testid="shipping-mobile-confirm-pack"
                          className="min-h-[44px] w-full"
                        >
                          {packMutation.isPending
                            ? t("shipping.confirmingPack", "Confirming packing...")
                            : t("shipping.confirmPack", "Confirm packing")}
                        </ActionButton>
                      </div>
                    ) : (
                      <p className="rounded-[0.9rem] border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-2 text-xs font-medium text-[#51606b]">
                        {packingLinesRemaining > 0
                          ? t("shipping.mobilePackScanRemaining", "Check {count} more SKU before confirming packing.", {
                              count: packingLinesRemaining,
                            })
                          : t("shipping.mobilePackScanFirst", "Scan the first picked SKU to start the pack check.")}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="mt-4 rounded-xl border border-[#e4c1b8] bg-[#fff1ed] px-3 py-3 text-sm font-medium text-[#8f3627]">
                    <p>{t("shipping.finishPicksFirstChip", "Finish picks first")}</p>
                    <a
                      href="/picking"
                      className="mt-3 inline-flex min-h-[44px] w-full items-center justify-center rounded-xl bg-[#13212c] px-4 py-2 text-sm font-semibold text-white"
                    >
                      {t("shipping.openPicking", "Open picking")}
                    </a>
                  </div>
                )}

                <details className="mt-5 rounded-[1.15rem] border border-[#13212c]/10 bg-[#fffdfa] p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-[#13212c]">
                    {t("shipping.mobileLineDetails", "Line details and quantities")}
                  </summary>
                  <div className="mt-4 space-y-3">
                    {lines.map((line: any, index: number) => {
                      const packedQty = getPackedDraftQuantity(line);
                      const lineConfirmed = Boolean(packingDrafts[line.sku_id]?.skuConfirmed);
                      const lineMatchesPicked = packedQty === Number(line.quantity_picked || 0);
                      return (
                        <div key={line.line_id} className="rounded-xl border border-[#13212c]/8 bg-white p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7f8d98]">
                                {t("common.rowNumber", "No.")} {index + 1}
                              </p>
                              <p className="mt-1 break-words text-sm font-semibold text-[#13212c]">{line.sku_code}</p>
                              <p className="mt-1 text-xs leading-5 text-[#61717d]">{line.sku_name}</p>
                            </div>
                            <span
                              className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium ${
                                lineConfirmed
                                  ? "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
                                  : "border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d]"
                              }`}
                            >
                              {lineConfirmed ? t("shipping.skuChecked", "Checked") : t("shipping.skuCheckNeeded", "Scan once")}
                            </span>
                          </div>
                          <div className="mt-3 grid grid-cols-2 gap-2">
                            <ShippingMiniStat label={t("shipping.qtyPicked", "Picked")} value={String(line.quantity_picked)} />
                            <label className="text-xs font-medium text-[#51606b]">
                              {t("shipping.qtyPacked", "Packed qty")}
                              <input
                                type="number"
                                min={0}
                                step={1}
                                value={packedQty}
                                onChange={(event) => handlePackedQuantityChange(line, event.target.value)}
                                className={`mt-1 h-10 w-full rounded-xl border bg-white px-3 text-sm font-semibold outline-none transition focus:border-[#13212c]/25 ${
                                  lineMatchesPicked ? "border-[#13212c]/10 text-[#13212c]" : "border-[#e6c06a] text-[#8a5b00]"
                                }`}
                                aria-label={t("shipping.packedQuantityForSku", "Packed quantity for {sku}", {
                                  sku: line.sku_code || line.sku_id,
                                })}
                              />
                            </label>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </details>
              </>
            ) : (
              <>
                <div className="mt-5 grid gap-3">
                  <label className="space-y-1.5 text-sm text-[#51606b]">
                    <span>{t("shipping.carrier", "Carrier")}</span>
	                    <input
                        ref={mobileCarrierInputRef}
	                      value={carrierDraft}
	                      onChange={(event) => {
                          setCarrierDraft(event.target.value);
                          setApiRecoveryPrompt(null);
                          setMobileHandoffReview(false);
                        }}
	                      placeholder={t("shipping.enterCarrier", "Enter a carrier before shipping.")}
	                      data-testid="shipping-carrier-input"
	                      className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
	                    />
                  </label>
                  <label className="block space-y-1.5 text-sm text-[#51606b]">
                    <span>{t("shipping.tracking", "Tracking")}</span>
	                    <input
                        ref={mobileTrackingInputRef}
	                      value={trackingDraft}
	                      onChange={(event) => {
                          setTrackingDraft(event.target.value);
                          setApiRecoveryPrompt(null);
                          setMobileHandoffReview(false);
                          setTrackingScanFeedback(null);
                        }}
	                      placeholder={t("shipping.enterTracking", "Enter a tracking number before shipping.")}
	                      data-testid="shipping-tracking-input"
	                      className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
	                    />
	                  </label>
                    {trackingScanFeedback ? (
                      <p className="rounded-[0.9rem] border border-[#9ed4b7] bg-[#edf8f1] px-3 py-2 text-xs font-medium text-[#1b5f38]">
                        {trackingScanFeedback}
                      </p>
                    ) : null}
	                  <div data-testid="shipping-tracking-scanner" className="rounded-[1rem] border border-[#13212c]/8 bg-[#fffdfa] p-3">
	                    <BarcodeScanner
                      context="tracking"
                      onScan={handleTrackingScan}
                      placeholder={t("shipping.trackingScanPlaceholder", "Scan tracking barcode...")}
                      manualHintTitle={t("shipping.trackingScanHintTitle", "Tracking barcode")}
                      manualHintBody={t("shipping.trackingScanHintBody", "Scan the carrier label or type the tracking number. The scanned value fills the tracking field above.")}
                      deviceHint={t("shipping.trackingScanDeviceHint", "Use a scanner gun, type the tracking number, or use Scan for the phone camera.")}
                    />
                  </div>
                  {mobileHandoffReview ? (
                    <div className="space-y-3 rounded-[1rem] border border-[#13212c]/10 bg-[#f7f4ee] p-3">
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <ShippingMiniStat label={t("shipping.carrier", "Carrier")} value={carrierDraft.trim()} />
                        <ShippingMiniStat label={t("shipping.tracking", "Tracking")} value={trackingDraft.trim()} />
                      </div>
                      <ActionButton
                        onClick={() => shipMutation.mutate()}
                        disabled={!canConfirmShip}
                        data-testid="shipping-mobile-confirm-shipment"
                        className="min-h-[44px] w-full"
                      >
                        {shipMutation.isPending
                          ? t("shipping.confirmingShipment", "Confirming shipment...")
                          : t("shipping.confirmShipment", "Confirm shipment")}
                      </ActionButton>
                    </div>
                  ) : (
                    <>
                      <ActionButton
                        onClick={continueMobileHandoff}
                        data-testid="shipping-mobile-review-handoff"
                        className="min-h-[44px] w-full"
                      >
                        {mobileHandoffCaptureComplete
                          ? t("shipping.mobileReviewHandoffAction", "Review handoff")
                          : t("shipping.mobileCaptureHandoffAction", "Enter carrier and tracking")}
                      </ActionButton>
                      {!mobileHandoffCaptureComplete ? (
                        <p className="rounded-[0.9rem] border border-[#e6c06a]/55 bg-[#fff8e8] px-3 py-2 text-xs font-medium text-[#8a5b00]">
                          {t("shipping.shipBlockedMissingFields", "Enter carrier and tracking to confirm handoff.")}
                        </p>
                      ) : null}
                    </>
                  )}
                </div>

                <details className="mt-5 rounded-[1.15rem] border border-[#13212c]/10 bg-[#fffdfa] p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-[#13212c]">
                    {t("shipping.mobileSecondaryDetails", "Documents and optional details")}
                  </summary>
                  <div className="mt-4 space-y-3">
                    <ActionButton
                      onClick={() => packingSlipMutation.mutate()}
                      disabled={!selectedOrderDetail?.id || packingSlipMutation.isPending}
                      variant="secondary"
                      className="min-h-[44px] w-full"
                    >
                      {packingSlipMutation.isPending
                        ? t("shipping.downloadingPackingSlip", "Downloading...")
                        : t("shipping.downloadPackingSlip", "Download packing slip")}
                    </ActionButton>
                    <label className="block space-y-1.5 text-sm text-[#51606b]">
                      <span>{t("shipping.serviceLevel", "Service level")}</span>
                      <input
                        value={serviceLevelDraft}
                        onChange={(event) => setServiceLevelDraft(event.target.value)}
                        placeholder={t("shipping.serviceLevelPlaceholder", "Optional")}
                        className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
                      />
                    </label>
                    <label className="block space-y-1.5 text-sm text-[#51606b]">
                      <span>{t("shipping.shippingCost", "Shipping cost")}</span>
                      <input
                        value={shippingCostDraft}
                        onChange={(event) => setShippingCostDraft(event.target.value)}
                        placeholder={t("shipping.shippingCostPlaceholder", "Optional")}
                        inputMode="decimal"
                        className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
                      />
                    </label>
                  </div>
                </details>
              </>
            )}
          </section>
          ) : null}

          <section className="hidden rounded-2xl bg-white p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <ActionButton
                  onClick={() => setSelectedOrder(null)}
                  className="mb-4 normal-case tracking-normal"
                >
                  {t("shipping.backToShippingList", "Back to shipping list")}
                </ActionButton>
                <Eyebrow className="tracking-[0.22em]">
                  {t("shipping.currentOrderEyebrow", "Current shipping order")}
                </Eyebrow>
                <h2 className="mt-2 text-lg font-semibold text-[#13212c]">
                  {t("shipping.currentOrderTitle", "Pack and ship one outbound order")}
                </h2>
              </div>
              <span className="w-fit rounded-full border border-[#13212c]/10 bg-[#f8f4ec] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                {selectedOrder.order_number}
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
                {t("shipping.client", "Client")}: {clientMap.get(selectedOrder.client_id) || selectedOrder.client_id || "—"}
              </span>
              <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
                {t("shipping.currentStatus", "Current status")}: <StatusLabel status={selectedStatus} t={t} />
              </span>
              <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
                {t("shipping.lineCount", "Lines")}: {lines.length}
              </span>
              {selectedOrder.reference_number ? (
                <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
                  {selectedOrder.reference_number}
                </span>
              ) : null}
            </div>
          </section>

          {recoveryPrompt ? (
            <RecoveryPanel
              prompt={recoveryPrompt}
              onAction={() => handleRecoveryAction(recoveryPrompt.action)}
              onEscape={() => handleRecoveryAction("backToShippingList")}
              escapeLabel={t("shipping.recoveryBackToListAction", "Back to shipping list")}
              className="hidden md:flex"
            />
          ) : null}

          {!recoveryPrompt ? (
          <section className="hidden rounded-2xl bg-white p-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
            <div className="grid gap-3 md:grid-cols-3">
              <ShippingStep
                index={1}
                label={t("shipping.packStepShort", "Pack check")}
                done={isPacked}
                active={!isPacked}
              />
              <ShippingStep
                index={2}
                label={t("shipping.documentsStepShort", "Documents")}
                done={false}
                active={!!selectedOrderDetail?.id}
              />
              <ShippingStep
                index={3}
                label={t("shipping.carrierStepShort", "Carrier handoff")}
                done={false}
                active={isPacked}
              />
            </div>
          </section>
          ) : null}

          {!recoveryPrompt ? (
          <section className="hidden rounded-2xl bg-white p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <Eyebrow className="tracking-[0.22em]">{t("shipping.packStep", "Step 1")}</Eyebrow>
                <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
                  {t("shipping.packWorkTitle", "Confirm packed SKUs and quantities")}
                </h3>
                <p className="mt-2 text-sm leading-6 text-[#61717d]">
                  {t("shipping.packWorkBody", "Scan each SKU once to confirm the product line. Packed quantities default to the picked quantity and can be adjusted before confirmation.")}
                </p>
              </div>
              <div className="hidden grid-cols-2 gap-2 text-sm sm:grid lg:min-w-[18rem]">
                <ShippingMiniStat label={t("shipping.currentStatus", "Current status")} value={selectedStatus || "—"} />
                <ShippingMiniStat label={t("shipping.lineCount", "Lines")} value={String(lines.length)} />
              </div>
            </div>

            {detailLoading ? <p className="mt-4 text-sm text-[#7f8d98]">{t("common.loading", "Loading...")}</p> : null}

            <div className="mt-5 hidden overflow-x-auto rounded-[1rem] border border-[#13212c]/8 bg-white md:block">
              <table className="min-w-[760px] w-full divide-y divide-[#13212c]/8 text-sm">
                <thead className="bg-[#f7f4ee] text-left text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                  <tr>
                    <th className="w-[72px] px-4 py-3">{t("common.rowNumber", "No.")}</th>
                    <th className="px-4 py-3">{t("common.sku", "SKU")}</th>
                    <th className="px-4 py-3">{t("shipping.qtyOrdered", "Ordered")}</th>
                    <th className="px-4 py-3">{t("shipping.qtyPicked", "Picked")}</th>
                    <th className="px-4 py-3">{t("shipping.qtyPacked", "Packed qty")}</th>
                    <th className="px-4 py-3">{t("shipping.skuCheck", "SKU check")}</th>
                    <th className="px-4 py-3">{t("shipping.qtyShipped", "Shipped")}</th>
                    <th className="px-4 py-3">{t("shipping.pickLocation", "Pick location")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#13212c]/8">
                  {lines.map((line: any, index: number) => {
                    const packedQty = getPackedDraftQuantity(line);
                    const lineConfirmed = isPacked || Boolean(packingDrafts[line.sku_id]?.skuConfirmed);
                    const lineMatchesPicked = packedQty === Number(line.quantity_picked || 0);
                    return (
                      <tr key={line.line_id}>
                        <td className="px-4 py-3 text-[#7f8d98]">{index + 1}</td>
                        <td className="px-4 py-3 text-[#13212c]">
                          <div className="font-medium">{line.sku_code}</div>
                          <div className="text-xs text-[#7f8d98]">{line.sku_name}</div>
                        </td>
                        <td className="px-4 py-3">{line.quantity_ordered}</td>
                        <td className="px-4 py-3">{line.quantity_picked}</td>
                        <td className="px-4 py-3">
                          {isPacked ? (
                            <span className="rounded-full border border-[#9ed4b7] bg-[#edf8f1] px-2.5 py-1 text-xs font-medium text-[#1b5f38]">
                              {line.quantity_picked}
                            </span>
                          ) : (
                            <input
                              type="number"
                              min={0}
                              step={1}
                              value={packedQty}
                              onChange={(event) => handlePackedQuantityChange(line, event.target.value)}
                              className={`h-9 w-24 rounded-xl border bg-white px-3 text-sm font-semibold outline-none transition focus:border-[#13212c]/25 ${
                                lineMatchesPicked ? "border-[#13212c]/10 text-[#13212c]" : "border-[#e6c06a] text-[#8a5b00]"
                              }`}
                              aria-label={t("shipping.packedQuantityForSku", "Packed quantity for {sku}", {
                                sku: line.sku_code || line.sku_id,
                              })}
                            />
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                              lineConfirmed
                                ? "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
                                : "border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d]"
                            }`}
                          >
                            {lineConfirmed ? t("shipping.skuChecked", "Checked") : t("shipping.skuCheckNeeded", "Scan once")}
                          </span>
                        </td>
                        <td className="px-4 py-3">{line.quantity_shipped}</td>
                        <td className="px-4 py-3">{line.pick_location || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <span
                className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                  packReady && (packingCheckComplete || isPacked)
                    ? "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
                    : packCheckConfirmedLines > 0
                      ? "border-[#e6c06a]/55 bg-[#fff8e8] text-[#8a5b00]"
                      : "border-[#e4c1b8] bg-[#fff1ed] text-[#8f3627]"
                }`}
              >
                {isPacked
                  ? t("shipping.packedStateChip", "Packed")
                  : packingCheckComplete
                    ? t("shipping.packingScanCompleteChip", "Pack check complete")
                    : packReady && packCheckConfirmedLines > 0
                      ? t("shipping.packingScanProgressChip", "SKU check {checked}/{total}", {
                          checked: packCheckConfirmedLines,
                          total: packCheckLineTotal,
                        })
                    : packReady
                      ? t("shipping.scanPackingFirstChip", "Scan each SKU once")
                      : t("shipping.finishPicksFirstChip", "Finish picks first")}
              </span>
              {packReady && packingLinesRemaining > 0 ? (
                <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                  {t("shipping.packingScanRemainingChip", "{count} SKU lines to check", {
                    count: packingLinesRemaining,
                  })}
                </span>
              ) : null}
              {packReady && packingQuantityMismatch ? (
                <span className="rounded-full border border-[#e6c06a]/55 bg-[#fff8e8] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a5b00]">
                  {t("shipping.packingQuantityMismatchChip", "Fix packed quantity")}
                </span>
              ) : null}
              {packReady ? (
                <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                  {t("shipping.packingQuantityTotalChip", "Packed {packed}/{picked}", {
                    packed: totalPackedDraft,
                    picked: totalPickedToPack,
                  })}
                </span>
              ) : null}
            </div>

            {!isPacked && packReady ? (
              <div id="shipping-pack-scanner-desktop" className="mt-5 space-y-3">
                <BarcodeScanner
                  context="packing"
                  onScan={handlePackingScan}
                  placeholder={t("shipping.packScanPlaceholder", "Scan SKU to check the packed line...")}
                  suggestedCodes={packingSuggestedCodes}
                  manualHintTitle={t("shipping.packScanHintTitle", "SKU check")}
                  manualHintBody={t("shipping.packScanHintBody", "Scan each picked SKU once. Packed quantity defaults to the picked quantity and can be adjusted in the table.")}
                  deviceHint={t("shipping.packScanDeviceHint", "Use a scanner gun, type the SKU, or press a suggested SKU chip to confirm that SKU line.")}
                />
                {packingScanError ? (
                  <p className="rounded-[0.9rem] border border-[#e4c1b8] bg-[#fff1ed] px-3 py-2 text-xs font-medium text-[#8f3627]">
                    {packingScanError}
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => packMutation.mutate()}
                    disabled={!canConfirmPack}
                    className={`min-h-[44px] rounded-xl px-5 py-2 text-sm font-semibold transition ${
                      canConfirmPack
                        ? "bg-[#13212c] text-white hover:bg-[#243545]"
                        : "cursor-not-allowed bg-[#cbd5e1] text-[#51606b]"
                    }`}
                  >
                    {packMutation.isPending
                      ? t("shipping.confirmingPack", "Confirming packing...")
                      : !canConfirmPack && packingLinesRemaining > 0
                        ? t("shipping.confirmPackBlocked", "Check {count} more SKU", {
                            count: packingLinesRemaining,
                          })
                      : !canConfirmPack && packingQuantityMismatch
                        ? t("shipping.confirmPackQuantityBlocked", "Fix packed quantity")
                      : t("shipping.confirmPack", "Confirm packing")}
                  </button>
                  {Object.keys(packingDrafts).length > 0 ? (
                    <button
                      type="button"
                      onClick={resetPackCheck}
                      className="min-h-[44px] rounded-xl border border-[#13212c]/10 bg-white px-5 py-2 text-sm font-semibold text-[#13212c] transition hover:bg-[#f7f4ee]"
                    >
                      {t("shipping.resetPackingScans", "Reset pack check")}
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </section>
          ) : null}

          {!recoveryPrompt ? (
          <section className="hidden rounded-2xl bg-white p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <Eyebrow className="tracking-[0.22em]">{t("shipping.documentStep", "Documents")}</Eyebrow>
                <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
                  {t("shipping.documentStepTitle", "Print the packing slip before carrier handoff")}
                </h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[#61717d]">
                  {t("shipping.documentStepBody", "Download a customer-ready PDF from the same order lines that packing and shipping are checking.")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => packingSlipMutation.mutate()}
                disabled={!selectedOrderDetail?.id || packingSlipMutation.isPending}
                className="min-h-[44px] w-fit rounded-xl bg-[#13212c] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#243545] disabled:cursor-not-allowed disabled:bg-[#cbd5e1] disabled:text-[#51606b]"
              >
                {packingSlipMutation.isPending
                  ? t("shipping.downloadingPackingSlip", "Downloading...")
                  : t("shipping.downloadPackingSlip", "Download packing slip")}
              </button>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                {t("shipping.packingSlipPdfChip", "PDF")}
              </span>
              <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                {t("shipping.packingSlipLinesChip", "{count} lines", { count: lines.length })}
              </span>
            </div>
          </section>
          ) : null}

          {!recoveryPrompt ? (
          <section className="hidden rounded-2xl bg-white p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <Eyebrow className="tracking-[0.22em]">{t("shipping.shipStep", "Step 3")}</Eyebrow>
                <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
                  {t("shipping.shipStepTitle", "Confirm carrier handoff and tracking")}
                </h3>
                <p className="mt-2 text-sm leading-6 text-[#61717d]">
                  {t("shipping.shipStepBody", "Once the package is packed, record the carrier and tracking number that become the customer-visible shipping truth.")}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <span
                  className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                    carrierDraft.trim()
                      ? "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
                      : "border-[#13212c]/10 bg-white text-[#61717d]"
                  }`}
                >
                  {carrierDraft.trim() ? t("shipping.carrierReadyChip", "Carrier ready") : t("shipping.carrierNeededChip", "Carrier needed")}
                </span>
                <span
                  className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                    trackingDraft.trim()
                      ? "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
                      : "border-[#13212c]/10 bg-white text-[#61717d]"
                  }`}
                >
                  {trackingDraft.trim()
                    ? t("shipping.trackingReadyChip", "Tracking ready")
                    : t("shipping.trackingNeededChip", "Tracking needed")}
                </span>
              </div>
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              <label className="space-y-1.5 text-sm text-[#51606b]">
                <span>{t("shipping.carrier", "Carrier")}</span>
                <input
                    ref={desktopCarrierInputRef}
	                  value={carrierDraft}
	                  onChange={(event) => {
                    setCarrierDraft(event.target.value);
                    setApiRecoveryPrompt(null);
                    setMobileHandoffReview(false);
                  }}
	                  placeholder={t("shipping.enterCarrier", "Enter a carrier before shipping.")}
	                  data-testid="shipping-carrier-input"
	                  className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
	                />
              </label>
              <div className="space-y-1.5 text-sm text-[#51606b]">
                <label className="block space-y-1.5">
                  <span>{t("shipping.tracking", "Tracking")}</span>
                  <input
                      ref={desktopTrackingInputRef}
	                    value={trackingDraft}
	                    onChange={(event) => {
                        setTrackingDraft(event.target.value);
                        setApiRecoveryPrompt(null);
                        setMobileHandoffReview(false);
                        setTrackingScanFeedback(null);
                      }}
	                    placeholder={t("shipping.enterTracking", "Enter a tracking number before shipping.")}
	                    data-testid="shipping-tracking-input"
	                    className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
	                  />
	                </label>
                  {trackingScanFeedback ? (
                    <p className="rounded-[0.9rem] border border-[#9ed4b7] bg-[#edf8f1] px-3 py-2 text-xs font-medium text-[#1b5f38]">
                      {trackingScanFeedback}
                    </p>
                  ) : null}
	                {isPacked ? (
	                  <div data-testid="shipping-tracking-scanner" className="rounded-[1rem] border border-[#13212c]/8 bg-[#fffdfa] p-3">
	                    <BarcodeScanner
                      context="tracking"
                      onScan={handleTrackingScan}
                      placeholder={t("shipping.trackingScanPlaceholder", "Scan tracking barcode...")}
                      manualHintTitle={t("shipping.trackingScanHintTitle", "Tracking barcode")}
                      manualHintBody={t("shipping.trackingScanHintBody", "Scan the carrier label or type the tracking number. The scanned value fills the tracking field above.")}
                      deviceHint={t("shipping.trackingScanDeviceHint", "Use a scanner gun, type the tracking number, or use Scan for the phone camera.")}
                    />
                  </div>
                ) : null}
              </div>
              <label className="space-y-1.5 text-sm text-[#51606b]">
                <span>{t("shipping.serviceLevel", "Service level")}</span>
                <input
                  value={serviceLevelDraft}
                  onChange={(event) => setServiceLevelDraft(event.target.value)}
                  placeholder={t("shipping.serviceLevelPlaceholder", "Optional")}
                  className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
                />
              </label>
              <label className="space-y-1.5 text-sm text-[#51606b]">
                <span>{t("shipping.shippingCost", "Shipping cost")}</span>
                <input
                  value={shippingCostDraft}
                  onChange={(event) => setShippingCostDraft(event.target.value)}
                  placeholder={t("shipping.shippingCostPlaceholder", "Optional")}
                  inputMode="decimal"
                  className="w-full rounded-xl border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/25"
                />
              </label>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                onClick={() => shipMutation.mutate()}
                disabled={!canConfirmShip}
                className={`min-h-[44px] rounded-xl px-5 py-2 text-sm font-semibold transition ${
                  canConfirmShip
                    ? "bg-[#13212c] text-white hover:bg-[#243545]"
                    : "cursor-not-allowed bg-[#cbd5e1] text-[#51606b]"
                }`}
              >
                {shipMutation.isPending ? t("shipping.confirmingShipment", "Confirming shipment...") : t("shipping.confirmShipment", "Confirm shipment")}
              </button>
            </div>
          </section>
          ) : null}
        </div>
      )}

      {!selectedOrder ? (
        <div className="space-y-4">
          <div className="space-y-2 md:hidden">
            <div className="px-1">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("shipping.mobileOrderQueueEyebrow", "Shipping queue")}
              </p>
            </div>
            <details className="rounded-[1rem] border border-[#13212c]/8 bg-[#fffdfa] px-3 py-2">
              <summary className="cursor-pointer list-none text-xs font-semibold text-[#51606b]">
                {t("shipping.mobileSortQueue", "Sort queue")}
              </summary>
              <div className="mt-3 flex flex-wrap gap-2">
                {columns
                  .filter((column) => "sortable" in column && column.sortable)
                  .slice(0, 5)
                  .map((column) => (
                    <button
                      key={`mobile-shipping-sort-${column.key}`}
                      type="button"
                      onClick={() => handleShippingHeaderClick(column.key)}
                      className={`inline-flex min-h-[44px] items-center gap-1 rounded-full border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] ${
                        shippingSortField === column.key
                          ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                          : "border-[#13212c]/10 bg-white text-[#61717d]"
                      }`}
                    >
                      <span>{column.header}</span>
                      <span>{shippingSortField === column.key ? (shippingSortDirection === "asc" ? "↑" : "↓") : "↕"}</span>
                    </button>
                  ))}
              </div>
            </details>
            {isLoading ? (
              <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white/80 px-4 py-6 text-center text-sm text-[#7f8e98]">
                {t("common.loading", "Loading...")}
              </div>
            ) : sortedOrders.length === 0 ? (
              <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white/80 px-4 py-6 text-sm text-[#61717d]">
                <p className="font-semibold text-[#13212c]">{t("shipping.empty", "No orders ready to ship")}</p>
                <p className="mt-2 leading-6">
                  {t("shipping.emptyHint", "Shipping becomes active after orders move through picking and arrive at dispatch-ready status.")}
                </p>
                <a
                  href="/picking"
                  className="mt-4 inline-flex min-h-[44px] items-center justify-center rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8]"
                >
                  {t("shipping.openPicking", "Open picking")}
                </a>
              </div>
            ) : (
              sortedOrders.map((row: any) => (
                <TaskCard
                  key={row.id}
                  label={t("shipping.mobileOrderQueueItemLabel", "Shipping order")}
                  title={row.order_number}
                  meta={mobileShippingActionLabel(row)}
                  chips={
                    <>
                      <StatusBadge status={row.status} />
                      <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#61717d]">
                        {clientMap.get(row.client_id) || row.client_id || t("common.client", "Client")}
                      </span>
                    </>
                  }
                  action={
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#13212c]/10 bg-white text-[#13212c]">
                      <ArrowRight size={15} />
                    </span>
                  }
                  onClick={() => setSelectedOrder(row)}
                />
              ))
            )}
          </div>

          <div className="hidden md:block">
            <DataTable
              columns={columns}
              data={sortedOrders}
              loading={isLoading}
              emptyMessage={t("shipping.empty", "No orders ready to ship")}
              emptyHint={t("shipping.emptyHint", "Shipping becomes active after orders move through picking and arrive at dispatch-ready status.")}
              emptyActionLabel={t("shipping.openPicking", "Open picking")}
              emptyActionHref="/picking"
              onRowClick={(row) => setSelectedOrder(row)}
              onHeaderClick={handleShippingHeaderClick}
              sortField={shippingSortField}
              sortDirection={shippingSortDirection}
            />
          </div>
          {hasMoreOrderBatches ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.4rem] border border-[#24507a]/12 bg-[#eef3f8] px-4 py-3 text-sm text-[#51606b]">
              <p>
                {t("shipping.moreOrdersAvailable", "{count} orders loaded. More outbound orders are available from the server.", {
                  count: String(orderRows.length),
                })}
              </p>
              <button
                type="button"
                onClick={() => fetchNextOrderBatch()}
                disabled={isFetchingNextOrderBatch}
                className="min-h-[44px] rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:cursor-not-allowed disabled:bg-[#9ca7af]"
              >
                {isFetchingNextOrderBatch
                  ? t("common.loading", "Loading...")
                  : t("shipping.loadMoreOrders", "Load more orders")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}


function ReadinessGate({
  eyebrow,
  title,
  body,
  nextLabel,
  steps,
  t,
}: {
  eyebrow: string;
  title: string;
  body: string;
  nextLabel: string;
  steps: any[];
  t: (key: string, fallback?: string) => string;
}) {
  return (
    <section className="rounded-[2rem] border border-[#f0cf9d] bg-[#fff7ea] p-6 shadow-[0_20px_52px_rgba(19,33,44,0.06)]">
      <div className="flex items-start gap-4">
        <div className="rounded-2xl border border-[#f7bf45]/35 bg-[#f7bf45]/14 p-2.5 text-[#c18500]">
          <AlertCircle size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#8b723f]">{eyebrow}</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[#13212c]">{title}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-[#6f6248]">{body}</p>
          <div className="mt-5 grid gap-3 lg:grid-cols-2">
            {steps.map((step: any) => (
              <a
                key={step.name}
                href={checklistHref(step.name)}
                className="rounded-[1.25rem] border border-[#e6d4b2] bg-white/80 px-4 py-4 transition hover:border-[#d4b07a] hover:bg-white"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#8a7755]">{t("receiving.requiredStep", "Required step")}</p>
                    <p className="mt-2 text-sm font-semibold text-[#13212c]">{t(`dashboard.checklist.${step.name}.title`, step.title || "")}</p>
                    <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{t(`dashboard.checklist.${step.name}.description`, step.description || "")}</p>
                  </div>
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#13212c] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#f4efe8]">
                    {t("dashboard.start", "Start")}
                    <ArrowRight size={13} />
                  </span>
                </div>
              </a>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3 text-sm text-[#6f6248]">
            <span className="font-semibold text-[#13212c]">{nextLabel}</span>
            <a
              href={checklistHref(steps[0]?.name || "warehouse")}
              className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-4 py-2 font-semibold text-[#13212c] transition hover:bg-[#fffdfa]"
            >
              {t(`dashboard.checklist.${steps[0]?.name || "warehouse"}.title`, steps[0]?.title || "")}
              <ArrowRight size={14} />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

function RecoveryPanel({
  prompt,
  onAction,
  onEscape,
  escapeLabel,
  className = "",
}: {
  prompt: RecoveryPrompt;
  onAction: () => void;
  onEscape?: () => void;
  escapeLabel?: string;
  className?: string;
}) {
  const { t } = useI18n();
  const safeExitAction = onEscape && prompt.action !== "backToShippingList" ? "backToShippingList" : undefined;
  const safeExitLabel = escapeLabel || t("shipping.recoveryBackToListAction", "Back to shipping list");

  return (
    <WorkflowRecoveryPanel
      as="section"
      workflow="shipping"
      code={prompt.action}
      action={prompt.action}
      safeExit={safeExitAction}
      title={prompt.title}
      body={prompt.body}
      recommendedActionLabel={prompt.actionLabel}
      returnEntryLabel={safeExitLabel}
      labels={{
        whatHappened: t("recovery.whatHappened", "What happened"),
        whyBlocked: t("recovery.whyBlocked", "Why this cannot continue"),
        recommendedAction: t("recovery.recommendedAction", "Recommended action"),
        returnEntry: t("recovery.returnEntry", "Return entry"),
      }}
      tone={prompt.tone}
      className={`shadow-[0_14px_32px_rgba(19,33,44,0.06)] ${className}`}
      actionsClassName="mt-4 grid gap-2 md:max-w-[13rem]"
      actions={
        <>
          <ActionButton
            onClick={onAction}
            variant={prompt.tone === "error" ? "danger" : prompt.tone === "warning" ? "secondary" : "primary"}
            className="min-h-[44px] w-full"
            data-testid={`shipping-recovery-action-${prompt.action}`}
          >
            {prompt.actionLabel}
          </ActionButton>
          {onEscape && prompt.action !== "backToShippingList" ? (
            <ActionButton
              onClick={onEscape}
              variant="secondary"
              className="min-h-[44px] w-full"
              data-testid="shipping-recovery-safe-exit"
            >
              {safeExitLabel}
            </ActionButton>
          ) : null}
        </>
      }
    />
  );
}

function ShippingStep({
  index,
  label,
  done,
  active,
}: {
  index: number;
  label: string;
  done: boolean;
  active: boolean;
}) {
  return (
    <div
      className={`rounded-xl border px-4 py-3 ${
        done
          ? "border-[#9ed4b7] bg-[#edf8f1]"
          : active
            ? "border-[#b7d3f4] bg-[#f3f8fb]"
            : "border-[#e3ddd2] bg-[#f8f4ec]"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
            done
              ? "bg-[#1b7f4c] text-white"
              : active
                ? "bg-[#245d8f] text-white"
                : "bg-white text-[#7f8d98]"
          }`}
        >
          {done ? "✓" : index}
        </span>
        <p className={`text-sm font-semibold ${done || active ? "text-[#13212c]" : "text-[#61717d]"}`}>
          {label}
        </p>
      </div>
    </div>
  );
}

function ShippingMiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}

function StatusLabel({ status, t }: { status: string; t: (key: string, fallback?: string) => string }) {
  if (status === "picked") return <span>{t("common.status.picked", "Picked")}</span>;
  if (status === "packed") return <span>{t("common.status.packed", "Packed")}</span>;
  if (status === "shipped") return <span>{t("common.status.shipped", "Shipped")}</span>;
  return <span>{status || "—"}</span>;
}
