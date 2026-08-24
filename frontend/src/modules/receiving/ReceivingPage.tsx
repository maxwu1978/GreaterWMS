import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/api/queryKeys";
import { fetchInboundOrderDetail, startReceiving } from "../../shared/api/receiving";
import { archiveInboundOrder, deleteInboundOrder, voidInboundOrder } from "../../shared/api/inboundOrders";
import { fetchClients } from "../../shared/api/clients";
import { fetchSetupProgress } from "../../shared/api/setup";
import {
  fetchInboundOrderListPage,
  ORDER_LIST_BATCH_SIZE,
} from "../../shared/api/orderLists";
import {
  fetchReceivingWorkbenchSummary,
  workbenchSummaryKeys,
} from "../../shared/api/workbenchSummaries";
import DataTable from "../../shared/components/DataTable";
import StatusBadge from "../../shared/components/StatusBadge";
import TaskCard from "../../shared/components/TaskCard";
import Pill from "../../shared/components/Pill";
import ReceivingFlow from "./ReceivingFlow";
import { AlertCircle, ArrowRight } from "lucide-react";
import { useI18n } from "../../shared/i18n";
import { useAuthStore } from "../../shared/hooks/useAuth";
import UpstreamActionLink from "../../shared/components/UpstreamActionLink";
import InboundOrderHistoryPanel from "./InboundOrderHistoryPanel";
import InboundOrderRecordStateBadge from "./InboundOrderRecordStateBadge";
import PackListImportPanel from "./PackListImportPanel";
import { checklistHref } from "../../shared/utils/checklistHref";
import {
  displayInboundReference,
  formatRecentActivityLabel,
  hasNonDefaultRecordState,
  isPutawayHandoffOrder,
  isReceivingStageOrder,
  isRecentlyChangedOrder,
  LAST_RECEIVING_ORDER_STORAGE_KEY,
  latestActivityTimestamp,
  operationalReasonsForOrder,
  packageLatestActivityTimestamp,
  packageMatchesOperationFilter,
  packageNeedsPrint,
  packageNeedsPutaway,
  packageNeedsReceivingAttention,
  packagePrimaryBlocker,
  packagePrimaryCode,
  packageRecommendedOwner,
  packageRecommendedOwnerLane,
  recommendedFilterForOrder,
  RECENT_ACTIVITY_WINDOW_HOURS,
  type ExceptionOwnerLane,
  type PackageOperationFilter,
  type QueueAction,
  type ReceivingPackageFocus,
  type SelectedReceiveOrder,
} from "./receivingWorkUtils";

const MOBILE_QUEUE_PRIORITY_FILTERS: PackageOperationFilter[] = [
  "supervisor_review",
  "package_open",
  "print_pending",
  "putaway_pending",
  "needs_action",
  "recently_changed",
];

