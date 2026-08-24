import { useMemo, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/api/queryKeys";
import { allocatePick, createPickTasks } from "../../shared/api/picking";
import { fetchClients } from "../../shared/api/clients";
import { fetchOutboundOrderDetail } from "../../shared/api/outboundOrders";
import { fetchSetupProgress } from "../../shared/api/setup";
import { fetchTasks } from "../../shared/api/tasks";
import { getApiErrorMessage } from "../../shared/api/error-message";
import {
  fetchOutboundOrderListPage,
  ORDER_LIST_BATCH_SIZE,
} from "../../shared/api/orderLists";
import {
  fetchPickingWorkbenchSummary,
  workbenchSummaryKeys,
} from "../../shared/api/workbenchSummaries";
import DataTable from "../../shared/components/DataTable";
import ActionButton from "../../shared/components/ActionButton";
import Eyebrow from "../../shared/components/Eyebrow";
import StatusBadge from "../../shared/components/StatusBadge";
import TaskCard from "../../shared/components/TaskCard";
import PickingFlow from "./PickingFlow";
import { AlertCircle, ArrowLeft, ArrowRight, ClipboardList } from "lucide-react";
import { useI18n } from "../../shared/i18n";
import UpstreamActionLink from "../../shared/components/UpstreamActionLink";
import { checklistHref } from "../../shared/utils/checklistHref";

export default function PickingPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"orders" | "work">("orders");
  const [selectedOrder, setSelectedOrder] = useState<any | null>(null);
  const [actionResult, setActionResult] = useState<{ tone: "success" | "warning"; message: string; shortages?: Record<string, number> } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [orderSortField, setOrderSortField] = useState("order_number");
  const [orderSortDirection, setOrderSortDirection] = useState<"asc" | "desc">("desc");
  const pickingOrderStatuses = ["pending", "allocated", "picking"];
  const serverOrderSortField = ["order_number", "status", "pick_readiness", "client_id", "carrier", "tracking_number"].includes(orderSortField)
    ? orderSortField
    : "created_at";

  const {
    data: orderPages,
    isLoading: ordersLoading,
    fetchNextPage: fetchNextOrderBatch,
    hasNextPage: hasMoreOrderBatches,
    isFetchingNextPage: isFetchingNextOrderBatch,
  } = useInfiniteQuery({
    queryKey: queryKeys.outboundOrders.list("picking", { statuses: pickingOrderStatuses.join(","), sortBy: serverOrderSortField, sortDirection: orderSortDirection }),
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      fetchOutboundOrderListPage({
        offset: Number(pageParam || 0),
        limit: ORDER_LIST_BATCH_SIZE,
        statuses: pickingOrderStatuses,
        sortBy: serverOrderSortField,
        sortDirection: orderSortDirection,
      }),
    getNextPageParam: (lastPage) => lastPage.nextOffset,
  });
  const orders = useMemo(
    () => orderPages?.pages.flatMap((page) => page.items) || [],
    [orderPages],
  );

  const { data: tasks = [] } = useQuery({
    queryKey: queryKeys.tasks.pick(),
    queryFn: () => fetchTasks({ status: "pending", task_type: "pick" }),
  });
  const { data: pickingWorkbenchSummary } = useQuery({
    queryKey: workbenchSummaryKeys.picking,
    queryFn: fetchPickingWorkbenchSummary,
  });

  const { data: clientsData } = useQuery({
    queryKey: queryKeys.clients.list("picking"),
    queryFn: () => fetchClients(),
  });

  const { data: setupProgress } = useQuery({
    queryKey: queryKeys.setup.progressFor("picking"),
    queryFn: fetchSetupProgress,
  });
  const { data: selectedOrderDetail, isLoading: selectedOrderLoading } = useQuery({
    queryKey: queryKeys.outboundOrders.detail(selectedOrder?.id),
    enabled: !!selectedOrder?.id,
    queryFn: () => fetchOutboundOrderDetail(selectedOrder.id),
  });

  const setupSteps = setupProgress?.steps || [];
  const clients = clientsData?.items || [];
  const clientMap = useMemo(
    () => new Map(clients.map((client: any) => [client.id, `${client.code ? `${client.code} · ` : ""}${client.name}`])),
    [clients]
  );
  const missingRequiredSteps = useMemo(
    () => setupSteps.filter((step: any) => ["warehouse", "locations", "client", "skus"].includes(step.name) && !step.done),
    [setupSteps]
  );
  const pickingReady = missingRequiredSteps.length === 0;
  const pickingStageOrders = useMemo(
    () => orders.filter((order: any) => ["pending", "allocated", "picking"].includes(order.status)),
    [orders]
  );

  const unassignedTasks = useMemo(
    () => tasks.filter((task: any) => task.assigned_type === "unassigned").length,
    [tasks]
  );

  const activeOrders = useMemo(
    () =>
      pickingWorkbenchSummary
        ? Number(pickingWorkbenchSummary.by_status.allocated || 0) + Number(pickingWorkbenchSummary.by_status.picking || 0)
        : pickingStageOrders.filter((order: any) => ["allocated", "picking"].includes(order.status)).length,
    [pickingStageOrders, pickingWorkbenchSummary]
  );
  const pickingStageOrderCount = pickingWorkbenchSummary
    ? Number(pickingWorkbenchSummary.by_status.pending || 0) +
      Number(pickingWorkbenchSummary.by_status.allocated || 0) +
      Number(pickingWorkbenchSummary.by_status.picking || 0)
    : pickingStageOrders.length;
  const releasedPickTaskCount = Math.max(Number(pickingWorkbenchSummary?.active_pick_tasks || 0), tasks.length);
  const selectedOrderView = selectedOrderDetail || selectedOrder;
  const selectedOrderStatus = selectedOrderView?.status || selectedOrder?.status || null;
  const selectedShortageBySku = actionResult?.shortages || {};
  const tabs = ["orders", "work"] as const;
  const pickWorkflowSteps = [
    {
      step: "01",
      title: t("picking.workflowAllocateTitle", "Allocate stock"),
      body: t("picking.workflowAllocateBody", "Start from a pending outbound order and reserve available inventory."),
      active: activeTab === "orders" || selectedOrderStatus === "pending",
    },
    {
      step: "02",
      title: t("picking.workflowReleaseTitle", "Release tasks"),
      body: t("picking.workflowReleaseBody", "Turn an allocated order into executable pick tasks."),
      active: selectedOrderStatus === "allocated",
    },
    {
      step: "03",
      title: t("picking.workflowScanTitle", "Scan picks"),
      body: t("picking.workflowScanBody", "{count} released tasks are ready for location and SKU scan.", { count: releasedPickTaskCount }),
      active: activeTab === "work" || releasedPickTaskCount > 0,
    },
    {
      step: "04",
      title: t("picking.workflowShippingTitle", "Hand off to shipping"),
      body: t("picking.workflowShippingBody", "Picked orders move to Shipping for packing and carrier confirmation."),
      active: false,
    },
  ];

  const refreshPickingWork = async (orderId: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.list() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.list("picking-flow") }),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.pick() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.myPick() }),
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.picking }),
      queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.detail(orderId) }),
    ]);
  };

  const allocateMutation = useMutation({
    mutationFn: (orderId: string) => allocatePick(orderId),
    onSuccess: async (data: any, orderId: string) => {
      setActionError(null);
      const shortages = Object.fromEntries(
        (data?.lines || [])
          .filter((line: any) => Number(line.shortage || 0) > 0)
          .map((line: any) => [line.sku_id, Number(line.shortage || 0)])
      );
      const shortageTotal = Object.values(shortages).reduce((sum: number, value) => sum + Number(value || 0), 0);
      setActionResult(
        data?.fully_allocated
          ? {
              tone: "success",
              message: t("picking.allocateSuccess", "Stock allocated. This order can now be released to pick tasks."),
            }
          : {
              tone: "warning",
              message: t("picking.allocateShortage", "Cannot release pick tasks yet. This order is short {count} units.", { count: shortageTotal }),
              shortages,
            }
      );
      await refreshPickingWork(orderId);
    },
    onError: (error: any) => {
      setActionResult(null);
      setActionError(getApiErrorMessage(error, t("picking.allocateError", "Could not allocate stock for this order.")));
    },
  });

  const releaseTasksMutation = useMutation({
    mutationFn: (orderId: string) => createPickTasks(orderId),
    onSuccess: async (data: any, orderId: string) => {
      setActionError(null);
      setActionResult({
        tone: "success",
        message: t("picking.releaseSuccess", "{count} pick tasks released.", { count: data?.task_ids?.length || 0 }),
      });
      await refreshPickingWork(orderId);
      setActiveTab("work");
    },
    onError: (error: any) => {
      setActionResult(null);
      setActionError(getApiErrorMessage(error, t("picking.releaseError", "Could not release pick tasks for this order.")));
    },
  });

  const pickReadinessContent = (row: any) => {
    const shortage = Number(row.pick_shortage_units || 0);
    const totalItems = Number(row.total_items || 0);
    const totalAllocated = Number(row.total_allocated || 0);
    const readiness = row.pick_readiness || "not_applicable";
    const config =
      readiness === "short_stock"
        ? {
            label: t("picking.readinessShort", "Short {count}", { count: shortage }),
            meta: t("picking.readinessShortMeta", "{allocated}/{total} allocated", {
              allocated: totalAllocated,
              total: totalItems,
            }),
            className: "border-[#e6c06a]/55 bg-[#fff8e8] text-[#8a5b00]",
          }
        : readiness === "ready_to_release"
        ? {
            label: t("picking.readinessRelease", "Ready to release"),
            meta: t("picking.readinessReleaseMeta", "Create pick tasks"),
            className: "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]",
          }
        : readiness === "pick_tasks_released"
        ? {
            label: t("picking.readinessTasksReady", "Pick tasks ready"),
            meta: t("picking.readinessTasksReadyMeta", "Start picking"),
            className: "border-[#8db6ff]/45 bg-[#eef5ff] text-[#245da8]",
          }
        : readiness === "ready_to_allocate"
        ? {
            label: t("picking.readinessAllocate", "Ready to allocate"),
            meta: t("picking.readinessAllocateMeta", "Stock available now"),
            className: "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]",
          }
        : readiness === "no_lines"
        ? {
            label: t("picking.readinessNoLines", "No lines"),
            meta: t("picking.readinessNoLinesMeta", "Add order lines first"),
            className: "border-[#e4c1b8] bg-[#fff1ed] text-[#8f3627]",
          }
        : {
            label: t("picking.readinessNotInPickFlow", "Not in pick flow"),
            meta: t("picking.readinessNotInPickFlowMeta", "{allocated}/{total} allocated", {
              allocated: totalAllocated,
              total: totalItems,
            }),
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

  const pickReadinessSortRank: Record<string, number> = {
    short_stock: 10,
    ready_to_allocate: 20,
    ready_to_release: 30,
    pick_tasks_released: 40,
    pick_tasks_ready: 40,
    ready_to_pack: 50,
    ready_to_ship: 60,
    shipped: 70,
    no_lines: 80,
    not_applicable: 90,
  };

  const getOrderComparable = (row: any) => {
    if (orderSortField === "client_id") return clientMap.get(row.client_id) || row.client_id || "";
    if (orderSortField === "pick_readiness") {
      const readiness = row.pick_readiness || "not_applicable";
      return pickReadinessSortRank[readiness] ?? 99;
    }
    return row?.[orderSortField] ?? "";
  };

  const sortedPickingStageOrders = useMemo(
    () =>
      pickingStageOrders
        .map((row: any, index: number) => ({ row, index }))
        .sort((left, right) => compareRows(left, right, getOrderComparable, orderSortDirection))
        .map(({ row }) => row),
    [pickingStageOrders, orderSortField, orderSortDirection, clientMap]
  );

  const handleOrderHeaderClick = (key: string) => {
    if (!["order_number", "status", "pick_readiness", "client_id", "carrier", "tracking_number"].includes(key)) return;
    if (orderSortField === key) {
      setOrderSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setOrderSortField(key);
    setOrderSortDirection("asc");
  };

  const mobileOrderActionLabel = (order: any) => {
    if (order.status === "pending") return t("picking.allocateStock", "Allocate stock");
    if (order.status === "allocated") return t("picking.releasePickTasks", "Release pick tasks");
    if (order.status === "picking") return t("picking.startPicking", "Picking Work");
    return t("picking.reviewOrder", "Review order");
  };
  const pickingMobilePath =
    releasedPickTaskCount > 0
      ? "scan"
      : ["pending", "allocated"].includes(sortedPickingStageOrders[0]?.status || "")
        ? "allocate"
        : sortedPickingStageOrders[0]
          ? "exception"
          : "allocate";

  const orderColumns = [
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
      key: "pick_readiness",
      header: t("picking.pickReadiness", "Pick readiness"),
      sortable: true,
      render: pickReadinessContent,
    },
    {
      key: "client_id",
      header: t("common.client", "Client"),
      sortable: true,
      render: (row: any) => clientMap.get(row.client_id) || row.client_id,
    },
    { key: "carrier", header: t("shipping.carrier", "Carrier"), sortable: true },
    { key: "tracking_number", header: t("shipping.tracking", "Tracking"), sortable: true },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <Eyebrow className="text-xs tracking-[0.24em]">{t("picking.eyebrow", "Outbound execution")}</Eyebrow>
          <h1 className="mt-2 text-2xl font-semibold text-[#13212c] md:text-3xl md:tracking-[-0.04em]">{t("picking.title", "Picking & Fulfillment")}</h1>
        </div>
        <div className="hidden flex-wrap items-center gap-3 md:flex">
          <UpstreamActionLink to="/migration" label={t("picking.openImportCenter", "Open import center")} />
        </div>
      </div>

      {!pickingReady && (
        <ReadinessGate
          eyebrow={t("picking.readinessEyebrow", "Picking readiness gate")}
          title={t("picking.readinessTitle", "Finish warehouse and item setup before releasing live outbound work")}
          body={t(
            "picking.readinessBody",
            "Picking depends on real warehouse structure, storage locations, client accounts, and SKU master data. Without that foundation, outbound work becomes guesswork instead of executable warehouse flow."
          )}
          nextLabel={t("picking.readinessNext", "Next recommended step:")}
          steps={missingRequiredSteps}
          t={t}
        />
      )}

      {pickingReady ? (
        <>
        <section
          className="rounded-[1.35rem] border border-[#13212c]/10 bg-white/88 p-4 shadow-[0_16px_34px_rgba(19,33,44,0.06)] md:hidden"
          data-testid="picking-mobile-next-action"
          data-picking-path={pickingMobilePath}
        >
          <TaskCard
            label={t("picking.mobileNextActionLabel", "Next action")}
            title={
              releasedPickTaskCount > 0
                ? t("picking.startPicking", "Picking Work")
                : sortedPickingStageOrders[0]
                  ? mobileOrderActionLabel(sortedPickingStageOrders[0])
                  : t("picking.mobileNoPickWorkTitle", "No picking action")}
            meta={
              releasedPickTaskCount > 0
                ? t("picking.mobileReleasedTasksMeta", "{count} released tasks ready to scan", {
                    count: releasedPickTaskCount,
                  })
                : sortedPickingStageOrders[0]
                  ? sortedPickingStageOrders[0].order_number
                  : t("picking.mobileNoPickWorkMeta", "Outbound picking is caught up.")
            }
            selected={releasedPickTaskCount > 0 || sortedPickingStageOrders.length > 0}
            tone={releasedPickTaskCount > 0 || sortedPickingStageOrders.length > 0 ? "neutral" : "success"}
            onClick={
              releasedPickTaskCount > 0
                ? () => setActiveTab("work")
                : sortedPickingStageOrders[0]
                  ? () => {
                      setSelectedOrder(sortedPickingStageOrders[0]);
                      setActiveTab("orders");
                      setActionResult(null);
                      setActionError(null);
                    }
                  : undefined
            }
            action={
              releasedPickTaskCount > 0 || sortedPickingStageOrders.length > 0 ? (
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#24507a] text-white">
                  <ArrowRight size={15} />
                </span>
              ) : null
            }
          />
          <details
            className="mt-3 rounded-[1rem] border border-[#13212c]/8 bg-[#fffdfa] px-3 py-2"
            data-testid="picking-mobile-queue-counts"
          >
            <summary className="cursor-pointer list-none text-xs font-semibold text-[#51606b]">
              {t("picking.mobileQueueCounts", "View counts")}
            </summary>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fbf8f2] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#7f8d98]">{t("picking.mobileOrdersShort", "Orders")}</p>
                <p className="mt-1 text-lg font-semibold text-[#13212c]">{pickingStageOrderCount}</p>
              </div>
              <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fbf8f2] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#7f8d98]">{t("picking.mobileActiveShort", "Active")}</p>
                <p className="mt-1 text-lg font-semibold text-[#13212c]">{activeOrders}</p>
              </div>
              <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fff7e8] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#8a6511]">{t("picking.mobileTasksShort", "Tasks")}</p>
                <p className="mt-1 text-lg font-semibold text-[#13212c]">{releasedPickTaskCount}</p>
              </div>
            </div>
          </details>
        </section>

        <section className="hidden rounded-[2rem] border border-[#13212c]/10 bg-white/84 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] md:block">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <Eyebrow className="tracking-[0.22em]">{t("picking.workbenchEyebrow", "Picking queue")}</Eyebrow>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-[#13212c]">
                {t("picking.workbenchTitle", "Review orders ready to pick, then start picking after tasks are released")}
              </h2>
            </div>
            {releasedPickTaskCount > 0 ? (
              <ActionButton
                onClick={() => setActiveTab("work")}
                className="w-fit text-[11px]"
              >
                {t("picking.startPicking", "Picking Work")}
              </ActionButton>
            ) : null}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
              {t("picking.ordersReadyChip", "{count} orders ready", { count: pickingStageOrderCount })}
            </span>
            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("picking.activeOrdersChip", "{count} in picking", { count: activeOrders })}
            </span>
            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("picking.pendingTasksChip", "{count} released tasks", { count: releasedPickTaskCount })}
            </span>
            {unassignedTasks > 0 ? (
              <span className="rounded-full border border-[#f7bf45]/28 bg-[#fff7e8] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8a6511]">
                {t("picking.unassignedTasksChip", "{count} unassigned", { count: unassignedTasks })}
              </span>
            ) : null}
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {pickWorkflowSteps.map((step) => (
              <div
                key={step.step}
                className={`rounded-[1.15rem] border px-4 py-4 ${
                  step.active
                    ? "border-[#13212c]/18 bg-[#fffdfa] shadow-[0_10px_28px_rgba(19,33,44,0.06)]"
                    : "border-[#13212c]/8 bg-[#f7f4ee]"
                }`}
              >
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("picking.workflowStep", "Step")} {step.step}
                </p>
                <p className="mt-2 text-sm font-semibold text-[#13212c]">{step.title}</p>
                <p className="mt-1.5 text-xs leading-5 text-[#61717d]">{step.body}</p>
              </div>
            ))}
          </div>
        </section>
        </>
      ) : null}

      {/* Tabs */}
      <div className="hidden w-fit gap-1 rounded-2xl bg-[#ebe5db] p-1.5 md:flex">
        {tabs.map((tab) => {
          const disabled = !pickingReady || (tab === "work" && releasedPickTaskCount === 0);
          return (
          <button
            key={tab}
            onClick={() => {
              if (disabled) return;
              setActiveTab(tab);
            }}
            disabled={disabled}
            className={`rounded-[1rem] px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-white text-[#13212c] shadow-sm"
                : disabled
                  ? "cursor-not-allowed text-[#9aa4ac]"
                  : "text-[#6c7a86] hover:text-[#13212c]"
            }`}
          >
            {tab === "orders"
              ? t("picking.outboundOrders", "Outbound Orders")
              : t("picking.startPicking", "Picking Work")}
          </button>
          );
        })}
      </div>

      {activeTab === "orders" && (
        <div className="space-y-4">
          {selectedOrder ? (
            <>
            <section className="max-w-full overflow-hidden rounded-[1.35rem] border border-[#13212c]/10 bg-white/92 p-4 shadow-[0_16px_32px_rgba(19,33,44,0.05)] md:hidden">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("picking.mobileCurrentFocus", "Current picking focus")}
                  </p>
                  <h2 className="mt-2 break-words text-lg font-semibold text-[#13212c]">
                    {selectedOrderView?.order_number || selectedOrder?.order_number}
                  </h2>
                  <p className="mt-1 text-sm text-[#61717d]">
                    {selectedOrderStatus ? mobileOrderActionLabel({ status: selectedOrderStatus }) : t("picking.reviewOrder", "Review order")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedOrder(null);
                    setActionResult(null);
                    setActionError(null);
                  }}
                  className="inline-flex min-h-[44px] shrink-0 items-center gap-1 rounded-full border border-[#13212c]/10 bg-[#fbf8f2] px-3 py-2 text-xs font-semibold text-[#13212c]"
                >
                  <ArrowLeft size={14} />
                  {t("picking.mobileBackToOrders", "Back")}
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {selectedOrderStatus ? <StatusBadge status={selectedOrderStatus} /> : null}
                <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                  {clientMap.get(selectedOrderView?.client_id) || selectedOrderView?.client_id || t("common.client", "Client")}
                </span>
              </div>

              <div className="mt-4 grid gap-2">
                {selectedOrderStatus === "pending" ? (
                  <button
                    type="button"
                    onClick={() => selectedOrder?.id && allocateMutation.mutate(selectedOrder.id)}
                    disabled={allocateMutation.isPending}
                    className="min-h-[44px] rounded-full bg-[#13212c] px-4 py-2 text-sm font-semibold text-[#f4efe8] disabled:cursor-not-allowed disabled:bg-[#9ca7af]"
                  >
                    {allocateMutation.isPending ? t("picking.allocating", "Allocating...") : t("picking.allocateStock", "Allocate stock")}
                  </button>
                ) : null}
                {selectedOrderStatus === "allocated" ? (
                  <button
                    type="button"
                    onClick={() => selectedOrder?.id && releaseTasksMutation.mutate(selectedOrder.id)}
                    disabled={releaseTasksMutation.isPending}
                    className="min-h-[44px] rounded-full bg-[#13212c] px-4 py-2 text-sm font-semibold text-[#f4efe8] disabled:cursor-not-allowed disabled:bg-[#9ca7af]"
                  >
                    {releaseTasksMutation.isPending ? t("picking.releasing", "Releasing...") : t("picking.releasePickTasks", "Release pick tasks")}
                  </button>
                ) : null}
                {selectedOrderStatus === "picking" ? (
                  <button
                    type="button"
                    onClick={() => setActiveTab("work")}
                    className="min-h-[44px] rounded-full bg-[#13212c] px-4 py-2 text-sm font-semibold text-[#f4efe8]"
                  >
                    {t("picking.startPicking", "Picking Work")}
                  </button>
                ) : null}
              </div>

              {actionResult ? (
                <div
                  className={`mt-4 rounded-[1rem] border px-4 py-3 text-sm font-medium ${
                    actionResult.tone === "warning"
                      ? "border-[#e6c06a]/50 bg-[#fff8e8] text-[#8a5b00]"
                      : "border-[#8edbb4]/40 bg-[#eefaf3] text-[#24734a]"
                  }`}
                >
                  {actionResult.message}
                  {actionResult.tone === "warning" ? (
                    <div className="mt-2 text-xs leading-5 text-[#7a6738]">
                      {t("picking.shortageNextStep", "Add or receive enough stock, correct the inventory balance, or reduce the outbound quantity. Then allocate stock again; once every line is allocated, Release pick tasks will be available.")}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {actionError ? (
                <div className="mt-4 rounded-[1rem] border border-[#f1a39b]/50 bg-[#fff1ef] px-4 py-3 text-sm font-medium text-[#b8463b]">
                  {actionError}
                </div>
              ) : null}
              {selectedOrderLoading ? (
                <div className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-5 text-sm text-[#61717d]">
                  {t("common.loading", "Loading...")}
                </div>
              ) : selectedOrderDetail?.lines?.length ? (
                <details className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#fffdfa] p-3" open={actionResult?.tone === "warning"}>
                  <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                    {t("picking.mobileLineDetails", "Line details and stock readiness")}
                  </summary>
                  <div className="mt-3 grid gap-3">
                    {selectedOrderDetail.lines.map((line: any) => (
                      <div key={`mobile-${line.line_id}`} className="rounded-[1rem] border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="break-words text-sm font-semibold text-[#13212c]">{line.sku_code}</p>
                            <p className="mt-1 text-xs leading-5 text-[#61717d]">{line.sku_name}</p>
                          </div>
                          <span className="max-w-[9rem] shrink-0 break-words rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold text-[#61717d]">
                            {line.pick_location || t("picking.noPickLocation", "No pick location")}
                          </span>
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2">
                          <TaskMiniStat label={t("picking.ordered", "Ordered")} value={String(line.quantity_ordered)} />
                          <TaskMiniStat label={t("picking.allocated", "Allocated")} value={String(line.quantity_allocated)} />
                          <TaskMiniStat label={t("picking.picked", "Picked")} value={String(line.quantity_picked)} />
                        </div>
                        {selectedShortageBySku[line.sku_id] ? (
                          <div className="mt-3 rounded-[0.9rem] border border-[#e6c06a]/45 bg-[#fff8e8] px-3 py-2 text-xs font-medium text-[#8a5b00]">
                            {t("picking.lineShortage", "Short by {count} units", { count: selectedShortageBySku[line.sku_id] })}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </details>
              ) : null}
            </section>

            <section className="hidden rounded-[1.6rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex items-start gap-3">
                  <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#4f7fd9]">
                    <ClipboardList size={18} />
                  </div>
                  <div>
                    <Eyebrow className="tracking-[0.22em]">
                      {t("picking.selectedOrder", "Selected outbound order")}
                    </Eyebrow>
                    <h2 className="mt-1 text-lg font-semibold text-[#13212c]">
                      {selectedOrderView?.order_number || selectedOrder?.order_number}
                    </h2>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {selectedOrderStatus ? <StatusBadge status={selectedOrderStatus} /> : null}
                      <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                        {clientMap.get(selectedOrderView?.client_id) || selectedOrderView?.client_id || t("common.client", "Client")}
                      </span>
                      {selectedOrderView?.reference_number ? (
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                          {selectedOrderView.reference_number}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {selectedOrderStatus === "pending" ? (
                    <button
                      type="button"
                      onClick={() => selectedOrder?.id && allocateMutation.mutate(selectedOrder.id)}
                      disabled={allocateMutation.isPending}
                      className="rounded-full bg-[#13212c] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1f3240] disabled:cursor-not-allowed disabled:bg-[#9ca7af]"
                    >
                      {allocateMutation.isPending
                        ? t("picking.allocating", "Allocating...")
                        : t("picking.allocateStock", "Allocate stock")}
                    </button>
                  ) : null}
                  {selectedOrderStatus === "allocated" ? (
                    <button
                      type="button"
                      onClick={() => selectedOrder?.id && releaseTasksMutation.mutate(selectedOrder.id)}
                      disabled={releaseTasksMutation.isPending}
                      className="rounded-full bg-[#13212c] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1f3240] disabled:cursor-not-allowed disabled:bg-[#9ca7af]"
                    >
                      {releaseTasksMutation.isPending
                        ? t("picking.releasing", "Releasing...")
                        : t("picking.releasePickTasks", "Release pick tasks")}
                    </button>
                  ) : null}
                  {selectedOrderStatus === "picking" ? (
                    <ActionButton
                      onClick={() => setActiveTab("work")}
                      className="text-[11px]"
                    >
                      {t("picking.startPicking", "Picking Work")}
                    </ActionButton>
                  ) : null}
                  <ActionButton
                    variant="secondary"
                    onClick={() => {
                      setSelectedOrder(null);
                      setActionResult(null);
                      setActionError(null);
                    }}
                    className="text-[11px]"
                  >
                    {t("common.close", "Close")}
                  </ActionButton>
                </div>
              </div>

              {actionResult ? (
                <div
                  className={`mt-4 rounded-[1rem] border px-4 py-3 text-sm font-medium ${
                    actionResult.tone === "warning"
                      ? "border-[#e6c06a]/50 bg-[#fff8e8] text-[#8a5b00]"
                      : "border-[#8edbb4]/40 bg-[#eefaf3] text-[#24734a]"
                  }`}
                >
                  {actionResult.message}
                  {actionResult.tone === "warning" ? (
                    <div className="mt-2 text-xs leading-5 text-[#7a6738]">
                      {t("picking.shortageNextStep", "Add or receive enough stock, correct the inventory balance, or reduce the outbound quantity. Then allocate stock again; once every line is allocated, Release pick tasks will be available.")}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {actionError ? (
                <div className="mt-4 rounded-[1rem] border border-[#f1a39b]/50 bg-[#fff1ef] px-4 py-3 text-sm font-medium text-[#b8463b]">
                  {actionError}
                </div>
              ) : null}

              {selectedOrderLoading ? (
                <div className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-5 text-sm text-[#61717d]">
                  {t("common.loading", "Loading...")}
                </div>
              ) : selectedOrderDetail?.lines?.length ? (
                <div className="mt-5 grid gap-3 lg:grid-cols-2">
                  {selectedOrderDetail.lines.map((line: any) => (
                    <div key={line.line_id} className="rounded-[1.15rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[#13212c]">{line.sku_code}</p>
                          <p className="mt-1 text-sm text-[#61717d]">{line.sku_name}</p>
                        </div>
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold text-[#61717d]">
                          {line.pick_location || t("picking.noPickLocation", "No pick location")}
                        </span>
                      </div>
                      <div className="mt-4 grid grid-cols-3 gap-2">
                        <TaskMiniStat label={t("picking.ordered", "Ordered")} value={String(line.quantity_ordered)} />
                        <TaskMiniStat label={t("picking.allocated", "Allocated")} value={String(line.quantity_allocated)} />
                        <TaskMiniStat label={t("picking.picked", "Picked")} value={String(line.quantity_picked)} />
                      </div>
                      {selectedShortageBySku[line.sku_id] ? (
                        <div className="mt-3 rounded-[0.9rem] border border-[#e6c06a]/45 bg-[#fff8e8] px-3 py-2 text-xs font-medium text-[#8a5b00]">
                          {t("picking.lineShortage", "Short by {count} units", { count: selectedShortageBySku[line.sku_id] })}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
            </>
          ) : null}

          {!selectedOrder ? (
            <div className="space-y-2 md:hidden">
              <div className="px-1">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("picking.mobileOrderQueueEyebrow", "Outbound queue")}
                </p>
              </div>
              <details className="rounded-[1rem] border border-[#13212c]/8 bg-[#fffdfa] px-3 py-2">
                <summary className="cursor-pointer list-none text-xs font-semibold text-[#51606b]">
                  {t("picking.mobileSortQueue", "Sort queue")}
                </summary>
                <div className="mt-3 flex flex-wrap gap-2">
                  {orderColumns
                    .filter((column) => "sortable" in column && column.sortable)
                    .slice(0, 5)
                    .map((column) => (
                      <button
                        key={`mobile-picking-sort-${column.key}`}
                        type="button"
                        onClick={() => handleOrderHeaderClick(column.key)}
                        className={`inline-flex min-h-[44px] items-center gap-1 rounded-full border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] ${
                          orderSortField === column.key
                            ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                            : "border-[#13212c]/10 bg-white text-[#61717d]"
                        }`}
                      >
                        <span>{column.header}</span>
                        <span>{orderSortField === column.key ? (orderSortDirection === "asc" ? "↑" : "↓") : "↕"}</span>
                      </button>
                    ))}
                </div>
              </details>
              {ordersLoading ? (
                <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white/80 px-4 py-6 text-center text-sm text-[#7f8e98]">
                  {t("common.loading", "Loading...")}
                </div>
              ) : sortedPickingStageOrders.length === 0 ? (
                <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white/80 px-4 py-6 text-sm text-[#61717d]">
                  <p className="font-semibold text-[#13212c]">{t("picking.emptyOrders", "No outbound orders")}</p>
                  <p className="mt-2 leading-6">
                    {t("picking.emptyOrdersHint", "Outbound work starts after clients, inventory, and orders are in place.")}
                  </p>
                  <a
                    href="/clients"
                    className="mt-4 inline-flex min-h-[44px] items-center justify-center rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8]"
                  >
                    {t("picking.reviewClients", "Review clients")}
                  </a>
                </div>
              ) : (
                sortedPickingStageOrders.map((row: any) => (
                  <TaskCard
                    key={row.id}
                    label={t("picking.mobileOrderQueueItemLabel", "Outbound order")}
                    title={row.order_number}
                    meta={mobileOrderActionLabel(row)}
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
                    onClick={() => {
                      setSelectedOrder(row);
                      setActionResult(null);
                      setActionError(null);
                    }}
                  />
                ))
              )}
            </div>
          ) : null}

          <div className="hidden md:block">
            <DataTable
              columns={orderColumns}
              data={sortedPickingStageOrders}
              loading={ordersLoading}
              emptyMessage={t("picking.emptyOrders", "No outbound orders")}
              emptyHint={t("picking.emptyOrdersHint", "Outbound work starts after clients, inventory, and orders are in place.")}
              emptyActionLabel={t("picking.reviewClients", "Review clients")}
              emptyActionHref="/clients"
              onHeaderClick={handleOrderHeaderClick}
              sortField={orderSortField}
              sortDirection={orderSortDirection}
              onRowClick={(row: any) => {
                setSelectedOrder(row);
                setActionResult(null);
                setActionError(null);
              }}
            />
          </div>
          {hasMoreOrderBatches ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.4rem] border border-[#24507a]/12 bg-[#eef3f8] px-4 py-3 text-sm text-[#51606b]">
              <p>
                {t("picking.moreOrdersAvailable", "{count} orders loaded. More outbound orders are available from the server.", {
                  count: String(orders.length),
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
                  : t("picking.loadMoreOrders", "Load more orders")}
              </button>
            </div>
          ) : null}
        </div>
      )}

      {activeTab === "work" && <PickingFlow />}
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

function TaskMiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-3 py-3">
      <p className="text-[10px] uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}