export default function ReceivingPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryOrderId = searchParams.get("orderId") || "";
  const permissions = useAuthStore((s) => s.permissions);
  const jobTitle = useAuthStore((s) => s.jobTitle);
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"orders" | "receive">("orders");
  const [selectedReceiveOrder, setSelectedReceiveOrder] = useState<SelectedReceiveOrder | null>(null);
  const [selectedOrdersTableOrder, setSelectedOrdersTableOrder] = useState<any | null>(null);
  const [ordersSortField, setOrdersSortField] = useState<"order_number" | "status" | "client_id">("order_number");
  const [ordersSortDirection, setOrdersSortDirection] = useState<"asc" | "desc">("desc");
  const [ordersPage, setOrdersPage] = useState(1);
  const [showArchivedOrders, setShowArchivedOrders] = useState(false);
  const [lifecycleFilter, setLifecycleFilter] = useState<"all" | "active" | "archived" | "voided" | "completed">("active");
  const [operationFilter, setOperationFilter] = useState<PackageOperationFilter>("all");
  const [exceptionOwnerLane, setExceptionOwnerLane] = useState<ExceptionOwnerLane>("all");
  const [showAllSelectedOrderPackages, setShowAllSelectedOrderPackages] = useState(false);
  const ordersPageSize = 12;
  const recentCutoff = Date.now() - RECENT_ACTIVITY_WINDOW_HOURS * 60 * 60 * 1000;
  const serverLifecycleFilter = operationFilter === "all" ? lifecycleFilter : undefined;
  const serverOperationFilter = operationFilter === "all" ? undefined : operationFilter;
  const serverIncludeArchived = showArchivedOrders || lifecycleFilter === "archived";
  const serverOrderSortField = ordersSortField;

  const {
    data: orderPages,
    isLoading,
    fetchNextPage: fetchNextOrderBatch,
    hasNextPage: hasMoreOrderBatches,
    isFetchingNextPage: isFetchingNextOrderBatch,
  } = useInfiniteQuery({
    queryKey: queryKeys.inboundOrders.list(
      serverIncludeArchived,
      serverLifecycleFilter,
      serverOperationFilter,
      serverOrderSortField,
      ordersSortDirection,
    ),
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      fetchInboundOrderListPage({
        includeArchived: serverIncludeArchived,
        lifecycle: serverLifecycleFilter,
        operation: serverOperationFilter,
        recentHours: RECENT_ACTIVITY_WINDOW_HOURS,
        sortBy: serverOrderSortField,
        sortDirection: ordersSortDirection,
        offset: Number(pageParam || 0),
        limit: ORDER_LIST_BATCH_SIZE,
      }),
    getNextPageParam: (lastPage) => lastPage.nextOffset,
  });
  const orders = useMemo(
    () => orderPages?.pages.flatMap((page) => page.items) || [],
    [orderPages],
  );
  const { data: receivingWorkbenchSummary } = useQuery({
    queryKey: workbenchSummaryKeys.receiving,
    queryFn: fetchReceivingWorkbenchSummary,
  });
  const { data: selectedOrderDetail, isLoading: isLoadingSelectedOrderDetail } = useQuery({
    queryKey: queryKeys.inboundOrders.detail(selectedOrdersTableOrder?.id),
    enabled: !!selectedOrdersTableOrder?.id,
    queryFn: () => fetchInboundOrderDetail(selectedOrdersTableOrder.id),
  });

  const { data: setupProgress } = useQuery({
    queryKey: queryKeys.setup.progressFor("receiving"),
    queryFn: fetchSetupProgress,
  });

  const { data: clientsData } = useQuery({
    queryKey: queryKeys.clients.list("receiving-create"),
    queryFn: () => fetchClients(),
  });

  const clients = clientsData?.items || [];
  const clientMap = useMemo(
    () =>
      new Map(
        clients.map((client: any) => [
          client.id,
          client.name ? `${client.code || client.id} · ${client.name}` : client.code || client.id,
        ]),
      ),
    [clients],
  );
  const setupSteps = setupProgress?.steps || [];
  const requiredReceivingSteps = ["warehouse", "locations", "client", "skus"];
  const missingRequiredSteps = setupSteps.filter((step: any) => requiredReceivingSteps.includes(step.name) && !step.done);
  const receivingReady = missingRequiredSteps.length === 0;
  const hasOpenReceivingOrder = orders.some((order: any) => order.status === "receiving" && !order.archived);
  const canImportInbound = permissions.includes("*") || permissions.includes("inbound_orders.import");
  const canReceiveInbound = permissions.includes("*") || permissions.includes("receiving.execute");
  const canOpenReceivingFlow = canReceiveInbound && (receivingReady || hasOpenReceivingOrder);
  const receivingStageOrders = useMemo(
    () => orders.filter((order: any) => isReceivingStageOrder(order)),
    [orders],
  );
  const putawayHandoffOrders = useMemo(
    () => orders.filter((order: any) => isPutawayHandoffOrder(order)),
    [orders],
  );
  const readyToOpenOrders = useMemo(
    () => receivingStageOrders.filter((order: any) => ["expected", "arrived"].includes(order.status)),
    [receivingStageOrders],
  );
  const activeReceivingOrders = useMemo(
    () => receivingStageOrders.filter((order: any) => order.status === "receiving"),
    [receivingStageOrders],
  );
  const noActiveReceivingWork =
    readyToOpenOrders.length === 0 &&
    activeReceivingOrders.length === 0 &&
    putawayHandoffOrders.length === 0;
  const quietOrdersManagementView =
    noActiveReceivingWork &&
    !selectedOrdersTableOrder &&
    !showArchivedOrders &&
    lifecycleFilter === "active" &&
    operationFilter === "all";
  const launchSelectedOrderToFlow = (
    order: { id: string; status: string },
    packageFocus: ReceivingPackageFocus = null,
    options?: {
      packageId?: string | null;
      printPackageId?: string | null;
      packageNumber?: number | null;
    },
  ) => {
    const resolvedPackageFocus =
      packageFocus || (order.status === "receiving" ? "package_open" : null);
    setSelectedReceiveOrder({
      id: order.id,
      status: order.status,
      nonce: Date.now(),
      packageFocus: resolvedPackageFocus,
      packageId: options?.packageId || null,
      printPackageId: options?.printPackageId || null,
      packageNumber: options?.packageNumber || null,
    });
    setSelectedOrdersTableOrder(null);
    setActiveTab("receive");
    window.sessionStorage.setItem(
      LAST_RECEIVING_ORDER_STORAGE_KEY,
      JSON.stringify({
        id: order.id,
        status: order.status,
      }),
    );
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("orderId", order.id);
    setSearchParams(nextParams, { replace: true });
    requestAnimationFrame(() => {
      document.getElementById("receiving-flow")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const queueActionForOrder = (order: any, filter: PackageOperationFilter): QueueAction | null => {
    if (filter === "putaway_pending") {
      return (order.packages_putaway_pending || 0) > 0 ? { kind: "putaway" } : null;
    }
    if (filter === "print_pending") {
      return (order.internal_labels_print_pending || 0) > 0 ? { kind: "receive", focus: "print_pending" } : null;
    }
    if (filter === "supervisor_review") {
      if (!order.supervisor_review_needed) return null;
      if ((order.packages_open || 0) > 0 && (order.packages_dock_created || 0) > 0) {
        return { kind: "receive", focus: "dock_created" };
      }
      if ((order.internal_labels_print_pending || 0) > 0 && (order.packages_dock_created || 0) > 0) {
        return { kind: "receive", focus: "print_pending" };
      }
      if ((order.packages_putaway_pending || 0) > 0 && (order.packages_dock_created || 0) > 0) {
        return { kind: "putaway" };
      }
      return { kind: "detail" };
    }
    if (filter === "package_open") {
      return (order.packages_open || 0) > 0 ? { kind: "receive", focus: "package_open" } : null;
    }
    if (filter === "needs_action") {
      if ((order.packages_open || 0) > 0) return { kind: "receive", focus: "needs_action" };
      if ((order.internal_labels_print_pending || 0) > 0) return { kind: "receive", focus: "print_pending" };
      return null;
    }
    if (filter === "prebooked") {
      if ((order.packages_prebooked || 0) > 0 && (order.packages_open || 0) > 0) {
        return { kind: "receive", focus: "prebooked" };
      }
      if ((order.packages_prebooked || 0) > 0 && (order.internal_labels_print_pending || 0) > 0) {
        return { kind: "receive", focus: "print_pending" };
      }
      return null;
    }
    if (filter === "dock_created") {
      if ((order.packages_dock_created || 0) > 0 && (order.packages_open || 0) > 0) {
        return { kind: "receive", focus: "dock_created" };
      }
      if ((order.packages_dock_created || 0) > 0 && (order.internal_labels_print_pending || 0) > 0) {
        return { kind: "receive", focus: "print_pending" };
      }
      return null;
    }
    if (filter === "recently_changed") {
      if ((order.packages_open || 0) > 0) return { kind: "receive", focus: "needs_action" };
      if ((order.internal_labels_print_pending || 0) > 0) return { kind: "receive", focus: "print_pending" };
      if ((order.packages_putaway_pending || 0) > 0) return { kind: "putaway" };
      return { kind: "detail" };
    }
    return null;
  };

  const sendOrderToPutaway = (order: any) => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(
        "putaway.focusContext",
        JSON.stringify({
          source: "receiving-package-queue",
          orderId: order.id,
          orderNumber: order.order_number,
          referenceNumber: order.reference_number || "",
        }),
      );
    }
    navigate("/putaway");
  };

  const focusOrderInOrdersWorkspace = (order: any) => {
    setSelectedOrdersTableOrder(order);
    setActiveTab("orders");
    requestAnimationFrame(() => {
      document.getElementById("receiving-orders-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const runQueueAction = (order: any, filter: PackageOperationFilter) => {
    const action = queueActionForOrder(order, filter);
    if (!action) return;
    if (action.kind === "putaway") {
      sendOrderToPutaway(order);
      return;
    }
    if (action.kind === "detail") {
      navigate(`/receiving/orders/${order.id}`);
      return;
    }
    launchSelectedOrderToFlow(order, action.focus);
  };

  const startSelectedOrderMutation = useMutation({
    mutationFn: async (orderId: string) => startReceiving(orderId),
    onSuccess: async (_resp, orderId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.receivable() });
      await queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.receiving });
      launchSelectedOrderToFlow({ id: orderId, status: "receiving" });
    },
  });

  const archiveSelectedOrderMutation = useMutation({
    mutationFn: async ({ orderId, archived }: { orderId: string; archived: boolean }) =>
      archiveInboundOrder(orderId, archived),
    onSuccess: async (resp, variables) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(variables.orderId) });
      await queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.receiving });
      setSelectedOrdersTableOrder((current) => (current ? { ...current, ...resp.data } : current));
      if (variables.archived && !showArchivedOrders) {
        setSelectedOrdersTableOrder(null);
      }
    },
  });

  const voidSelectedOrderMutation = useMutation({
    mutationFn: async (orderId: string) => voidInboundOrder(orderId),
    onSuccess: async (resp, orderId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.detail(orderId) });
      await queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.receiving });
      setSelectedOrdersTableOrder((current) => (current ? { ...current, ...resp.data } : current));
    },
  });

  const deleteSelectedOrderMutation = useMutation({
    mutationFn: async (orderId: string) => deleteInboundOrder(orderId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
      await queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.receiving });
      setSelectedOrdersTableOrder(null);
    },
  });

  const columns = [
    {
      key: "__row_number",
      header: t("common.rowNumber", "No."),
      className: "w-[72px] text-[#7f8d98]",
      render: (_row: any, index: number) => index + 1,
    },
    { key: "order_number", header: t("common.poNumber", "PO #"), sortable: true },
    {
      key: "status",
      header: t("common.status", "Status"),
      sortable: true,
      render: (row: any) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={row.status} />
          {hasNonDefaultRecordState(row) ? <InboundOrderRecordStateBadge order={row} /> : null}
        </div>
      ),
    },
    {
      key: "client_id",
      header: t("common.client", "Client"),
      sortable: true,
      render: (row: any) => clientMap.get(row.client_id) || row.client_id,
    },
    {
      key: "package_work",
      header: t("receiving.packageWorkColumn", "Package work"),
      render: (row: any) => (
        <div className="flex flex-wrap gap-1.5">
          {row.supervisor_review_needed ? (
            <span className="rounded-full bg-[#fff0e8] px-2.5 py-0.5 text-xs font-medium text-[#9a4b18]">
              {t("receiving.packageWorkSupervisorReviewCount", "Supervisor review")}
            </span>
          ) : null}
          {isRecentlyChangedOrder(row, recentCutoff) ? (
            <span className="rounded-full bg-[#eaf1fb] px-2.5 py-0.5 text-xs font-medium text-[#355a84]">
              {t("receiving.packageWorkRecentlyChanged", "Changed recently")}
            </span>
          ) : null}
          {row.packages_open > 0 ? (
            <span className="rounded-full bg-[#eef3f6] px-2.5 py-0.5 text-xs font-medium text-[#24507a]">
              {t("receiving.packageWorkOpenCount", "{count} open", { count: String(row.packages_open || 0) })}
            </span>
          ) : null}
          {row.packages_putaway_pending > 0 ? (
            <span className="rounded-full bg-[#fff6e6] px-2.5 py-0.5 text-xs font-medium text-[#91621a]">
              {t("receiving.packageWorkPutawayCount", "{count} putaway", {
                count: String(row.packages_putaway_pending || 0),
              })}
            </span>
          ) : null}
          {row.packages_prebooked > 0 ? (
            <span className="rounded-full bg-[#eef7ef] px-2.5 py-0.5 text-xs font-medium text-[#2f6c43]">
              {t("receiving.packageWorkPrebookedCount", "{count} pre-booked", {
                count: String(row.packages_prebooked || 0),
              })}
            </span>
          ) : null}
          {row.packages_dock_created > 0 ? (
            <span className="rounded-full bg-[#edf2f7] px-2.5 py-0.5 text-xs font-medium text-[#425466]">
              {t("receiving.packageWorkDockCreatedCount", "{count} dock-opened", {
                count: String(row.packages_dock_created || 0),
              })}
            </span>
          ) : null}
          {row.internal_labels_print_pending > 0 ? (
            <span className="rounded-full bg-[#f5efe5] px-2.5 py-0.5 text-xs font-medium text-[#6c5a39]">
              {t("receiving.packageWorkPrintPendingCount", "{count} print", {
                count: String(row.internal_labels_print_pending || 0),
              })}
            </span>
          ) : null}
          {row.total_packages === 0 ? (
            <span className="text-xs text-[#7f8d98]">
              {t("receiving.packageWorkEmpty", "No packages yet")}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "reference_number",
      header: t("receiving.externalReferenceColumn", "External ref"),
      render: (row: any) => (
        <span className={displayInboundReference(row) === "—" ? "text-[#9aa6af]" : undefined}>
          {displayInboundReference(row)}
        </span>
      ),
    },
  ];

  const lifecycleScopedOrders = useMemo(
    () =>
      orders.filter((order: any) => {
        if (lifecycleFilter === "all") return true;
        if (lifecycleFilter === "active") return isReceivingStageOrder(order);
        if (lifecycleFilter === "archived") return order.archived;
        if (lifecycleFilter === "voided") return order.voided;
        if (lifecycleFilter === "completed") return order.status === "completed" && !order.archived && !order.voided;
        return true;
      }),
    [lifecycleFilter, orders],
  );

  const getOrderComparable = (row: any) => {
    if (ordersSortField === "client_id") {
      return (clientMap.get(row.client_id) || row.client_id || "").toString().toLowerCase();
    }
    return (row?.[ordersSortField] || "").toString().toLowerCase();
  };

  const sortOrdersForSurface = (input: any[]) => {
    const direction = ordersSortDirection === "asc" ? 1 : -1;
    return [...input].sort((a: any, b: any) => {
      const aValue = getOrderComparable(a);
      const bValue = getOrderComparable(b);
      if (aValue < bValue) return -1 * direction;
      if (aValue > bValue) return 1 * direction;
      return 0;
    });
  };

  const operationScopedOrders = useMemo(() => {
    const baseOrders =
      operationFilter === "putaway_pending" ? putawayHandoffOrders : lifecycleScopedOrders;
    return baseOrders.filter((order: any) => {
      if (operationFilter === "all") return true;
      if (operationFilter === "needs_action") {
        return (order.packages_needing_action || 0) > 0 || (order.internal_labels_print_pending || 0) > 0;
      }
      if (operationFilter === "supervisor_review") return !!order.supervisor_review_needed;
      if (operationFilter === "package_open") return (order.packages_open || 0) > 0;
      if (operationFilter === "putaway_pending") return (order.packages_putaway_pending || 0) > 0;
      if (operationFilter === "print_pending") return (order.internal_labels_print_pending || 0) > 0;
      if (operationFilter === "prebooked") return (order.packages_prebooked || 0) > 0;
      if (operationFilter === "dock_created") return (order.packages_dock_created || 0) > 0;
      if (operationFilter === "recently_changed") return isRecentlyChangedOrder(order, recentCutoff);
      return true;
    });
  }, [lifecycleScopedOrders, operationFilter, putawayHandoffOrders]);
  const getSupervisorReviewPriority = (order: any) => {
    const mixedOrigin = (order.packages_prebooked || 0) > 0 && (order.packages_dock_created || 0) > 0;
    return (
      (mixedOrigin ? 5000 : 0) +
      Number(order.packages_open || 0) * 100 +
      Number(order.internal_labels_print_pending || 0) * 80 +
      Number(order.packages_putaway_pending || 0) * 60 +
      Number(order.packages_dock_created || 0) * 20 +
      Number(order.total_packages || 0)
    );
  };
  const sortedOrders = useMemo(() => {
    if (operationFilter === "recently_changed") {
      return [...operationScopedOrders].sort((a: any, b: any) => {
        const aTime = latestActivityTimestamp(a);
        const bTime = latestActivityTimestamp(b);
        return bTime - aTime;
      });
    }
    if (operationFilter === "supervisor_review") {
      return [...operationScopedOrders].sort((a: any, b: any) => {
        const priorityDelta = getSupervisorReviewPriority(b) - getSupervisorReviewPriority(a);
        if (priorityDelta !== 0) return priorityDelta;
        const activityDelta = latestActivityTimestamp(b) - latestActivityTimestamp(a);
        if (activityDelta !== 0) return activityDelta;
        return 0;
      });
    }
    return sortOrdersForSurface(operationScopedOrders);
  }, [operationFilter, operationScopedOrders, ordersSortDirection, ordersSortField, clientMap]);
  const lifecycleSortedOrders = useMemo(
    () => sortOrdersForSurface(lifecycleScopedOrders),
    [lifecycleScopedOrders, ordersSortDirection, ordersSortField, clientMap],
  );
  const lifecycleCounts = useMemo(
    () => ({
      active: receivingWorkbenchSummary?.active_orders ?? receivingStageOrders.length,
      all: receivingWorkbenchSummary?.total_orders ?? orders.length,
      archived: receivingWorkbenchSummary?.archived_orders ?? orders.filter((order: any) => order.archived).length,
      voided: receivingWorkbenchSummary?.voided_orders ?? orders.filter((order: any) => order.voided).length,
      completed:
        receivingWorkbenchSummary?.completed_orders ??
        orders.filter((order: any) => order.status === "completed" && !order.archived && !order.voided).length,
    }),
    [orders, receivingStageOrders, receivingWorkbenchSummary],
  );
  const operationCounts = useMemo(
    () => ({
      all: receivingStageOrders.length,
      needs_action: receivingStageOrders.filter((order: any) => (order.packages_needing_action || 0) > 0 || (order.internal_labels_print_pending || 0) > 0).length,
      supervisor_review: receivingStageOrders.filter((order: any) => !!order.supervisor_review_needed).length,
      package_open: receivingStageOrders.filter((order: any) => (order.packages_open || 0) > 0).length,
      putaway_pending: putawayHandoffOrders.length,
      print_pending: receivingStageOrders.filter((order: any) => (order.internal_labels_print_pending || 0) > 0).length,
      prebooked: receivingStageOrders.filter((order: any) => (order.packages_prebooked || 0) > 0).length,
      dock_created: receivingStageOrders.filter((order: any) => (order.packages_dock_created || 0) > 0).length,
      recently_changed: receivingStageOrders.filter((order: any) => isRecentlyChangedOrder(order, recentCutoff)).length,
    }),
    [putawayHandoffOrders, receivingStageOrders, recentCutoff],
  );
  const nextQueueAction = useMemo(() => {
    if (operationFilter === "all") return null;
    const nextOrder = sortedOrders.find((order: any) => queueActionForOrder(order, operationFilter));
    if (!nextOrder) return null;
    return {
      order: nextOrder,
      action: queueActionForOrder(nextOrder, operationFilter) as QueueAction,
    };
  }, [operationFilter, sortedOrders]);
  const bestOrderForOperation = (filter: PackageOperationFilter) => {
    const baseOrders =
      filter === "putaway_pending"
        ? sortOrdersForSurface(putawayHandoffOrders)
        : lifecycleSortedOrders;
    const filtered = baseOrders.filter((order: any) => {
      if (filter === "supervisor_review") return !!order.supervisor_review_needed;
      if (filter === "package_open") return (order.packages_open || 0) > 0;
      if (filter === "putaway_pending") return (order.packages_putaway_pending || 0) > 0;
      if (filter === "print_pending") return (order.internal_labels_print_pending || 0) > 0;
      if (filter === "prebooked") return (order.packages_prebooked || 0) > 0;
      if (filter === "dock_created") return (order.packages_dock_created || 0) > 0;
      if (filter === "recently_changed") return isRecentlyChangedOrder(order, recentCutoff);
      if (filter === "needs_action") return (order.packages_needing_action || 0) > 0 || (order.internal_labels_print_pending || 0) > 0;
      return true;
    });
    if (filter === "recently_changed") {
      filtered.sort((a: any, b: any) => (Date.parse(b.latest_activity_at || "") || 0) - (Date.parse(a.latest_activity_at || "") || 0));
    } else if (filter === "supervisor_review") {
      filtered.sort((a: any, b: any) => {
        const priorityDelta = getSupervisorReviewPriority(b) - getSupervisorReviewPriority(a);
        if (priorityDelta !== 0) return priorityDelta;
        return (Date.parse(b.latest_activity_at || "") || 0) - (Date.parse(a.latest_activity_at || "") || 0);
      });
    }
    return filtered.find((order: any) => queueActionForOrder(order, filter)) || null;
  };
  const mobileSuggestedQueueAction = (() => {
    if (nextQueueAction) {
      return {
        filter: operationFilter,
        order: nextQueueAction.order,
        action: nextQueueAction.action,
      };
    }

    for (const filter of MOBILE_QUEUE_PRIORITY_FILTERS) {
      const order = bestOrderForOperation(filter);
      const action = order ? queueActionForOrder(order, filter) : null;
      if (order && action) {
        return { filter, order, action };
      }
    }
    return null;
  })();
  const supervisorExceptionOrders = (() => {
    const candidates = [
      { order: bestOrderForOperation("supervisor_review"), filter: "supervisor_review" as PackageOperationFilter },
      { order: bestOrderForOperation("recently_changed"), filter: "recently_changed" as PackageOperationFilter },
      { order: bestOrderForOperation("print_pending"), filter: "print_pending" as PackageOperationFilter },
      { order: bestOrderForOperation("putaway_pending"), filter: "putaway_pending" as PackageOperationFilter },
    ].filter((entry) => entry.order) as Array<{ order: any; filter: PackageOperationFilter }>;
    const seen = new Set<string>();
    return candidates.filter((entry) => {
      if (seen.has(entry.order.id)) return false;
      seen.add(entry.order.id);
      return true;
    });
  })();
  const { data: supervisorExceptionDetails, isLoading: isLoadingSupervisorExceptionDetails } = useQuery({
    queryKey: queryKeys.receiving.supervisorExceptions(supervisorExceptionOrders.map((entry) => entry.order.id)),
    enabled: supervisorExceptionOrders.length > 0,
    queryFn: async () =>
      Promise.all(
        supervisorExceptionOrders.map(async (entry) => ({
          ...entry,
          detail: await fetchInboundOrderDetail(entry.order.id),
        })),
      ),
  });
  const supervisorExceptionPackages = useMemo(() => {
    if (!supervisorExceptionDetails?.length) return [];
    return supervisorExceptionDetails
      .flatMap((entry: any) =>
        (entry.detail?.lines || []).flatMap((line: any) =>
          (line.packages || []).map((pkg: any) => ({
            ...pkg,
            line_id: line.line_id,
            line_number: line.line_number,
            sku_code: line.sku_code,
            sku_name: line.sku_name,
            order_id: entry.order.id,
            order_number: entry.order.order_number,
            reference_number: entry.order.reference_number,
            source_filter: entry.filter,
          })),
        ),
      )
      .filter((pkg: any) => {
        const latestTimestamp = packageLatestActivityTimestamp(pkg);
        const stale = latestTimestamp > 0 && latestTimestamp < recentCutoff;
        return (
          packageNeedsReceivingAttention(pkg) ||
          packageNeedsPrint(pkg) ||
          packageNeedsPutaway(pkg) ||
          pkg?.damaged_qty > 0 ||
          !packagePrimaryCode(pkg) ||
          stale
        );
      })
      .sort((a: any, b: any) => {
        const score = (pkg: any) => {
          const latestTimestamp = packageLatestActivityTimestamp(pkg);
          const stale = latestTimestamp > 0 && latestTimestamp < recentCutoff;
          return (
            (pkg?.source_filter === "supervisor_review" ? 600 : 0) +
            (pkg?.source_filter === "recently_changed" ? 420 : 0) +
            (packageNeedsReceivingAttention(pkg) ? 360 : 0) +
            (pkg?.package_origin === "dock_created" ? 120 : 0) +
            (packageNeedsPrint(pkg) ? 260 : 0) +
            (packageNeedsPutaway(pkg) ? 240 : 0) +
            (pkg?.damaged_qty > 0 ? 160 : 0) +
            (!packagePrimaryCode(pkg) ? 140 : 0) +
            (stale ? 110 : 0)
          );
        };
        const scoreDelta = score(b) - score(a);
        if (scoreDelta !== 0) return scoreDelta;
        return packageLatestActivityTimestamp(b) - packageLatestActivityTimestamp(a);
      })
      .slice(0, 6);
  }, [supervisorExceptionDetails, recentCutoff]);
  const supervisorExceptionLaneCounts = useMemo(
    () => ({
      all: supervisorExceptionPackages.length,
      receiving: supervisorExceptionPackages.filter((pkg: any) => packageRecommendedOwnerLane(pkg) === "receiving").length,
      print: supervisorExceptionPackages.filter((pkg: any) => packageRecommendedOwnerLane(pkg) === "print").length,
      putaway: supervisorExceptionPackages.filter((pkg: any) => packageRecommendedOwnerLane(pkg) === "putaway").length,
      review: supervisorExceptionPackages.filter((pkg: any) => packageRecommendedOwnerLane(pkg) === "review").length,
    }),
    [supervisorExceptionPackages],
  );
  const visibleSupervisorExceptionPackages = useMemo(() => {
    if (exceptionOwnerLane === "all") return supervisorExceptionPackages;
    return supervisorExceptionPackages.filter((pkg: any) => packageRecommendedOwnerLane(pkg) === exceptionOwnerLane);
  }, [exceptionOwnerLane, supervisorExceptionPackages]);
  const openOperationQueue = (filter: PackageOperationFilter) => {
    setOperationFilter(filter);
    setOrdersPage(1);
    const nextOrder = bestOrderForOperation(filter);
    if (nextOrder) runQueueAction(nextOrder, filter);
  };
  const packageRollup = useMemo(
    () => ({
      open:
        receivingWorkbenchSummary?.packages_open ??
        receivingStageOrders.reduce((sum: number, order: any) => sum + Number(order.packages_open || 0), 0),
      supervisorReview: receivingStageOrders.reduce((sum: number, order: any) => sum + (order.supervisor_review_needed ? 1 : 0), 0),
      putawayPending:
        receivingWorkbenchSummary?.packages_putaway_pending ??
        putawayHandoffOrders.reduce((sum: number, order: any) => sum + Number(order.packages_putaway_pending || 0), 0),
      printPending:
        receivingWorkbenchSummary?.internal_labels_print_pending ??
        receivingStageOrders.reduce((sum: number, order: any) => sum + Number(order.internal_labels_print_pending || 0), 0),
      prebooked: receivingStageOrders.reduce((sum: number, order: any) => sum + Number(order.packages_prebooked || 0), 0),
      dockCreated: receivingStageOrders.reduce((sum: number, order: any) => sum + Number(order.packages_dock_created || 0), 0),
      recentlyChanged: receivingStageOrders.reduce((sum: number, order: any) => (isRecentlyChangedOrder(order, recentCutoff) ? sum + 1 : sum), 0),
    }),
    [putawayHandoffOrders, receivingStageOrders, receivingWorkbenchSummary, recentCutoff],
  );
  const handoffLanes = useMemo(
    () =>
      ([
        {
          filter: "supervisor_review" as PackageOperationFilter,
          title: t("receiving.handoffSupervisorReviewTitle", "Supervisor review"),
          empty: t("receiving.handoffSupervisorReviewEmpty", "No supervisor review handoff is waiting right now."),
          action: t("receiving.queueActionReview", "Review"),
        },
        {
          filter: "recently_changed" as PackageOperationFilter,
          title: t("receiving.handoffRecentlyChangedTitle", "Recently changed orders"),
          empty: t("receiving.handoffRecentlyChangedEmpty", "No recently changed inbound orders need handoff right now."),
          action: t("receiving.queueActionReview", "Review"),
        },
      ] as const).map((lane) => {
        const order = bestOrderForOperation(lane.filter);
        return {
          ...lane,
          order,
          actionSpec: order ? queueActionForOrder(order, lane.filter) : null,
          reasons: order ? operationalReasonsForOrder(order, recentCutoff, t).slice(0, 3) : [],
        };
      }),
    [bestOrderForOperation, recentCutoff, t],
  );
  const selectedOrderPackages = useMemo(() => {
    if (!selectedOrderDetail?.lines?.length) return [];
    return selectedOrderDetail.lines
      .flatMap((line: any) =>
        (line.packages || []).map((pkg: any) => ({
          ...pkg,
          line_id: line.line_id,
          line_number: line.line_number,
          sku_code: line.sku_code,
          sku_name: line.sku_name,
        })),
      )
      .sort((a: any, b: any) => {
        const score = (pkg: any) =>
          (packageNeedsReceivingAttention(pkg) ? 500 : 0) +
          (packageNeedsPrint(pkg) ? 320 : 0) +
          (packageNeedsPutaway(pkg) ? 300 : 0) +
          (pkg?.package_origin === "dock_created" ? 30 : 0) +
          (pkg?.status === "expected" ? 10 : 0);
        const scoreDelta = score(b) - score(a);
        if (scoreDelta !== 0) return scoreDelta;
        const activityDelta = packageLatestActivityTimestamp(b) - packageLatestActivityTimestamp(a);
        if (activityDelta !== 0) return activityDelta;
        return Number(a.package_number || 0) - Number(b.package_number || 0);
      });
  }, [selectedOrderDetail]);
  const selectedOrderActionablePackages = useMemo(
    () =>
      selectedOrderPackages.filter(
        (pkg: any) => packageNeedsReceivingAttention(pkg) || packageNeedsPrint(pkg) || packageNeedsPutaway(pkg),
      ),
    [selectedOrderPackages],
  );
  const selectedOrderDispatchPackages = useMemo(() => {
    const matching = selectedOrderActionablePackages.filter((pkg: any) =>
      packageMatchesOperationFilter(pkg, operationFilter, recentCutoff),
    );
    if (matching.length > 0) return matching;
    return selectedOrderActionablePackages;
  }, [selectedOrderActionablePackages, operationFilter, recentCutoff]);
  const selectedOrderVisiblePackages = useMemo(
    () =>
      showAllSelectedOrderPackages
        ? selectedOrderDispatchPackages
        : selectedOrderDispatchPackages.slice(0, 4),
    [selectedOrderDispatchPackages, showAllSelectedOrderPackages],
  );
  const selectedOrderRecommendedFilter = selectedOrdersTableOrder
    ? recommendedFilterForOrder(selectedOrdersTableOrder, recentCutoff)
    : null;
  const selectedOrderRecommendedAction =
    selectedOrdersTableOrder && selectedOrderRecommendedFilter
      ? queueActionForOrder(selectedOrdersTableOrder, selectedOrderRecommendedFilter)
      : null;
  const selectedOrderHasSecondaryActions = Boolean(
    selectedOrdersTableOrder?.can_archive ||
      selectedOrdersTableOrder?.can_void ||
      selectedOrdersTableOrder?.can_delete,
  );
  const packagePrimaryActionKind = (pkg: any): "receiving" | "print" | "putaway" | null => {
    if (packageNeedsReceivingAttention(pkg)) return "receiving";
    if (packageNeedsPrint(pkg)) return "print";
    if (packageNeedsPutaway(pkg)) return "putaway";
    return null;
  };

  const openPackageReceiving = (pkg: any) => {
    if (!selectedOrdersTableOrder) return;
    openPackageReceivingForOrder(selectedOrdersTableOrder, pkg);
  };

  const openPackageReceivingForOrder = (order: any, pkg: any) => {
    if (!order) return;
    launchSelectedOrderToFlow(
      { id: order.id, status: order.status },
      "needs_action",
      {
        packageId: pkg.id,
        packageNumber: pkg.package_number || null,
      },
    );
  };

  const openPackagePrint = (pkg: any) => {
    if (!selectedOrdersTableOrder) return;
    openPackagePrintForOrder(selectedOrdersTableOrder, pkg);
  };

  const openPackagePrintForOrder = (order: any, pkg: any) => {
    if (!order) return;
    launchSelectedOrderToFlow(
      { id: order.id, status: order.status },
      "print_pending",
      {
        packageId: pkg.id,
        printPackageId: pkg.id,
        packageNumber: pkg.package_number || null,
      },
    );
  };

  const openPackagePutaway = (pkg: any) => {
    const openTask = (pkg?.downstream_tasks || []).find((task: any) => task?.status !== "completed");
    if (!selectedOrdersTableOrder || !openTask) return;
    openPackagePutawayForOrder(selectedOrdersTableOrder, pkg);
  };

  const openPackagePutawayForOrder = (order: any, pkg: any) => {
    const openTask = (pkg?.downstream_tasks || []).find((task: any) => task?.status !== "completed");
    if (!order || !openTask) return;
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(
        "putaway.focusContext",
        JSON.stringify({
          source: "receiving-package-dispatch",
          orderId: order.id,
          orderNumber: order.order_number,
          referenceNumber: order.reference_number || "",
          handlingUnitCode: openTask.handling_unit_code || null,
          taskId: openTask.id || null,
        }),
      );
    }
    navigate("/putaway");
  };
  const totalOrdersPages = Math.max(1, Math.ceil(sortedOrders.length / ordersPageSize));
  const pagedOrders = useMemo(() => {
    const start = (ordersPage - 1) * ordersPageSize;
    return sortedOrders.slice(start, start + ordersPageSize);
  }, [ordersPage, ordersPageSize, sortedOrders]);

  useEffect(() => {
    setOrdersPage((current) => Math.min(current, totalOrdersPages));
  }, [totalOrdersPages]);

  useEffect(() => {
    setShowAllSelectedOrderPackages(false);
  }, [selectedOrdersTableOrder?.id, operationFilter]);

  useEffect(() => {
    const pendingFocus = sessionStorage.getItem("receiving.focusContext");
    if (pendingFocus && orders.length > 0) {
      try {
        const parsed = JSON.parse(pendingFocus);
        const matched = orders.find((order: any) => order.id === parsed.orderId);
        if (matched) {
          setSelectedReceiveOrder({
            id: matched.id,
            status: matched.status,
            nonce: Date.now(),
            packageFocus: parsed.target === "print" ? "print_pending" : parsed.target === "package_open" ? "package_open" : null,
            packageId: parsed.target === "package" ? parsed.packageId || null : null,
            printPackageId: parsed.target === "print" ? parsed.packageId || null : null,
            packageNumber: parsed.packageNumber || null,
          });
          setSelectedOrdersTableOrder(null);
          setActiveTab("receive");
          sessionStorage.removeItem("receiving.focusContext");
          sessionStorage.removeItem("receiving.selectedOrderId");
          return;
        }
        sessionStorage.removeItem("receiving.focusContext");
      } catch {
        sessionStorage.removeItem("receiving.focusContext");
      }
    }

    const pendingOrderId = sessionStorage.getItem("receiving.selectedOrderId");
    let rememberedOrder: { id: string; status: string } | null = null;
    try {
      const stored = sessionStorage.getItem(LAST_RECEIVING_ORDER_STORAGE_KEY);
      rememberedOrder = stored ? JSON.parse(stored) : null;
    } catch {
      sessionStorage.removeItem(LAST_RECEIVING_ORDER_STORAGE_KEY);
    }

    const targetOrderId = queryOrderId || pendingOrderId || rememberedOrder?.id || "";
    if (!targetOrderId || orders.length === 0) return;
    const matched = orders.find((order: any) => order.id === targetOrderId);
    if (!matched || !isReceivingStageOrder(matched)) {
      if (pendingOrderId === targetOrderId) {
        sessionStorage.removeItem("receiving.selectedOrderId");
      }
      if (rememberedOrder?.id === targetOrderId) {
        sessionStorage.removeItem(LAST_RECEIVING_ORDER_STORAGE_KEY);
      }
      return;
    }
    if (activeTab === "receive" && selectedReceiveOrder?.id === matched.id) {
      sessionStorage.removeItem("receiving.selectedOrderId");
      return;
    }
    setSelectedReceiveOrder({
      id: matched.id,
      status: matched.status,
      nonce: Date.now(),
      packageFocus: matched.status === "receiving" ? "package_open" : null,
      packageId: null,
      printPackageId: null,
      packageNumber: null,
    });
    setSelectedOrdersTableOrder(null);
    setActiveTab("receive");
    sessionStorage.removeItem("receiving.selectedOrderId");
  }, [activeTab, orders, queryOrderId, selectedReceiveOrder?.id]);

  const operationFilterSummary = (filter: PackageOperationFilter) => {
    switch (filter) {
      case "needs_action":
        return t(
          "receiving.operationFocusNeedsAction",
          "Stay on the next order that still has package work or labels waiting to print.",
        );
      case "supervisor_review":
        return t(
          "receiving.operationFocusSupervisorReview",
          "Review the inbound orders whose dock-opened packages still need operator follow-through, printing, or downstream storage.",
        );
      case "package_open":
        return t(
          "receiving.operationFocusPackageOpen",
          "Jump straight into the next order that still has packages open at the dock.",
        );
      case "putaway_pending":
        return t(
          "receiving.operationFocusPutawayPending",
          "These inbound orders have left receiving. Open the putaway board to finish storage work.",
        );
      case "print_pending":
        return t(
          "receiving.operationFocusPrintPending",
          "These orders already issued internal labels and still need label printing.",
        );
      case "prebooked":
        return t(
          "receiving.operationFocusPrebooked",
          "Keep the team on the upstream-planned packages that are already waiting on the dock.",
        );
      case "dock_created":
        return t(
          "receiving.operationFocusDockCreated",
          "Keep the team on the packages that were opened manually during dock intake.",
        );
      case "recently_changed":
        return t(
          "receiving.operationFocusRecentlyChanged",
          "Review the inbound orders whose package or label state changed most recently.",
        );
      default:
        return "";
    }
  };

  const operationActionLabel = (filter: PackageOperationFilter, action: QueueAction) => {
    if (action.kind === "putaway") {
      return t("receiving.operationActionPutaway", "Open putaway board");
    }
    if (action.kind === "detail") {
      return filter === "supervisor_review"
        ? t("receiving.operationActionSupervisorReview", "Review supervisor exceptions")
        : t("receiving.operationActionReview", "Review latest package activity");
    }
    if (filter === "print_pending") {
      return t("receiving.operationActionPrintPending", "Open next print-ready receipt");
    }
    return t("receiving.operationActionReceive", "Continue receiving");
  };
  const selectedOrderMobilePackage = selectedOrderDispatchPackages[0] || null;
  const selectedOrderMobileActionKind = selectedOrderMobilePackage
    ? packagePrimaryActionKind(selectedOrderMobilePackage)
    : null;
  const selectedOrderMobileTitle = selectedOrderMobilePackage
    ? selectedOrderMobileActionKind === "receiving"
      ? t("receiving.mobileSelectedActionReceiveTitle", "Finish Package {number} receiving", {
          number: String(selectedOrderMobilePackage.package_number || 1),
        })
      : selectedOrderMobileActionKind === "print"
        ? t("receiving.mobileSelectedActionPrintTitle", "Print Package {number} label", {
            number: String(selectedOrderMobilePackage.package_number || 1),
          })
        : selectedOrderMobileActionKind === "putaway"
          ? t("receiving.mobileSelectedActionPutawayTitle", "Send Package {number} to putaway", {
              number: String(selectedOrderMobilePackage.package_number || 1),
            })
          : t("receiving.mobileSelectedActionReviewTitle", "Review this inbound order")
    : selectedOrderRecommendedAction && selectedOrderRecommendedFilter
      ? operationActionLabel(selectedOrderRecommendedFilter, selectedOrderRecommendedAction)
      : t("receiving.mobileSelectedActionReviewTitle", "Review this inbound order");
  const selectedOrderMobileBody = selectedOrderMobilePackage
    ? selectedOrderMobileActionKind === "receiving"
      ? t(
          "receiving.mobileSelectedActionReceiveBody",
          "{sku} still needs receiving checks. Finish this before printing labels or sending stock to putaway.",
          { sku: selectedOrderMobilePackage.sku_code || "SKU" },
        )
      : selectedOrderMobileActionKind === "print"
        ? t(
            "receiving.mobileSelectedActionPrintBody",
            "{sku} is received. Print the internal label before downstream movement.",
            { sku: selectedOrderMobilePackage.sku_code || "SKU" },
          )
        : selectedOrderMobileActionKind === "putaway"
          ? t(
              "receiving.mobileSelectedActionPutawayBody",
              "{sku} is received and ready for putaway handoff.",
              { sku: selectedOrderMobilePackage.sku_code || "SKU" },
            )
          : t("receiving.mobileSelectedActionReviewBody", "No open package action is blocking this inbound.")
    : t("receiving.mobileSelectedActionOrderBody", "Open the focused order and continue the recommended receiving work.");
  const selectedOrderMobilePrimaryLabel = selectedOrderMobilePackage
    ? selectedOrderMobileActionKind === "receiving"
      ? t("receiving.mobileSelectedActionReceiveCta", "Continue receiving")
      : selectedOrderMobileActionKind === "print"
        ? t("receiving.mobileSelectedActionPrintCta", "Print label")
        : selectedOrderMobileActionKind === "putaway"
          ? t("receiving.mobileSelectedActionPutawayCta", "Open putaway")
          : t("receiving.mobileSelectedActionReviewCta", "Open full detail")
    : selectedOrderRecommendedAction && selectedOrderRecommendedFilter
      ? operationActionLabel(selectedOrderRecommendedFilter, selectedOrderRecommendedAction)
      : t("receiving.mobileSelectedActionReviewCta", "Open full detail");
  const runSelectedOrderMobilePrimaryAction = () => {
    if (selectedOrderMobilePackage) {
      if (selectedOrderMobileActionKind === "receiving") {
        openPackageReceiving(selectedOrderMobilePackage);
        return;
      }
      if (selectedOrderMobileActionKind === "print") {
        openPackagePrint(selectedOrderMobilePackage);
        return;
      }
      if (selectedOrderMobileActionKind === "putaway") {
        openPackagePutaway(selectedOrderMobilePackage);
        return;
      }
    }
    if (selectedOrdersTableOrder && selectedOrderRecommendedAction && selectedOrderRecommendedFilter) {
      runQueueAction(selectedOrdersTableOrder, selectedOrderRecommendedFilter);
      return;
    }
    if (selectedOrdersTableOrder) {
      navigate(`/receiving/orders/${selectedOrdersTableOrder.id}`);
    }
  };
  const mobileFilterPillClass =
    "min-w-0 w-full justify-between whitespace-normal text-left normal-case leading-4 tracking-[0.04em]";
  const firstMissingReceivingStep = missingRequiredSteps[0];
  const mobileReadyOrder = readyToOpenOrders[0] || null;
  const mobileLiveOrder = activeReceivingOrders[0] || null;
  const mobilePrimaryAction: {
    state: "ready" | "blocked" | "empty";
    eyebrow: string;
    title: string;
    body: string;
    primaryLabel: string;
    href?: string;
    onAction?: () => void;
    context?: string;
    disabled?: boolean;
  } = (() => {
    if (!canReceiveInbound) {
      return {
        state: "blocked",
        eyebrow: t("receiving.mobilePrimaryBlockedEyebrow", "Next step"),
        title: t("receiving.mobilePrimaryNoPermissionTitle", "Receiving work is not available for this login"),
        body: t(
          "receiving.mobilePrimaryNoPermissionBody",
          "Go back to the dashboard and ask an admin to assign receiving permission before scanning freight.",
        ),
        primaryLabel: t("receiving.mobilePrimaryBackDashboard", "Back to dashboard"),
        href: "/dashboard",
        context: "",
        disabled: false,
      };
    }

    if (mobileSuggestedQueueAction) {
      return {
        state: "ready",
        eyebrow: t("receiving.mobilePrimaryReadyEyebrow", "Do this now"),
        title: operationActionLabel(mobileSuggestedQueueAction.filter, mobileSuggestedQueueAction.action),
        body: t("receiving.mobilePrimaryReadyBody", "Work on {order} first.", {
          order: mobileSuggestedQueueAction.order.order_number,
        }),
        primaryLabel: operationActionLabel(mobileSuggestedQueueAction.filter, mobileSuggestedQueueAction.action),
        onAction: () => runQueueAction(mobileSuggestedQueueAction.order, mobileSuggestedQueueAction.filter),
        context: t("receiving.queueFocusLatestActivity", "Latest activity: {timeAgo}", {
          timeAgo: formatRecentActivityLabel(mobileSuggestedQueueAction.order, t),
        }),
        disabled: false,
      };
    }

    if (mobileLiveOrder) {
      return {
        state: "ready",
        eyebrow: t("receiving.mobilePrimaryReadyEyebrow", "Do this now"),
        title: t("receiving.mobilePrimaryContinueTitle", "Continue the open receiving order"),
        body: t("receiving.mobilePrimaryReadyBody", "Work on {order} first.", {
          order: mobileLiveOrder.order_number,
        }),
        primaryLabel: t("receiving.tableSelectionReceivingAction", "Continue receiving"),
        onAction: () => launchSelectedOrderToFlow(mobileLiveOrder),
        context: t("receiving.queueFocusLatestActivity", "Latest activity: {timeAgo}", {
          timeAgo: formatRecentActivityLabel(mobileLiveOrder, t),
        }),
        disabled: false,
      };
    }

    if (mobileReadyOrder) {
      const canStartReadyOrder = canOpenReceivingFlow && !startSelectedOrderMutation.isPending;
      return {
        state: canStartReadyOrder ? "ready" : "blocked",
        eyebrow: canStartReadyOrder
          ? t("receiving.mobilePrimaryReadyEyebrow", "Do this now")
          : t("receiving.mobilePrimaryBlockedEyebrow", "Next step"),
        title: canStartReadyOrder
          ? t("receiving.mobilePrimaryStartTitle", "Start the next inbound order")
          : t("receiving.mobilePrimaryCannotStartTitle", "Finish setup before starting this inbound"),
        body: canStartReadyOrder
          ? t("receiving.mobilePrimaryReadyBody", "Work on {order} first.", {
              order: mobileReadyOrder.order_number,
            })
          : t(
              "receiving.mobilePrimaryCannotStartBody",
              "This order is waiting, but receiving cannot start until the required warehouse setup is complete.",
            ),
        primaryLabel: startSelectedOrderMutation.isPending
          ? t("receiving.tableSelectionStarting", "Opening receiving...")
          : canStartReadyOrder
          ? t("receiving.mobilePrimaryStartAction", "Start this inbound")
          : t("receiving.mobilePrimaryGoSetup", "Go to setup"),
        onAction: canStartReadyOrder ? () => startSelectedOrderMutation.mutate(mobileReadyOrder.id) : undefined,
        href: canStartReadyOrder ? undefined : checklistHref(firstMissingReceivingStep?.name || "warehouse"),
        context: canStartReadyOrder
          ? t("receiving.mobilePrimaryStartContext", "After this, scan or type the package barcode.")
          : t("receiving.mobilePrimarySetupContext", "Return here after setup is complete."),
        disabled: startSelectedOrderMutation.isPending,
      };
    }

    if (!receivingReady) {
      return {
        state: "blocked",
        eyebrow: t("receiving.mobilePrimaryBlockedEyebrow", "Next step"),
        title: t("receiving.mobilePrimarySetupTitle", "Finish receiving setup first"),
        body: t(
          "receiving.mobilePrimarySetupBody",
          "No receiving task can start until warehouse, locations, clients, and SKUs are ready.",
        ),
        primaryLabel: t("receiving.mobilePrimaryGoSetup", "Go to setup"),
        href: checklistHref(firstMissingReceivingStep?.name || "warehouse"),
        context: t("receiving.mobilePrimarySetupContext", "Return here after setup is complete."),
        disabled: false,
      };
    }

    return {
      state: "empty",
      eyebrow: t("receiving.mobilePrimaryEmptyEyebrow", "Queue clear"),
      title: t("receiving.mobilePrimaryClearTitle", "No receiving work is waiting"),
      body: t(
        "receiving.mobilePrimaryClearBody",
        "Return to the dashboard and wait for a receiving task. Create or import inbound orders from the desktop back-office.",
      ),
      primaryLabel: t("receiving.mobilePrimaryBackDashboard", "Back to dashboard"),
      href: "/dashboard",
      context: t(
        "receiving.mobilePrimaryClearContext",
        "Import Center is hidden on phones so mobile receiving stays focused on scan work.",
      ),
      disabled: false,
    };
  })();

  const tabSwitcher = (
    <div className="-mx-1 max-w-[calc(100%+0.5rem)] touch-pan-x overflow-x-auto overscroll-x-contain px-1 pb-1 sm:mx-0 sm:w-fit sm:max-w-full sm:rounded-2xl sm:bg-[#ebe5db] sm:p-1.5">
      <div className="flex w-max gap-1 rounded-2xl bg-[#ebe5db] p-1.5 sm:rounded-none sm:bg-transparent sm:p-0">
        {(["orders", "receive"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => {
              if (!canOpenReceivingFlow && tab === "receive") return;
              setActiveTab(tab);
            }}
            disabled={tab === "receive" && !canOpenReceivingFlow}
            className={`shrink-0 whitespace-nowrap rounded-[1rem] px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-white text-[#13212c] shadow-sm"
                : "text-[#6c7a86] hover:text-[#13212c]"
            }`}
          >
            {tab === "orders" ? t("receiving.allOrders", "All Orders") : t("receiving.startReceiving", "Start Receiving")}
          </button>
        ))}
      </div>
    </div>
  );

  const receivingWorkspaceContent =
    activeTab === "orders" ? (
        <div id="receiving-orders-workspace" className="max-w-full space-y-4 overflow-hidden">
        {selectedOrdersTableOrder ? (
          <>
            <section className="max-w-full overflow-hidden rounded-[1.35rem] border border-[#24507a]/18 bg-[#f3f8fb] p-4 shadow-[0_16px_32px_rgba(19,33,44,0.06)] md:hidden">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#24507a]">
                    {t("receiving.mobileDoThisNow", "Do this now")}
                  </p>
                  <h2 className="mt-2 break-words text-xl font-semibold leading-snug text-[#13212c]">
                    {selectedOrderMobileTitle}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-[#51606b]">{selectedOrderMobileBody}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedOrdersTableOrder(null)}
                  className="shrink-0 rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-semibold text-[#13212c]"
                >
                  {t("receiving.mobileChangeOrderAction", "Change")}
                </button>
              </div>

              <div className="mt-3 rounded-[1rem] border border-[#24507a]/12 bg-white/84 px-3 py-2">
                <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                  {t("receiving.mobileSelectedOrderContext", "Current inbound")}
                </p>
                <p className="mt-1 break-words text-sm font-semibold text-[#13212c]">
                  {selectedOrdersTableOrder.order_number}
                </p>
                {selectedOrderMobilePackage ? (
                  <p className="mt-1 text-sm leading-5 text-[#61717d]">
                    {t("receiving.packageDispatchCardTitle", "Package {number}", {
                      number: String(selectedOrderMobilePackage.package_number || 1),
                    })}
                    {selectedOrderMobilePackage.package_type ? ` · ${selectedOrderMobilePackage.package_type}` : ""} ·{" "}
                    {packagePrimaryBlocker(selectedOrderMobilePackage, t)}
                  </p>
                ) : null}
              </div>

              <button
                type="button"
                onClick={runSelectedOrderMobilePrimaryAction}
                className="mt-4 flex min-h-12 w-full items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold text-white"
              >
                {selectedOrderMobilePrimaryLabel}
              </button>

              <details className="mt-3 rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3">
                <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                  {t("receiving.mobileOrderContextToggle", "Show order context")}
                </summary>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Pill as="span" tone="neutral" count={selectedOrdersTableOrder.packages_open || 0}>
                    {t("receiving.packageMetricOpenShort", "Open")}
                  </Pill>
                  <Pill as="span" tone="neutral" count={selectedOrdersTableOrder.internal_labels_print_pending || 0}>
                    {t("receiving.packageMetricPrintShort", "Print")}
                  </Pill>
                  <Pill as="span" tone="neutral" count={selectedOrdersTableOrder.packages_putaway_pending || 0}>
                    {t("receiving.packageMetricPutawayShort", "Putaway")}
                  </Pill>
                  <StatusBadge status={selectedOrdersTableOrder.status} />
                  {hasNonDefaultRecordState(selectedOrdersTableOrder) ? (
                    <InboundOrderRecordStateBadge order={selectedOrdersTableOrder} />
                  ) : null}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    to={`/receiving/orders/${selectedOrdersTableOrder.id}`}
                    className="rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
                  >
                    {t("receiving.openFullDetailAction", "Open full detail")}
                  </Link>
                </div>
              </details>
            </section>

            <section className="hidden rounded-[1.6rem] border border-[#13212c]/10 bg-white/90 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
                  {selectedOrdersTableOrder.archived
                    ? t("receiving.tableSelectionArchivedEyebrow", "Selected archived inbound")
                    : selectedOrdersTableOrder.voided
                    ? t("receiving.tableSelectionVoidedEyebrow", "Selected voided inbound")
                    : ["expected", "arrived"].includes(selectedOrdersTableOrder.status)
                    ? t("receiving.tableSelectionExpectedEyebrow", "Selected expected inbound")
                    : selectedOrdersTableOrder.status === "receiving"
                    ? t("receiving.tableSelectionReceivingEyebrow", "Selected active receipt")
                    : t("receiving.tableSelectionManagedEyebrow", "Selected inbound order")}
                </p>
                <h2 className="mt-2 text-xl font-semibold text-[#13212c]">{selectedOrdersTableOrder.order_number}</h2>
                <p className="mt-2 text-sm text-[#61717d]">
                  {t("receiving.externalReferenceColumn", "External ref")}: {displayInboundReference(selectedOrdersTableOrder)}
                </p>
              </div>
              <div className="flex flex-wrap items-start gap-3">
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">
                    {t("common.status", "Status")}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={selectedOrdersTableOrder.status} />
                    {hasNonDefaultRecordState(selectedOrdersTableOrder) ? (
                      <InboundOrderRecordStateBadge order={selectedOrdersTableOrder} />
                    ) : null}
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                onClick={() => setSelectedOrdersTableOrder(null)}
                className="rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
              >
                {t("receiving.tableSelectionClear", "Clear selection")}
              </button>
              <Link
                to={`/receiving/orders/${selectedOrdersTableOrder.id}`}
                className="rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
              >
                {t("receiving.openFullDetailAction", "Open full detail")}
              </Link>
              {["expected", "arrived"].includes(selectedOrdersTableOrder.status) && canOpenReceivingFlow && !selectedOrdersTableOrder.archived ? (
                <button
                  onClick={() => startSelectedOrderMutation.mutate(selectedOrdersTableOrder.id)}
                  disabled={startSelectedOrderMutation.isPending}
                  className="rounded-full bg-[#13212c] px-5 py-2 text-sm font-semibold text-[#f4efe8] disabled:opacity-50"
                >
                  {startSelectedOrderMutation.isPending
                    ? t("receiving.tableSelectionStarting", "Opening receiving...")
                    : t("receiving.tableSelectionExpectedAction", "Start receiving")}
                </button>
              ) : selectedOrdersTableOrder.status === "receiving" && !selectedOrdersTableOrder.archived ? (
                <button
                  onClick={() => launchSelectedOrderToFlow(selectedOrdersTableOrder)}
                  className="rounded-full bg-[#13212c] px-5 py-2 text-sm font-semibold text-[#f4efe8]"
                >
                  {t("receiving.tableSelectionReceivingAction", "Continue receiving")}
                </button>
              ) : null}
            </div>
            {selectedOrderHasSecondaryActions ? (
              <details className="mt-4 rounded-[1.1rem] border border-[#13212c]/8 bg-[#faf7f2] px-4 py-3">
                <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                  {t("receiving.tableSelectionMoreActions", "More order actions")}
                </summary>
                <div className="mt-4 flex flex-wrap gap-3">
                  {selectedOrdersTableOrder.can_archive ? (
                    <button
                      onClick={() => {
                        const archived = !selectedOrdersTableOrder.archived;
                        const confirmed = window.confirm(
                          archived
                            ? t("receiving.confirmArchive", "Archive this inbound order and hide it from the default work queue?")
                            : t("receiving.confirmRestore", "Restore this inbound order to the default work queue?"),
                        );
                        if (!confirmed) return;
                        archiveSelectedOrderMutation.mutate({ orderId: selectedOrdersTableOrder.id, archived });
                      }}
                      disabled={archiveSelectedOrderMutation.isPending}
                      className="rounded-full border border-[#13212c]/12 bg-white px-4 py-2 text-sm font-semibold text-[#13212c] disabled:opacity-50"
                    >
                      {selectedOrdersTableOrder.archived
                        ? t("receiving.restoreOrderAction", "Restore order")
                        : t("receiving.archiveOrderAction", "Archive order")}
                    </button>
                  ) : null}
                  {selectedOrdersTableOrder.can_void ? (
                    <button
                      onClick={() => {
                        const confirmed = window.confirm(
                          t(
                            "receiving.confirmVoid",
                            "Void this inbound order? This keeps the audit trail but removes it from active receiving work.",
                          ),
                        );
                        if (!confirmed) return;
                        voidSelectedOrderMutation.mutate(selectedOrdersTableOrder.id);
                      }}
                      disabled={voidSelectedOrderMutation.isPending}
                      className="rounded-full border border-[#b98383] bg-[#fff7f7] px-4 py-2 text-sm font-semibold text-[#8d2f2f] disabled:opacity-50"
                    >
                      {t("receiving.voidOrderAction", "Void order")}
                    </button>
                  ) : null}
                  {selectedOrdersTableOrder.can_delete ? (
                    <button
                      onClick={() => {
                        const confirmed = window.confirm(
                          t(
                            "receiving.confirmDelete",
                            "Delete this inbound order permanently? Only use this for clean orders that never entered receiving.",
                          ),
                        );
                        if (!confirmed) return;
                        deleteSelectedOrderMutation.mutate(selectedOrdersTableOrder.id);
                      }}
                      disabled={deleteSelectedOrderMutation.isPending}
                      className="rounded-full border border-[#b98383] bg-white px-4 py-2 text-sm font-semibold text-[#8d2f2f] disabled:opacity-50"
                    >
                      {t("receiving.deleteOrderAction", "Delete permanently")}
                    </button>
                  ) : null}
                </div>
                {!selectedOrdersTableOrder.can_delete && !selectedOrdersTableOrder.can_void ? (
                  <p className="mt-4 text-xs text-[#7f8d98]">
                    {t(
                      "receiving.lifecycleLockHint",
                      "Orders that already have scans, confirmed receipts, internal labels, or downstream work should be archived instead of deleted.",
                    )}
                  </p>
                ) : null}
              </details>
            ) : null}
            <section className="mt-5 rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("receiving.packageDispatchEyebrow", "Package dispatch")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="rounded-full border border-[#d7d0c4] bg-[#f8f4ec] px-3 py-1 text-xs font-semibold text-[#51606b]">
                    {t("receiving.packageDispatchCount", "{count} packages still need action", {
                      count: String(selectedOrderDispatchPackages.length),
                    })}
                  </div>
                  {selectedOrdersTableOrder.supervisor_review_needed ? (
                    <span className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                      {t("receiving.packageMetricSupervisorReview", "Supervisor review")}: 1
                    </span>
                  ) : null}
                  {selectedOrderRecommendedAction && selectedOrderRecommendedFilter ? (
                    <button
                      type="button"
                      onClick={() => runQueueAction(selectedOrdersTableOrder, selectedOrderRecommendedFilter)}
                      className="rounded-full bg-[#24507a] px-4 py-2 text-sm font-semibold text-white"
                    >
                      {operationActionLabel(selectedOrderRecommendedFilter, selectedOrderRecommendedAction)}
                    </button>
                  ) : null}
                </div>
              </div>

              {operationFilter !== "all" ? (
                <div className="mt-3">
                  <span className="rounded-full border border-[#24507a]/10 bg-[#eef3f8] px-3 py-1 text-xs font-medium text-[#58718a]">
                    {operationFilter === "needs_action"
                      ? t("receiving.operationFilterNeedsAction", "Needs action")
                      : operationFilter === "supervisor_review"
                      ? t("receiving.operationFilterSupervisorReview", "Supervisor review")
                      : operationFilter === "package_open"
                      ? t("receiving.operationFilterPackageOpen", "Packages open")
                      : operationFilter === "putaway_pending"
                      ? t("receiving.operationFilterPutawayPending", "Putaway handoff")
                      : operationFilter === "print_pending"
                      ? t("receiving.operationFilterPrintPending", "Print pending")
                      : operationFilter === "prebooked"
                      ? t("receiving.operationFilterPrebooked", "Pre-booked")
                      : operationFilter === "dock_created"
                      ? t("receiving.operationFilterDockCreated", "Opened at dock")
                      : t("receiving.operationFilterRecentlyChanged", "Recently changed orders")}
                  </span>
                </div>
              ) : null}

              {isLoadingSelectedOrderDetail ? (
                <p className="mt-4 text-sm text-[#61717d]">
                  {t("receiving.packageDispatchLoading", "Loading package work for this inbound order...")}
                </p>
              ) : selectedOrderDispatchPackages.length ? (
                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  {selectedOrderVisiblePackages.map((pkg: any) => {
                    const primaryCode = packagePrimaryCode(pkg);
                    const primaryAction = packagePrimaryActionKind(pkg);
                    return (
                      <div
                        key={pkg.id}
                        className="rounded-[1rem] border border-[#13212c]/8 bg-[#faf7f2] px-4 py-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-[#13212c]">
                              {t("receiving.packageDispatchCardTitle", "Package {number}", {
                                number: String(pkg.package_number || 1),
                              })}
                              {pkg.package_type ? ` · ${pkg.package_type}` : ""}
                              {pkg.sku_code ? ` · ${pkg.sku_code}` : ""}
                            </p>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-full px-3 py-1 text-xs font-medium ${
                                pkg.package_origin === "dock_created"
                                  ? "bg-[#edf2f7] text-[#425466]"
                                  : "bg-[#eef7ef] text-[#2f6c43]"
                              }`}
                            >
                              {pkg.package_origin === "dock_created"
                                ? t("receiving.packageOriginDockCreated", "Opened at dock")
                                : t("receiving.packageOriginPrebooked", "Pre-booked")}
                            </span>
                          </div>
                        </div>

                        <div className="mt-3 flex flex-wrap gap-2">
                          <span className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                            {t("receiving.packageDispatchLineChip", "Line {line}", {
                              line: String(pkg.line_number || "—"),
                            })}
                          </span>
                          <span className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                            {t("receiving.packageDispatchQuantityChip", "Expected {expected} · Received {received}", {
                              expected: String(pkg.expected_qty || 0),
                              received: String(pkg.received_qty || 0),
                            })}
                          </span>
                          <span className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                            {packagePrimaryBlocker(pkg, t)}
                          </span>
                          {primaryCode ? (
                            <span className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1 text-xs font-medium text-[#51606b]">
                              {t("receiving.packageDispatchPrimaryCode", "Primary code {code}", {
                                code: String(primaryCode),
                              })}
                            </span>
                          ) : null}
                        </div>

                        <div className="mt-4 flex flex-wrap gap-2">
                          {primaryAction === "receiving" ? (
                            <button
                              type="button"
                              onClick={() => openPackageReceiving(pkg)}
                              className="rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8]"
                            >
                              {t("receiving.packageDispatchReceiveAction", "Open package in receiving")}
                            </button>
                          ) : null}
                          {primaryAction === "print" ? (
                            <button
                              type="button"
                              onClick={() => openPackagePrint(pkg)}
                              className="rounded-full bg-[#24507a] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-white"
                            >
                              {t("receiving.packageDispatchPrintAction", "Open package print")}
                            </button>
                          ) : null}
                          {primaryAction === "putaway" ? (
                            <button
                              type="button"
                              onClick={() => openPackagePutaway(pkg)}
                              className="rounded-full bg-[#91621a] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-white"
                            >
                              {t("receiving.packageDispatchPutawayAction", "Open package putaway")}
                            </button>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => navigate(`/receiving/orders/${selectedOrdersTableOrder.id}`)}
                            className="rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                          >
                            {t("receiving.packageDispatchDetailAction", "Open full detail")}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-4 text-sm text-[#61717d]">
                  {t(
                    "receiving.packageDispatchEmpty",
                    "No package-level work is still open here. Use the full inbound detail if you want to review the audit trail.",
                  )}
                </p>
              )}

              {selectedOrderDispatchPackages.length > 4 ? (
                <div className="mt-4 flex justify-end">
                  <button
                    type="button"
                    onClick={() => setShowAllSelectedOrderPackages((current) => !current)}
                    className="rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                  >
                    {showAllSelectedOrderPackages
                      ? t("receiving.packageDispatchShowFewer", "Show fewer packages")
                      : t("receiving.packageDispatchShowMore", "Show all {count} packages", {
                          count: String(selectedOrderDispatchPackages.length),
                        })}
                  </button>
                </div>
              ) : null}
            </section>
            <details className="mt-5 rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-3">
              <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                {t("receiving.historyPanelToggle", "Review history and audit")}
              </summary>
              <InboundOrderHistoryPanel
                detail={selectedOrderDetail}
                isLoading={isLoadingSelectedOrderDetail}
                className="mt-4"
                orderId={selectedOrdersTableOrder?.id || null}
              />
            </details>
            </section>
          </>
        ) : null}

        {!selectedOrdersTableOrder ? (
          <section className="max-w-full overflow-hidden rounded-[1.25rem] border border-[#13212c]/10 bg-white/86 p-4 shadow-[0_16px_34px_rgba(19,33,44,0.06)] md:hidden">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#7f8d98]">
              {mobilePrimaryAction.eyebrow}
            </p>
            <h2 className="mt-2 text-xl font-semibold leading-snug text-[#13212c]">
              {mobilePrimaryAction.title}
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#61717d]">
              {mobilePrimaryAction.body}
            </p>
            {mobilePrimaryAction.context ? (
              <p className="mt-2 rounded-[0.9rem] border border-[#13212c]/8 bg-[#faf7f2] px-3 py-2 text-xs font-medium leading-5 text-[#6f6248]">
                {mobilePrimaryAction.context}
              </p>
            ) : null}

            {mobilePrimaryAction.href ? (
              <Link
                to={mobilePrimaryAction.href}
                className={`mt-4 inline-flex min-h-12 w-full items-center justify-center rounded-full px-5 py-3 text-sm font-semibold text-white ${
                  mobilePrimaryAction.state === "ready" ? "bg-[#13212c]" : "bg-[#8b723f]"
                }`}
              >
                {mobilePrimaryAction.primaryLabel}
              </Link>
            ) : (
              <button
                type="button"
                onClick={mobilePrimaryAction.onAction}
                disabled={mobilePrimaryAction.disabled}
                className={`mt-4 min-h-12 w-full rounded-full px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#9ca7af] ${
                  mobilePrimaryAction.state === "ready" ? "bg-[#13212c]" : "bg-[#8b723f]"
                }`}
              >
                {mobilePrimaryAction.primaryLabel}
              </button>
            )}

            <details className="mt-3 rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3">
              <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                {t("receiving.mobileSecondaryToolsAction", "View counts or change queue")}
              </summary>
              <div className="mt-3 grid max-w-full grid-cols-2 gap-2">
                {([
                  ["package_open", t("receiving.operationFilterPackageOpen", "Packages open"), operationCounts.package_open],
                  ["print_pending", t("receiving.operationFilterPrintPending", "Print pending"), operationCounts.print_pending],
                  ["putaway_pending", t("receiving.operationFilterPutawayPending", "Putaway handoff"), operationCounts.putaway_pending],
                  ["supervisor_review", t("receiving.operationFilterSupervisorReview", "Supervisor review"), operationCounts.supervisor_review],
                ] as const).map(([filter, label, count]) => (
                  <Pill
                    key={filter}
                    active={operationFilter === filter}
                    count={count}
                    onClick={() => {
                      setOperationFilter(filter);
                      setOrdersPage(1);
                    }}
                    className={mobileFilterPillClass}
                  >
                    {label}
                  </Pill>
                ))}
              </div>
              <div className="mt-3 grid max-w-full grid-cols-2 gap-2">
                {(
                  [
                    ["active", t("receiving.lifecycleFilterActive", "Receiving work")],
                    ["all", t("receiving.lifecycleFilterAll", "All orders")],
                    ["archived", t("receiving.lifecycleFilterArchived", "Archived")],
                    ["voided", t("receiving.lifecycleFilterVoided", "Voided")],
                    ["completed", t("receiving.lifecycleFilterCompleted", "Completed")],
                  ] as const
                ).map(([value, label]) => (
                  <Pill
                    key={value}
                    onClick={() => {
                      setLifecycleFilter(value);
                      setOrdersPage(1);
                    }}
                    active={lifecycleFilter === value}
                    count={lifecycleCounts[value]}
                    className={mobileFilterPillClass}
                  >
                    {label}
                  </Pill>
                ))}
              </div>
            </details>
          </section>
        ) : null}

        {quietOrdersManagementView ? (
          <section className="hidden max-w-full overflow-hidden rounded-[1.2rem] border border-[#13212c]/8 bg-white/70 px-4 py-4 md:block">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("receiving.ordersQuietEyebrow", "Order history")}
                </p>
                <p className="mt-1 break-words text-sm font-semibold leading-6 text-[#13212c]">
                  {t("receiving.ordersQuietTitle", "No active inbound work is blocking the floor right now")}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setLifecycleFilter("all");
                    setOrdersPage(1);
                  }}
                  className="rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
                >
                  {t("receiving.ordersQuietAllAction", "Browse all orders")}
                </button>
                <button
                  type="button"
                  onClick={() => setShowArchivedOrders(true)}
                  className="rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
                >
                  {t("receiving.ordersQuietArchivedAction", "Show archived")}
                </button>
              </div>
            </div>
          </section>
        ) : (
          <>
            <div className="hidden max-w-full flex-col gap-3 overflow-hidden rounded-[1.2rem] border border-[#13212c]/8 bg-white/70 px-4 py-3 text-sm md:flex sm:flex-row sm:items-center sm:justify-between">
              <span className="min-w-0 flex-1 rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-2 font-medium leading-5 text-[#51606b] sm:rounded-full sm:py-1">
                {showArchivedOrders
                  ? t("receiving.archivedToggleBodyOn", "Showing archived inbound orders alongside active work.")
                  : t("receiving.archivedToggleBodyOff", "Archived inbound orders are hidden from the default work queue.")}
              </span>
              <button
                type="button"
                onClick={() => setShowArchivedOrders((current) => !current)}
                className="w-full rounded-full border border-[#13212c]/10 bg-white px-4 py-2 font-semibold text-[#13212c] sm:w-auto"
              >
                {showArchivedOrders
                  ? t("receiving.hideArchivedAction", "Hide archived")
                  : t("receiving.showArchivedAction", "Show archived")}
              </button>
            </div>

            <div className="hidden max-w-full overflow-hidden rounded-[1.2rem] border border-[#13212c]/8 bg-white/70 p-3 md:block">
              <div className="grid max-w-full grid-cols-2 gap-2 sm:flex sm:touch-pan-x sm:items-center sm:overflow-x-auto sm:overscroll-x-contain sm:pb-1">
                {(
                  [
                    ["active", t("receiving.lifecycleFilterActive", "Receiving work")],
                    ["all", t("receiving.lifecycleFilterAll", "All orders")],
                    ["archived", t("receiving.lifecycleFilterArchived", "Archived")],
                    ["voided", t("receiving.lifecycleFilterVoided", "Voided")],
                    ["completed", t("receiving.lifecycleFilterCompleted", "Completed")],
                  ] as const
                ).map(([value, label]) => (
                  <Pill
                    key={value}
                    onClick={() => {
                      setLifecycleFilter(value);
                      setOrdersPage(1);
                    }}
                    active={lifecycleFilter === value}
                    count={lifecycleCounts[value]}
                    className={`${mobileFilterPillClass} sm:w-auto sm:justify-start sm:whitespace-nowrap sm:uppercase sm:tracking-[0.12em]`}
                  >
                    {label}
                  </Pill>
                ))}
              </div>
            </div>

          </>
        )}

        {nextQueueAction && !selectedOrdersTableOrder ? (
          <section className="hidden max-w-full flex-col gap-3 overflow-hidden rounded-[1.4rem] border border-[#24507a]/12 bg-[#eef3f8] px-4 py-3 md:flex sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#58718a]">
                {t("receiving.operationFocusEyebrow", "Package work focus")}
              </p>
              <p className="mt-1 text-sm font-semibold text-[#13212c]">
                {nextQueueAction.order.order_number}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className="max-w-full break-words rounded-full border border-[#24507a]/10 bg-white/80 px-3 py-1 text-[11px] font-semibold leading-5 text-[#355a84]">
                  {operationFilterSummary(operationFilter)}
                </span>
                <span className="rounded-full border border-[#24507a]/10 bg-white/80 px-3 py-1 text-[11px] font-medium text-[#58718a]">
                  {t("receiving.queueFocusLatestActivity", "Latest activity: {timeAgo}", {
                    timeAgo: formatRecentActivityLabel(nextQueueAction.order, t),
                  })}
                </span>
              </div>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <button
                type="button"
                onClick={() => runQueueAction(nextQueueAction.order, operationFilter)}
                className="w-full rounded-full bg-[#24507a] px-4 py-2 text-sm font-semibold text-white sm:w-auto"
              >
                {operationActionLabel(operationFilter, nextQueueAction.action)}
              </button>
              <button
                type="button"
                onClick={() => {
                  setOperationFilter("all");
                  setOrdersPage(1);
                }}
                className="w-full rounded-full border border-[#24507a]/12 bg-white px-4 py-2 text-sm font-semibold text-[#24507a] sm:w-auto"
              >
                {t("receiving.operationFilterAll", "All package work")}
              </button>
            </div>
          </section>
        ) : null}

        {!quietOrdersManagementView && !selectedOrdersTableOrder ? (
        <div className="space-y-2 md:hidden">
          <div className="px-1">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
              {t("receiving.mobileOrderQueueEyebrow", "Inbound queue")}
            </p>
          </div>
          {pagedOrders.map((row: any) => {
            const rowRecommendedFilter =
              operationFilter === "all" ? recommendedFilterForOrder(row, recentCutoff) : operationFilter;
            const rowRecommendedAction = rowRecommendedFilter
              ? queueActionForOrder(row, rowRecommendedFilter)
              : null;
            const externalReference = displayInboundReference(row);

            return (
              <TaskCard
                key={row.id}
                label={t("receiving.mobileOrderQueueItemLabel", "Inbound order")}
                title={row.order_number}
                meta={
                  rowRecommendedAction && rowRecommendedFilter
                    ? operationActionLabel(rowRecommendedFilter, rowRecommendedAction)
                    : externalReference !== "—"
                    ? `${t("receiving.externalReferenceColumn", "External ref")}: ${externalReference}`
                    : t("receiving.mobileOrderQueueReviewMeta", "Tap to review inbound order")
                }
                chips={
                  <>
                    <StatusBadge status={row.status} />
                    {hasNonDefaultRecordState(row) ? <InboundOrderRecordStateBadge order={row} /> : null}
                    {row.packages_open > 0 ? (
                      <Pill as="span" tone="neutral" count={row.packages_open || 0}>
                        {t("receiving.packageMetricOpenShort", "Open")}
                      </Pill>
                    ) : null}
                    {row.internal_labels_print_pending > 0 ? (
                      <Pill as="span" tone="neutral" count={row.internal_labels_print_pending || 0}>
                        {t("receiving.packageMetricPrintShort", "Print")}
                      </Pill>
                    ) : null}
                    {row.packages_putaway_pending > 0 ? (
                      <Pill as="span" tone="neutral" count={row.packages_putaway_pending || 0}>
                        {t("receiving.packageMetricPutawayShort", "Putaway")}
                      </Pill>
                    ) : null}
                  </>
                }
                action={
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#13212c]/10 bg-white text-[#13212c]">
                    <ArrowRight size={15} />
                  </span>
                }
                onClick={() => setSelectedOrdersTableOrder(row)}
              />
            );
          })}
        </div>
        ) : null}

        {!quietOrdersManagementView ? (
        <div className="hidden md:block">
        <DataTable
          columns={columns}
          data={pagedOrders}
          loading={isLoading}
          emptyMessage={t("receiving.empty", "No inbound orders")}
          emptyHint={t("receiving.emptyHint", "Create the first inbound order before you start unloading or receiving against freight.")}
          emptyActionLabel={t("receiving.emptyAction", "Open setup wizard")}
          emptyActionHref="/setup"
          onHeaderClick={(key) => {
            if (!(key === "order_number" || key === "status" || key === "client_id")) return;
            setOrdersPage(1);
            if (ordersSortField === key) {
              setOrdersSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
              return;
            }
            setOrdersSortField(key);
            setOrdersSortDirection("asc");
          }}
          sortField={ordersSortField}
          sortDirection={ordersSortDirection}
          onRowClick={(row: any) => {
            setSelectedOrdersTableOrder(row);
          }}
        />
        </div>
        ) : null}
        {!quietOrdersManagementView && sortedOrders.length > ordersPageSize ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.4rem] border border-[#13212c]/8 bg-white/70 px-4 py-3 text-sm text-[#51606b]">
            <p>
              {t("receiving.ordersPaginationSummary", "Showing {start}-{end} of {total} orders", {
                start: String((ordersPage - 1) * ordersPageSize + 1),
                end: String(Math.min(ordersPage * ordersPageSize, sortedOrders.length)),
                total: String(sortedOrders.length),
              })}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setOrdersPage((current) => Math.max(1, current - 1))}
                disabled={ordersPage === 1}
                className="rounded-full border border-[#13212c]/10 bg-white px-4 py-2 font-semibold text-[#13212c] disabled:cursor-not-allowed disabled:opacity-45"
              >
                {t("common.previous", "Previous")}
              </button>
              <span className="rounded-full bg-[#f5efe5] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#6c7a86]">
                {t("receiving.ordersPaginationPage", "Page {page} / {total}", {
                  page: String(ordersPage),
                  total: String(totalOrdersPages),
                })}
              </span>
              <button
                type="button"
                onClick={() => setOrdersPage((current) => Math.min(totalOrdersPages, current + 1))}
                disabled={ordersPage === totalOrdersPages}
                className="rounded-full border border-[#13212c]/10 bg-white px-4 py-2 font-semibold text-[#13212c] disabled:cursor-not-allowed disabled:opacity-45"
              >
                {t("common.next", "Next")}
              </button>
            </div>
          </div>
        ) : null}
        {!quietOrdersManagementView && hasMoreOrderBatches ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.4rem] border border-[#24507a]/12 bg-[#eef3f8] px-4 py-3 text-sm text-[#51606b]">
            <p>
              {t("receiving.moreOrdersAvailable", "{count} orders loaded. More orders are available from the server.", {
                count: String(orders.length),
              })}
            </p>
            <button
              type="button"
              onClick={() => fetchNextOrderBatch()}
              disabled={isFetchingNextOrderBatch}
              className="rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8] disabled:cursor-not-allowed disabled:bg-[#9ca7af]"
            >
              {isFetchingNextOrderBatch
                ? t("common.loading", "Loading...")
                : t("receiving.loadMoreOrders", "Load more orders")}
            </button>
          </div>
        ) : null}
      </div>
    ) : (
      <div id="receiving-flow">
        <ReceivingFlow
          key={
            selectedReceiveOrder
              ? `${selectedReceiveOrder.id}-${selectedReceiveOrder.status}-${selectedReceiveOrder.packageFocus || "none"}-${selectedReceiveOrder.packageId || "nopkg"}-${selectedReceiveOrder.printPackageId || "noprint"}-${selectedReceiveOrder.nonce}`
              : "receiving-flow-default"
          }
          initialOrderId={selectedReceiveOrder?.id}
          initialOrderStatus={selectedReceiveOrder?.status}
          initialPackageFocus={selectedReceiveOrder?.packageFocus || null}
          initialPackageId={selectedReceiveOrder?.packageId || null}
          initialPrintPackageId={selectedReceiveOrder?.printPackageId || null}
        />
      </div>
    );

  const exceptionPackageDetailsPanel =
    !quietOrdersManagementView && !selectedOrdersTableOrder ? (
      <details className="mt-4 rounded-[1.85rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
        <summary className="cursor-pointer list-none">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("receiving.exceptionBoardEyebrow", "Exception package details")}
              </p>
              <h3 className="mt-2 text-sm font-semibold text-[#13212c]">
                {t("receiving.exceptionBoardTitle", "See the packages that still need a lead decision or follow-through")}
              </h3>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-[#d7d0c4] bg-[#f8f4ec] px-3 py-1 text-xs font-semibold text-[#51606b]">
                {t("receiving.exceptionBoardCount", "{count} packages in focus", {
                  count: String(visibleSupervisorExceptionPackages.length),
                })}
              </span>
              <span className="rounded-full border border-[#24507a]/12 bg-white px-3 py-1 text-xs font-semibold text-[#24507a]">
                {t("common.details", "Details")}
              </span>
            </div>
          </div>
        </summary>

        <div className="mt-4 flex flex-wrap gap-1.5">
          {([
            ["all", t("receiving.exceptionLaneAll", "All exceptions")],
            ["receiving", t("receiving.packageDispatchOwnerReceiving", "Dock receiving")],
            ["print", t("receiving.packageDispatchOwnerPrint", "Label printing")],
            ["putaway", t("receiving.packageDispatchOwnerPutaway", "Putaway team")],
            ["review", t("receiving.packageDispatchOwnerReview", "Supervisor review")],
          ] as const).map(([lane, label]) => (
            <button
              key={lane}
              type="button"
              onClick={() => setExceptionOwnerLane(lane)}
              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
                exceptionOwnerLane === lane
                  ? "border border-[#24507a]/15 bg-[#eef3f8] text-[#24507a]"
                  : "border border-[#13212c]/8 bg-white/70 text-[#61717d]"
              }`}
            >
              {label}
              <span className="ml-1.5 rounded-full bg-[#13212c]/5 px-1.5 py-0.5 text-[10px]">
                {String(supervisorExceptionLaneCounts[lane])}
              </span>
            </button>
          ))}
        </div>

        {isLoadingSupervisorExceptionDetails ? (
          <p className="mt-4 text-sm text-[#61717d]">
            {t("receiving.exceptionBoardLoading", "Loading package exceptions...")}
          </p>
        ) : visibleSupervisorExceptionPackages.length ? (
          <div className="mt-4 space-y-3">
            {visibleSupervisorExceptionPackages.map((pkg: any) => {
              const primaryCode = packagePrimaryCode(pkg);
              const latestPackageTimestamp = packageLatestActivityTimestamp(pkg);
              const stale = latestPackageTimestamp > 0 && latestPackageTimestamp < recentCutoff;
              const primaryAction = packagePrimaryActionKind(pkg) || "detail";
              return (
                <div
                  key={`exception-${pkg.order_id}-${pkg.id}`}
                  className="rounded-[1rem] border border-[#13212c]/8 bg-[#faf7f2] px-3 py-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="text-sm font-semibold leading-5 text-[#13212c]">
                      {t("receiving.packageDispatchCardTitle", "Package {number}", {
                        number: String(pkg.package_number || 1),
                      })}
                      {pkg.package_type ? ` · ${pkg.package_type}` : ""}
                      {pkg.sku_code ? ` · ${pkg.sku_code}` : ""}
                    </p>
                    <span
                      className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                        pkg.package_origin === "dock_created"
                          ? "bg-[#edf2f7] text-[#425466]"
                          : "bg-[#eef7ef] text-[#2f6c43]"
                      }`}
                    >
                      {pkg.package_origin === "dock_created"
                        ? t("receiving.packageOriginDockCreated", "Opened at dock")
                        : t("receiving.packageOriginPrebooked", "Pre-booked")}
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <span className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[11px] font-medium text-[#51606b]">
                      {t("receiving.exceptionBoardLineChip", "Line {line} · {order}", {
                        line: String(pkg.line_number || "—"),
                        order: String(pkg.order_number || "—"),
                      })}
                    </span>
                    <span className="rounded-full border border-[#24507a]/10 bg-[#eef3f8] px-2.5 py-1 text-[11px] font-medium text-[#355a84]">
                      {packageRecommendedOwner(pkg, t)}
                    </span>
                    {latestPackageTimestamp ? (
                      <span className="rounded-full border border-[#24507a]/10 bg-[#eef3f8] px-2.5 py-1 text-[11px] font-medium text-[#355a84]">
                        {formatRecentActivityLabel(
                          { latest_activity_at: new Date(latestPackageTimestamp).toISOString() },
                          t,
                        )}
                      </span>
                    ) : null}
                    <span className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[11px] font-medium text-[#51606b]">
                      {packagePrimaryBlocker(pkg, t)}
                    </span>
                    {primaryCode ? (
                      <span className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[11px] font-medium text-[#51606b]">
                        {t("receiving.packageDispatchPrimaryCode", "Primary code {code}", {
                          code: String(primaryCode),
                        })}
                      </span>
                    ) : (
                      <span className="rounded-full bg-[#fff5e8] px-2.5 py-1 text-[11px] font-medium text-[#9a6421]">
                        {t("receiving.exceptionChipNoPrimaryCode", "No primary code")}
                      </span>
                    )}
                    {pkg.damaged_qty > 0 ? (
                      <span className="rounded-full bg-[#fff1f1] px-2.5 py-1 text-[11px] font-medium text-[#8d2f2f]">
                        {t("receiving.exceptionChipDamaged", "{count} damaged", {
                          count: String(pkg.damaged_qty || 0),
                        })}
                      </span>
                    ) : null}
                    {stale ? (
                      <span className="rounded-full bg-[#f5efe5] px-2.5 py-1 text-[11px] font-medium text-[#6c5a39]">
                        {t("receiving.exceptionChipStale", "Stale follow-up")}
                      </span>
                    ) : null}
                    {pkg.source_filter === "supervisor_review" ? (
                      <span className="rounded-full bg-[#fff0e8] px-2.5 py-1 text-[11px] font-medium text-[#9a4b18]">
                        {t("receiving.operationFilterSupervisorReview", "Supervisor review")}
                      </span>
                    ) : null}
                    {pkg.source_filter === "recently_changed" ? (
                      <span className="rounded-full bg-[#eaf1fb] px-2.5 py-1 text-[11px] font-medium text-[#355a84]">
                        {t("receiving.operationFilterRecentlyChanged", "Recently changed orders")}
                      </span>
                    ) : null}
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {primaryAction === "receiving" ? (
                      <button
                        type="button"
                        onClick={() => openPackageReceivingForOrder({ id: pkg.order_id, status: "receiving" }, pkg)}
                        className="rounded-full bg-[#13212c] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#f4efe8]"
                      >
                        {t("receiving.packageDispatchReceiveAction", "Open package in receiving")}
                      </button>
                    ) : null}
                    {primaryAction === "print" ? (
                      <button
                        type="button"
                        onClick={() =>
                          openPackagePrintForOrder(
                            { id: pkg.order_id, status: "receiving" },
                            pkg,
                          )
                        }
                        className="rounded-full bg-[#24507a] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-white"
                      >
                        {t("receiving.packageDispatchPrintAction", "Open package print")}
                      </button>
                    ) : null}
                    {primaryAction === "putaway" ? (
                      <button
                        type="button"
                        onClick={() =>
                          openPackagePutawayForOrder(
                            {
                              id: pkg.order_id,
                              status: "receiving",
                              order_number: pkg.order_number,
                              reference_number: pkg.reference_number,
                            },
                            pkg,
                          )
                        }
                        className="rounded-full bg-[#91621a] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-white"
                      >
                        {t("receiving.packageDispatchPutawayAction", "Open package putaway")}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => navigate(`/receiving/orders/${pkg.order_id}`)}
                      className="rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                    >
                      {t("receiving.packageDispatchDetailAction", "Open full detail")}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="mt-4 text-sm text-[#61717d]">
            {t(
              "receiving.exceptionBoardEmpty",
              "No package exceptions are active right now. The queue and handoff cards are already caught up.",
            )}
          </p>
        )}
      </details>
    ) : null;

  return (
    <div className="space-y-5 overflow-x-hidden">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[#7f8d98]">{t("receiving.eyebrow", "Inbound operations")}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{t("receiving.title", "Receiving")}</h1>
        </div>
        <div className="hidden flex-wrap items-center gap-3 lg:flex">
          {canImportInbound && !noActiveReceivingWork ? (
            <UpstreamActionLink to="/migration" label={t("receiving.openImportCenter", "Open import center")} />
          ) : null}
        </div>
      </div>

      {!receivingReady && (
        <section className="rounded-[2rem] border border-[#f0cf9d] bg-[#fff7ea] p-6 shadow-[0_20px_52px_rgba(19,33,44,0.06)]">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl border border-[#f7bf45]/35 bg-[#f7bf45]/14 p-2.5 text-[#c18500]">
              <AlertCircle size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#8b723f]">
                {t("receiving.readinessEyebrow", "Receiving readiness gate")}
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[#13212c]">
                {t("receiving.readinessTitle", "Finish the warehouse basics before receiving starts")}
              </h2>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-[#6f6248]">
                {t(
                  "receiving.readinessBody",
                  "Before the team books or receives freight, the workspace needs a real warehouse, storage locations, at least one client, and at least one SKU. Otherwise inbound work has nowhere reliable to land."
                )}
              </p>

              <div className="mt-5 grid gap-3 lg:grid-cols-2">
                {missingRequiredSteps.map((step: any) => (
                  <a
                    key={step.name}
                    href={checklistHref(step.name)}
                    className="rounded-[1.25rem] border border-[#e6d4b2] bg-white/80 px-4 py-4 transition hover:border-[#d4b07a] hover:bg-white"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-[#8a7755]">
                          {t("receiving.requiredStep", "Required step")}
                        </p>
                        <p className="mt-2 text-sm font-semibold text-[#13212c]">
                          {t(`dashboard.checklist.${step.name}.title`, step.title || "")}
                        </p>
                        <p className="mt-1.5 text-sm leading-6 text-[#61717d]">
                          {t(`dashboard.checklist.${step.name}.description`, step.description || "")}
                        </p>
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
                <span className="font-semibold text-[#13212c]">{t("receiving.readinessNext", "Next recommended step:")}</span>
                <a
                  href={checklistHref(missingRequiredSteps[0]?.name || "warehouse")}
                  className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-4 py-2 font-semibold text-[#13212c] transition hover:bg-[#fffdfa]"
                >
                  {t(`dashboard.checklist.${missingRequiredSteps[0]?.name || "warehouse"}.title`, missingRequiredSteps[0]?.title || "")}
                  <ArrowRight size={14} />
                </a>
              </div>
            </div>
          </div>
        </section>
      )}

      {canImportInbound ? (
        <PackListImportPanel
          onImported={async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.inboundOrders.list() });
            await queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.receiving });
          }}
        />
      ) : null}

      {receivingReady && (
        <section className="max-w-full space-y-3 overflow-hidden rounded-[2.2rem] border border-[#13212c]/8 bg-white/45 p-3 shadow-[0_24px_64px_rgba(19,33,44,0.08)] backdrop-blur sm:p-4">
          <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1.16fr)_340px]">
            <div className="min-w-0 space-y-3">
              <div className="hidden max-w-full overflow-hidden rounded-[1.4rem] border border-[#13212c]/8 bg-white/88 p-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block lg:hidden">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
                      {t("receiving.entryEyebrow", "Receiving work")}
                    </p>
                    <h2 className="mt-2 break-words text-lg font-semibold leading-snug text-[#13212c]">
                      {noActiveReceivingWork
                        ? t("receiving.mobileEmptyTitle", "Receiving is clear right now")
                        : t("receiving.mobileReadyTitle", "Move straight into the next inbound check")}
                    </h2>
                  </div>
                </div>
                <div className="mt-3 flex max-w-full gap-2 overflow-x-auto pb-1">
                  <Pill as="span" tone="neutral" count={readyToOpenOrders.length}>
                    {t("receiving.footerExpectedShort", "Ready")}
                  </Pill>
                  <Pill as="span" tone="neutral" count={activeReceivingOrders.length}>
                    {t("receiving.footerActiveShort", "Live")}
                  </Pill>
                </div>
              </div>

              {noActiveReceivingWork ? (
                <div className="hidden rounded-[1.85rem] border border-[#13212c]/10 bg-[#f7f3ec] p-6 shadow-[0_24px_60px_rgba(19,33,44,0.08)] lg:block">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="max-w-2xl">
                      <p className="text-[11px] uppercase tracking-[0.24em] text-[#7f8d98]">
                        {t("receiving.entryEyebrow", "Receiving work")}
                      </p>
                      <h2 className="mt-3 text-[1.9rem] font-semibold tracking-[-0.03em] text-[#13212c]">
                        {t("receiving.desktopEmptyTitle", "Receiving is clear right now")}
                      </h2>
                    </div>
                    {canImportInbound ? (
                      <UpstreamActionLink to="/migration" label={t("receiving.openImportCenter", "Open import center")} />
                    ) : null}
                  </div>
                </div>
              ) : (
                <>
                  <div className="hidden overflow-hidden rounded-[1.85rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_58%,#253847_100%)] p-5 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)] lg:block">
                    <div>
                      <div className="max-w-2xl">
                        <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">{t("receiving.entryEyebrow", "Receiving work")}</p>
                        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">
                          {t("receiving.entryTitle", "Continue inbound receiving, scans, and label follow-up.")}
                        </h2>
                      </div>
                    </div>

                    <div className="mt-5 flex flex-wrap gap-2">
                      <span className="rounded-full border border-white/12 bg-white/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#dbe4ea]">
                        {t("receiving.footerExpectedCount", "{count} ready", { count: String(readyToOpenOrders.length) })}
                      </span>
                      <span className="rounded-full border border-white/12 bg-white/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#dbe4ea]">
                        {t("receiving.footerActiveCount", "{count} live", { count: String(activeReceivingOrders.length) })}
                      </span>
                      <span className="rounded-full border border-white/12 bg-white/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#dbe4ea]">
                        {t("receiving.queuePackagesOpen", "Packages not completed")}: {packageRollup.open}
                      </span>
                      <span className="rounded-full border border-white/12 bg-white/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#dbe4ea]">
                        {t("receiving.queuePrintPending", "Internal labels still to print")}: {packageRollup.printPending}
                      </span>
                      <span className="rounded-full border border-white/12 bg-white/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#dbe4ea]">
                        {t("receiving.quickStartTitle", jobTitle || "Warehouse operator")}
                      </span>
                      {canImportInbound ? (
                        <UpstreamActionLink to="/migration" label={t("receiving.openImportCenter", "Open import center")} />
                      ) : null}
                    </div>
                  </div>
                </>
              )}

              <section className="max-w-full space-y-4 overflow-hidden rounded-[1.7rem] border border-[#13212c]/8 bg-white/68 p-3 shadow-[0_18px_44px_rgba(19,33,44,0.05)] sm:p-4">
                <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="hidden md:block">{tabSwitcher}</div>
                  <div className={`hidden flex-wrap items-center gap-2 text-xs text-[#61717d] ${noActiveReceivingWork ? "" : "md:flex"}`}>
                    <span className="rounded-full border border-[#13212c]/8 bg-white/80 px-3 py-1.5 font-semibold uppercase tracking-[0.14em] text-[#5c6974]">
                      {t("receiving.footerExpectedCount", "{count} ready", { count: String(readyToOpenOrders.length) })}
                    </span>
                    <span className="rounded-full border border-[#13212c]/8 bg-white/80 px-3 py-1.5 font-semibold uppercase tracking-[0.14em] text-[#5c6974]">
                      {t("receiving.footerActiveCount", "{count} live", { count: String(activeReceivingOrders.length) })}
                    </span>
                  </div>
                </div>
                {receivingWorkspaceContent}
              </section>
            </div>

            <div className="hidden xl:block">
              {noActiveReceivingWork ? (
                <section className="rounded-[1.85rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                    {t("receiving.queueClearEyebrow", "Receiving queue")}
                  </p>
                  <h2 className="mt-2 text-[1.4rem] font-semibold tracking-[-0.03em] text-[#13212c]">
                    {t("receiving.queueClearTitle", "Queue is clear right now")}
                  </h2>
                  <div className="mt-4">
                    <span className="rounded-full border border-[#d9d0c2] bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6c7a86]">
                      {t("receiving.queueClearState", "No active receiving work")}
                    </span>
                  </div>
                </section>
              ) : selectedOrdersTableOrder ? (
                <section className="rounded-[1.85rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                    {t("receiving.queueEyebrow", "Work queue")}
                  </p>
                  <h2 className="mt-2 text-[1.35rem] font-semibold tracking-[-0.03em] text-[#13212c]">
                    {t("receiving.globalQueuePausedTitle", "Current focus is on one inbound order")}
                  </h2>
                  <p className="mt-3 text-sm leading-6 text-[#61717d]">
                    {t(
                      "receiving.globalQueuePausedBody",
                      "Clear the current selection when you want to return to the wider queue and handoff lanes.",
                    )}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                      {t("receiving.footerExpectedCount", "{count} ready", { count: String(readyToOpenOrders.length) })}
                    </span>
                    <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                      {t("receiving.footerActiveCount", "{count} live", { count: String(activeReceivingOrders.length) })}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedOrdersTableOrder(null)}
                    className="mt-5 rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
                  >
                    {t("receiving.tableSelectionClear", "Clear selection")}
                  </button>
                </section>
              ) : (
                <>
                  <section className="rounded-[1.85rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("receiving.queueEyebrow", "Work queue")}</p>
                    <p className="mt-2 text-xs leading-5 text-[#61717d]">
                      {t("receiving.queuePriorityHint", "Work from top to bottom when several queues have items.")}
                    </p>
                    <div className="mt-4 space-y-4">
                      <QueuePriorityGroup label={t("receiving.queuePriorityBlockers", "1. Resolve blockers")}>
                        <ReceivingQueueCard
                          title={t("receiving.queueSupervisorReview", "Supervisor review")}
                          count={packageRollup.supervisorReview}
                          actionLabel={t("receiving.queueActionReview", "Review")}
                          onAction={
                            packageRollup.supervisorReview > 0 && bestOrderForOperation("supervisor_review")
                              ? () => openOperationQueue("supervisor_review")
                              : undefined
                          }
                        />
                      </QueuePriorityGroup>

                      <QueuePriorityGroup label={t("receiving.queuePriorityDock", "2. Finish dock work")}>
                        <ReceivingQueueCard
                          title={t("receiving.queuePackagesOpen", "Packages not completed")}
                          count={packageRollup.open}
                          actionLabel={t("receiving.queueActionOpenWork", "Open work")}
                          onAction={
                            packageRollup.open > 0 && bestOrderForOperation("package_open")
                              ? () => openOperationQueue("package_open")
                              : undefined
                          }
                        />
                        <ReceivingQueueCard
                          title={t("receiving.queueActive", "Continue receiving")}
                          count={activeReceivingOrders.length}
                          actionLabel={t("receiving.queueActionResume", "Continue receiving")}
                          onAction={
                            activeReceivingOrders.length > 0
                              ? () => launchSelectedOrderToFlow(activeReceivingOrders[0])
                              : undefined
                          }
                        />
                      </QueuePriorityGroup>

                      <QueuePriorityGroup label={t("receiving.queuePriorityDownstream", "3. Print and put away")}>
                        <ReceivingQueueCard
                          title={t("receiving.queuePrintPending", "Internal labels still to print")}
                          count={packageRollup.printPending}
                          actionLabel={t("receiving.queueActionOpenWork", "Open work")}
                          onAction={
                            packageRollup.printPending > 0 && bestOrderForOperation("print_pending")
                              ? () => openOperationQueue("print_pending")
                              : undefined
                          }
                        />
                        <ReceivingQueueCard
                          title={t("receiving.queuePutawayPending", "Putaway handoff")}
                          count={packageRollup.putawayPending}
                          actionLabel={t("receiving.queueActionOpenPutaway", "Open putaway")}
                          onAction={
                            packageRollup.putawayPending > 0 && bestOrderForOperation("putaway_pending")
                              ? () => openOperationQueue("putaway_pending")
                              : undefined
                          }
                        />
                      </QueuePriorityGroup>

                      <QueuePriorityGroup label={t("receiving.queuePriorityNewWork", "4. Start next inbound")}>
                        <ReceivingQueueCard
                          title={t("receiving.queueExpected", "Start next inbound")}
                          count={readyToOpenOrders.length}
                          actionLabel={t("receiving.queueActionOpenOrder", "Open next inbound")}
                          onAction={
                            readyToOpenOrders.length > 0
                              ? () => focusOrderInOrdersWorkspace(readyToOpenOrders[0])
                              : undefined
                          }
                        />
                      </QueuePriorityGroup>

                      <QueuePriorityGroup label={t("receiving.queuePriorityContext", "5. Reference signals")}>
                        <ReceivingQueueCard
                          title={t("receiving.queuePrebooked", "Pre-booked from import/planning")}
                          count={packageRollup.prebooked}
                          actionLabel={t("receiving.queueActionOpenWork", "Open work")}
                          onAction={
                            packageRollup.prebooked > 0 && bestOrderForOperation("prebooked")
                              ? () => openOperationQueue("prebooked")
                              : undefined
                          }
                        />
                        <ReceivingQueueCard
                          title={t("receiving.queueDockCreated", "Packages opened at dock")}
                          count={packageRollup.dockCreated}
                          actionLabel={t("receiving.queueActionOpenWork", "Open work")}
                          onAction={
                            packageRollup.dockCreated > 0 && bestOrderForOperation("dock_created")
                              ? () => openOperationQueue("dock_created")
                              : undefined
                          }
                        />
                        <ReceivingQueueCard
                          title={t("receiving.queueRecentlyChanged", "Recently changed orders")}
                          count={packageRollup.recentlyChanged}
                          actionLabel={t("receiving.queueActionReview", "Review")}
                          onAction={
                            packageRollup.recentlyChanged > 0 && bestOrderForOperation("recently_changed")
                              ? () => openOperationQueue("recently_changed")
                              : undefined
                          }
                        />
                      </QueuePriorityGroup>
                    </div>
                  </section>

                  {exceptionPackageDetailsPanel}

                  <section className="mt-4 rounded-[1.85rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                      {t("receiving.handoffEyebrow", "Shift handoff")}
                    </p>
                    <div className="mt-3 space-y-3">
                      {handoffLanes.map((lane) => (
                        <ShiftHandoffCard
                          key={lane.filter}
                          title={lane.title}
                          emptyBody={lane.empty}
                          order={lane.order}
                          reasons={lane.reasons}
                          latestActivityTitle={t("receiving.latestActivityLabel", "Latest activity")}
                          latestActivityLabel={lane.order ? formatRecentActivityLabel(lane.order, t) : null}
                          actionLabel={lane.action}
                          onAction={
                            lane.order && lane.actionSpec
                              ? () => runQueueAction(lane.order, lane.filter)
                              : undefined
                          }
                        />
                      ))}
                    </div>
                  </section>
                </>
              )}
            </div>
          </div>

        </section>
      )}

      {!receivingReady && tabSwitcher}

      {!receivingReady && receivingWorkspaceContent}
    </div>
  );
}


function ReceivingQueueCard({
  title,
  count,
  actionLabel,
  onAction,
}: {
  title: string;
  count: number;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const cardClasses =
    "w-full rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3.5 text-left transition-colors";

  if (onAction) {
    return (
      <button
        type="button"
        onClick={onAction}
        className={`${cardClasses} hover:border-[#24507a]/20 hover:bg-[#f2f7fb] focus:outline-none focus:ring-2 focus:ring-[#24507a]/20`}
      >
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-[#13212c]">{title}</p>
          <span className="rounded-full border border-[#d9d0c2] bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6c7a86]">
            {count}
          </span>
        </div>
        {actionLabel ? (
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#24507a]">
            {actionLabel}
          </p>
        ) : null}
      </button>
    );
  }

  return (
    <div className={cardClasses}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-[#13212c]">{title}</p>
        <span className="rounded-full border border-[#d9d0c2] bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6c7a86]">
          {count}
        </span>
      </div>
    </div>
  );
}

function QueuePriorityGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2 border-t border-[#13212c]/8 pt-3 first:border-t-0 first:pt-0">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      {children}
    </div>
  );
}

function ShiftHandoffCard({
  title,
  emptyBody,
  order,
  reasons,
  latestActivityTitle,
  latestActivityLabel,
  actionLabel,
  onAction,
}: {
  title: string;
  emptyBody: string;
  order?: any | null;
  reasons: string[];
  latestActivityTitle: string;
  latestActivityLabel?: string | null;
  actionLabel: string;
  onAction?: () => void;
}) {
  return (
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f8f5ef] px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[#13212c]">{title}</p>
        </div>
        {order ? (
          <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#51606b]">
            {order.order_number}
          </span>
        ) : null}
      </div>
      {order ? (
        <>
          <p className="mt-3 text-xs font-medium text-[#58718a]">
            {latestActivityTitle}: {latestActivityLabel || "—"}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {reasons.map((reason) => (
              <span
                key={reason}
                className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]"
              >
                {reason}
              </span>
            ))}
          </div>
          {onAction ? (
            <div className="mt-3">
              <button
                type="button"
                onClick={onAction}
                className="rounded-full bg-[#24507a] px-4 py-2 text-sm font-semibold text-white"
              >
                {actionLabel}
              </button>
            </div>
          ) : null}
        </>
      ) : (
        <div className="mt-3">
          <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6c7a86]">
            {emptyBody}
          </span>
        </div>
      )}
    </div>
  );
}
