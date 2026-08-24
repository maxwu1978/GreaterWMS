/**
 * Interactive picking workflow — guided pick-by-task flow.
 *
 * Steps:
 * 1. Load assigned pick tasks (sorted by pick path)
 * 2. Navigate to location → scan location barcode to confirm
 * 3. Scan SKU barcode → enter quantity → confirm pick
 * 4. Move to next task until all picks done
 * 5. Proceed to packing
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/api/queryKeys";
import { fetchTasks } from "../../shared/api/tasks";
import { getApiErrorCode, getApiErrorMessage } from "../../shared/api/error-message";
import { requestWithOutbox } from "../../shared/offline/mutations";
import { isOfflineMutationQueuedError } from "../../shared/offline/outbox";
import {
  fetchOutboundOrderListPage,
  ORDER_LIST_BATCH_SIZE,
} from "../../shared/api/orderLists";
import { workbenchSummaryKeys } from "../../shared/api/workbenchSummaries";
import { useAuthStore } from "../../shared/hooks/useAuth";
import BarcodeScanner from "../../scanner/BarcodeScanner";
import { ArrowLeft } from "lucide-react";
import { type MobileFlowStepItem } from "../../shared/components/MobileFlowGuide";
import WorkflowRecoveryPanel from "../../shared/components/WorkflowRecoveryPanel";
import { useI18n } from "../../shared/i18n";

interface PickTask {
  id: string;
  sku_id: string;
  quantity: number;
  reference_id?: string | null;
  source_location_id: string;
  source_location_barcode?: string | null;
  destination_location_barcode?: string | null;
  sku_code?: string | null;
  sku_barcode?: string | null;
  status: string;
  assigned_to?: string | null;
}

type PickRecoveryAction =
  | "scan_again"
  | "back_to_list"
  | "refresh_tasks"
  | "adjust_quantity"
  | "open_picking_list";

interface PickRecoveryState {
  code: string;
  title: string;
  body: string;
  actions: PickRecoveryAction[];
}
type PickRecoveryKind = "task_not_available" | "quantity_rejected" | "stock_changed";

const pickRecoveryCodeKinds: Record<string, PickRecoveryKind> = {
  pick_task_not_found: "task_not_available",
  pick_task_already_completed: "task_not_available",
  pick_task_cancelled: "task_not_available",
  pick_task_assigned_to_agv: "task_not_available",
  pick_task_assigned_to_other_operator: "task_not_available",
  pick_quantity_non_positive: "quantity_rejected",
  pick_quantity_exceeds_task: "quantity_rejected",
  pick_quantity_exceeds_reserved: "quantity_rejected",
  pick_insufficient_stock: "stock_changed",
  pick_source_inventory_not_found: "stock_changed",
};

function classifyPickRecoveryCode(code: string | null): PickRecoveryKind | null {
  if (!code) return null;
  return pickRecoveryCodeKinds[code] || null;
}

function decodeTokenSubject(token: string | null) {
  if (!token) return null;

  try {
    const payload = token.split(".")[1];
    if (!payload) return null;

    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const parsed = JSON.parse(atob(padded));
    return typeof parsed.sub === "string" && parsed.sub ? parsed.sub : null;
  } catch {
    return null;
  }
}

async function fetchPickTasksForFlow(currentUserId: string | null) {
  if (currentUserId) {
    const assignedResponses = await Promise.all([
      fetchTasks<PickTask[]>({ status: "assigned", assigned_type: "human", assigned_to: currentUserId, task_type: "pick", limit: 500 }),
      fetchTasks<PickTask[]>({ status: "in_progress", assigned_type: "human", assigned_to: currentUserId, task_type: "pick", limit: 500 }),
    ]);
    const assignedTasks = assignedResponses.flat();

    if (assignedTasks.length > 0) {
      return assignedTasks;
    }
  }

  return fetchTasks<PickTask[]>({ status: "pending", assigned_type: "unassigned", task_type: "pick", limit: 500 });
}

export default function PickingFlow() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const currentUserId = useMemo(() => decodeTokenSubject(token), [token]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [phase, setPhase] = useState<"location" | "sku" | "confirm">("location");
  const [locationConfirmed, setLocationConfirmed] = useState(false);
  const [skuConfirmed, setSkuConfirmed] = useState(false);
  const [pickedQty, setPickedQty] = useState(0);
  const [recovery, setRecovery] = useState<PickRecoveryState | null>(null);
  const [completedPick, setCompletedPick] = useState<{ orderNumber?: string | null; taskCount: number } | null>(null);
  const offlineQueuedText = () =>
    t("offline.mutationQueued", "Saved offline. It will sync automatically when the connection is back.");

  // Load pending pick tasks
  const { data: tasks = [], isLoading, isFetching: isFetchingTasks, refetch: refetchTasks } = useQuery<PickTask[]>({
    queryKey: queryKeys.tasks.myPick(currentUserId),
    queryFn: () => fetchPickTasksForFlow(currentUserId),
  });

  const { data: orders = [] } = useQuery<any[]>({
    queryKey: queryKeys.outboundOrders.list("picking-flow"),
    queryFn: () =>
      fetchOutboundOrderListPage({
        statuses: ["picking"],
        limit: ORDER_LIST_BATCH_SIZE,
      }).then((page) => page.items),
  });

  const confirmMutation = useMutation({
    mutationFn: (data: { task_id: string; quantity_picked: number }) =>
      requestWithOutbox<any>({
        url: "/fulfillment/pick/confirm",
        data,
        scope: "picking.confirm",
        description: `Confirm pick task ${data.task_id}`,
      }),
    onSuccess: async (result) => {
      const response = result.data;
      if (response?.success === false) {
        const responseDetail = response.detail && typeof response.detail === "object" ? response.detail : null;
        const responseCode = response.error_code || responseDetail?.error_code || responseDetail?.code || null;
        const responseMessage =
          response.error ||
          responseDetail?.message ||
          responseDetail?.error ||
          t("picking.confirmError", "Pick confirmation failed.");
        setRecovery(
          confirmFailureRecovery(
            responseMessage,
            responseCode,
          )
        );
        return;
      }
      const completingLastTask = tasks.length <= 1;
      const completedTask = tasks.find((candidate) => candidate.id === selectedTaskId);
      const completedOrder = orders.find((order) => order.id === completedTask?.reference_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.myPick() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.pick() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.list() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.shipping.orders() }),
        queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.picking }),
      ]);
      setSelectedTaskId(null);
      resetPhase();
      if (completingLastTask) {
        setCompletedPick({
          orderNumber: completedOrder?.order_number || completedTask?.reference_id || null,
          taskCount: tasks.length,
        });
      }
    },
    onError: (error) => {
      if (isOfflineMutationQueuedError(error)) {
        setRecovery(confirmFailureRecovery(offlineQueuedText()));
        return;
      }
      setRecovery(
        confirmFailureRecovery(
          getApiErrorMessage(error, t("picking.confirmError", "Pick confirmation failed.")),
          getApiErrorCode(error),
        )
      );
    },
  });

  const resetPhase = () => {
    setPhase("location");
    setLocationConfirmed(false);
    setSkuConfirmed(false);
    setPickedQty(0);
    setRecovery(null);
  };

  const openTask = (taskId: string) => {
    setSelectedTaskId(taskId);
    setCompletedPick(null);
    resetPhase();
  };

  const returnToPickList = () => {
    setSelectedTaskId(null);
    setCompletedPick(null);
    resetPhase();
  };

  const refreshTaskViews = async () => {
    await Promise.all([
      refetchTasks(),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.pick() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.outboundOrders.list() }),
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.picking }),
    ]);
  };

  const normalizeScan = (value: string | null | undefined) =>
    (value || "").trim().toLowerCase().replace(/\s+/g, "");

  const matchesExpected = (barcode: string, expectedValues: Array<string | null | undefined>) => {
    const scan = normalizeScan(barcode);
    return expectedValues.some((value) => value && normalizeScan(value) === scan);
  };

  const confirmFailureRecovery = (detail: string, code: string | null = null): PickRecoveryState => {
    const recoveryKind = classifyPickRecoveryCode(code);
    if (recoveryKind === "task_not_available") {
      return {
        code: code || "task_not_available",
        title: t("picking.recoveryTaskNotAvailableTitle", "This pick task is no longer open"),
        body: t("picking.recoveryTaskNotAvailableBody", "The task may have been completed, cancelled, or changed on another screen. Refresh the work queue before picking more stock."),
        actions: ["refresh_tasks", "back_to_list"],
      };
    }
    if (recoveryKind === "quantity_rejected") {
      return {
        code: code || "quantity_rejected",
        title: t("picking.recoveryConfirmQuantityTitle", "Check the picked quantity"),
        body: detail || t("picking.recoveryConfirmQuantityBody", "The system did not accept this quantity. Adjust the count to the task quantity, then confirm again."),
        actions: ["adjust_quantity", "scan_again", "back_to_list"],
      };
    }
    if (recoveryKind === "stock_changed") {
      return {
        code: code || "stock_changed",
        title: t("picking.recoveryConfirmStockTitle", "Stock changed before confirmation"),
        body: detail || t("picking.recoveryConfirmStockBody", "Available stock at this slot changed before the pick was confirmed. Refresh tasks and choose the next valid pick."),
        actions: ["refresh_tasks", "open_picking_list"],
      };
    }
    return {
      code: code || "confirm_failed",
      title: t("picking.recoveryConfirmFailedTitle", "Pick was not confirmed"),
      body: detail || t("picking.recoveryConfirmFailedBody", "The system could not save this pick. Keep the stock at the source location, then retry or return to the pick list."),
      actions: ["scan_again", "refresh_tasks", "back_to_list"],
    };
  };

  if (isLoading) {
    return <div className="p-8 text-center text-gray-400">{t("picking.loadingTasks", "Loading tasks...")}</div>;
  }

  if (tasks.length === 0) {
    if (selectedTaskId) {
      return (
        <div className="mx-auto max-w-xl">
          <PickRecoveryPanel
            code="no_open_task"
            title={t("picking.recoveryNoTaskTitle", "No open pick task is available")}
            body={t("picking.recoveryNoTaskBody", "This task may have been completed elsewhere or the queue may be stale. Refresh tasks, then open the next released pick from the list.")}
            actions={["refresh_tasks", "open_picking_list"]}
            onAction={(action) => {
              if (action === "refresh_tasks") {
                void refreshTaskViews().then(returnToPickList);
                return;
              }
              returnToPickList();
            }}
            t={t}
          />
        </div>
      );
    }

    if (completedPick) {
      return (
        <div
          className="mx-auto max-w-xl rounded-[1.6rem] border border-[#9ed4b7] bg-[#edf8f1] px-6 py-8 text-center shadow-[0_18px_44px_rgba(19,33,44,0.06)]"
          data-testid="picking-success-next-step"
        >
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-2xl text-[#1b5f38]">✓</div>
          <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#2f7a4d]">
            {t("picking.pickingCompleteEyebrow", "Picking complete")}
          </p>
          <h2 className="mt-2 text-xl font-semibold text-[#13212c]">
            {completedPick.orderNumber
              ? t("picking.pickingCompleteTitleWithOrder", "{order} is ready for packing", { order: completedPick.orderNumber })
              : t("picking.pickingCompleteTitle", "This pick work is ready for packing")}
          </h2>
          <p className="mt-3 text-sm leading-6 text-[#4f6b5b]">
            {t("picking.pickingCompleteBody", "{count} pick tasks were confirmed. Continue in Shipping to verify packing and carrier handoff.", {
              count: completedPick.taskCount,
            })}
          </p>
          <p className="mt-3 rounded-xl border border-[#9ed4b7]/70 bg-white/70 px-3 py-2 text-sm font-semibold text-[#1b5f38]">
            {t("picking.pickingCompleteNextStep", "Next: open Shipping and pack this order.")}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <a
              href="/shipping"
              className="inline-flex min-h-[42px] items-center justify-center rounded-full bg-[#13212c] px-5 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#203240]"
            >
              {t("picking.goToShipping", "Go to Shipping")}
            </a>
            <a
              href="/picking"
              className="inline-flex min-h-[42px] items-center justify-center rounded-full border border-[#13212c]/10 bg-white px-5 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#f7f4ee]"
            >
              {t("picking.backToPickingQueue", "Back to picking queue")}
            </a>
          </div>
        </div>
      );
    }

    return (
      <div className="py-12 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-[#13212c]/10 bg-white text-xl text-[#13212c]">0</div>
        <h2 className="text-lg font-semibold text-gray-700">{t("picking.noPickTasks", "No pick tasks")}</h2>
        <p className="mt-1 text-sm text-gray-400">{t("picking.noPickTasksBody", "All orders are fulfilled or still waiting to be released into pick work.")}</p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => void refreshTaskViews()}
            className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-[#13212c] px-4 py-2 text-sm font-semibold text-white"
          >
            {isFetchingTasks ? t("picking.refreshingTasks", "Refreshing...") : t("picking.refreshTasks", "Refresh tasks")}
          </button>
          <a
            href="/picking"
            className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
          >
            {t("picking.openPickingList", "Open picking list")}
          </a>
        </div>
      </div>
    );
  }

  const selectedTaskIndex = selectedTaskId ? tasks.findIndex((candidate) => candidate.id === selectedTaskId) : -1;
  const currentIndex = selectedTaskIndex >= 0 ? selectedTaskIndex : 0;
  const task = selectedTaskIndex >= 0 ? tasks[selectedTaskIndex] : null;

  if (selectedTaskId && !task) {
    return (
      <div className="mx-auto max-w-xl">
        <PickRecoveryPanel
          code="stale_task"
          title={t("picking.recoveryStaleTaskTitle", "This pick task is no longer in the open queue")}
          body={t("picking.recoveryStaleTaskBody", "The task list changed while this pick was open. Refresh the tasks, then open the next released pick from the list.")}
          actions={["refresh_tasks", "back_to_list"]}
          onAction={(action) => {
            if (action === "refresh_tasks") {
              void refreshTaskViews().then(returnToPickList);
              return;
            }
            returnToPickList();
          }}
          t={t}
        />
      </div>
    );
  }

  if (!selectedTaskId || !task) {
    return (
      <div className="space-y-4">
        <section className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                {t("picking.taskQueueEyebrow", "Pick task queue")}
              </p>
              <h2 className="mt-1 text-lg font-semibold text-[#13212c]">
                {t("picking.taskQueueTitle", "Choose a released task before scanning")}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[#61717d]">
                {t(
                  "picking.taskQueueBody",
                  "Each row is one SKU and source location to pick. Open only the task you are ready to scan."
                )}
              </p>
            </div>
            <span className="w-fit rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
              {t("picking.openTasksChip", "{count} open tasks", { count: tasks.length })}
            </span>
          </div>

          <div className="mt-5 overflow-hidden rounded-[1.1rem] border border-[#13212c]/10 bg-[#fffdfa]">
            {tasks.map((pickTask, index) => {
              const order = orders.find((candidate) => candidate.id === pickTask.reference_id);
              const sourceLocation = pickTask.source_location_barcode || pickTask.source_location_id || "—";
              const skuLabel = pickTask.sku_code || pickTask.sku_barcode || pickTask.sku_id?.slice(0, 12) || "—";
              return (
                <button
                  key={pickTask.id}
                  type="button"
                  onClick={() => openTask(pickTask.id)}
                  className="grid min-h-[44px] w-full gap-3 border-b border-[#13212c]/8 px-4 py-4 text-left transition last:border-b-0 hover:bg-white md:grid-cols-[72px_minmax(0,1.25fr)_minmax(0,1fr)_96px_auto] md:items-center"
                >
                  <div className="flex items-start gap-3 md:contents">
                    <div className="inline-flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-[0.9rem] border border-[#13212c]/15 bg-white text-[#13212c]">
                      <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#7e8d98]">
                        {t("picking.taskShort", "Task")}
                      </span>
                      <span className="text-lg font-semibold leading-none">{index + 1}</span>
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-[#13212c]">
                        {order?.order_number || pickTask.reference_id?.slice(0, 12) || "—"}
                      </p>
                      <p className="mt-1 truncate text-sm text-[#61717d]">{skuLabel}</p>
                      <div className="mt-2 flex flex-wrap gap-2 md:hidden">
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-medium text-[#61717d]">
                          {t("picking.sourceLocation", "Source location")}: {sourceLocation}
                        </span>
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-medium text-[#61717d]">
                          {t("common.qty", "Qty")}: {pickTask.quantity}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="hidden min-w-0 md:block">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">
                      {t("picking.sourceLocation", "Source location")}
                    </p>
                    <p className="mt-1 truncate text-sm font-medium text-[#13212c]">{sourceLocation}</p>
                  </div>
                  <div className="hidden md:block">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">
                      {t("common.qty", "Qty")}
                    </p>
                    <p className="mt-1 text-sm font-semibold text-[#13212c]">{pickTask.quantity}</p>
                  </div>
                  <span className="inline-flex min-h-[44px] w-full items-center justify-center rounded-full bg-[#13212c] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#f4efe8] md:w-fit">
                    {t("picking.openPickTask", "Open pick task")}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      </div>
    );
  }

  const currentOrder = orders.find((order) => order.id === task.reference_id);

  const handleScan = (barcode: string) => {
    if (phase === "location") {
      if (!matchesExpected(barcode, [task.source_location_barcode, task.source_location_id])) {
        setRecovery({
          code: "wrong_location",
          title: t("picking.recoveryWrongLocationTitle", "Wrong location scanned"),
          body: t("picking.recoveryWrongLocationBody", "This scan does not match the source slot for the task. Stay at the current pick until the location code matches {expected}.", {
            expected: task.source_location_barcode || task.source_location_id || "—",
          }),
          actions: ["scan_again", "back_to_list"],
        });
        return;
      }
      setRecovery(null);
      setLocationConfirmed(true);
      setPhase("sku");
    } else if (phase === "sku") {
      if (!matchesExpected(barcode, [task.sku_barcode, task.sku_code, task.sku_id])) {
        setRecovery({
          code: "wrong_sku",
          title: t("picking.recoveryWrongSkuTitle", "Wrong SKU scanned"),
          body: t("picking.recoveryWrongSkuBody", "This product does not match the task. Put it back, scan the SKU shown for this pick, and only then confirm quantity. Expected {expected}.", {
            expected: task.sku_barcode || task.sku_code || task.sku_id || "—",
          }),
          actions: ["scan_again", "back_to_list"],
        });
        return;
      }
      setRecovery(null);
      setSkuConfirmed(true);
      setPickedQty(task.quantity);
      setPhase("confirm");
    }
  };

  const handleConfirmPick = () => {
    confirmMutation.mutate({
      task_id: task.id,
      quantity_picked: pickedQty,
    });
  };

  const scannerSuggestedCodes =
    phase === "location"
      ? [
          {
            label: t("picking.expectedLocationChip", "Expected location"),
            value: task.source_location_barcode || task.source_location_id || "",
          },
        ].filter((item) => item.value)
      : [
          {
            label: t("picking.expectedSkuChip", "Expected SKU"),
            value: task.sku_barcode || task.sku_code || task.sku_id || "",
          },
        ].filter((item) => item.value);

  const sourceLocation = task.source_location_barcode || task.source_location_id || "—";
  const skuLabel = task.sku_code || task.sku_barcode || task.sku_id?.slice(0, 12) || "—";
  const expectedScanCode =
    phase === "location"
      ? task.source_location_barcode || task.source_location_id || ""
      : task.sku_barcode || task.sku_code || task.sku_id || "";
  const pickingMobileSteps: MobileFlowStepItem[] = [
    {
      key: "location",
      number: "1",
      label: t("picking.locationStep", "Location"),
      status: locationConfirmed ? "done" : phase === "location" ? "active" : "pending",
    },
    {
      key: "sku",
      number: "2",
      label: t("picking.skuStep", "SKU"),
      status: skuConfirmed ? "done" : phase === "sku" ? "active" : "pending",
    },
    {
      key: "confirm",
      number: "3",
      label: t("picking.confirmStep", "Confirm"),
      status: phase === "confirm" ? "active" : "pending",
    },
  ];
  const pickingMobileTitle =
    phase === "location"
      ? t("picking.mobileStepTitleLocation", "Step 1 · Confirm the source location")
      : phase === "sku"
        ? t("picking.mobileStepTitleSku", "Step 2 · Confirm the SKU")
        : t("picking.mobileStepTitleConfirm", "Step 3 · Confirm picked quantity");
  const mobileStepObjectLabel =
    phase === "location"
      ? t("picking.expectedLocationShort", "Location")
      : phase === "sku"
        ? t("picking.skuLabel", "SKU")
        : t("picking.quantityPicked", "Quantity picked");
  const mobileStepObjectValue =
    phase === "location" ? sourceLocation : phase === "sku" ? skuLabel : String(pickedQty || task.quantity);
  const scanSuccessMessage =
    phase === "sku" && locationConfirmed
      ? t("picking.locationConfirmedFeedback", "Location confirmed. Scan the SKU next.")
      : phase === "confirm" && skuConfirmed
        ? t("picking.skuConfirmedFeedback", "SKU confirmed. Confirm the picked quantity.")
        : null;
  const currentScanCodeMissing = (phase === "location" || phase === "sku") && !expectedScanCode;
  const activeRecovery = recovery || (currentScanCodeMissing
    ? {
        code: "missing_scan_code",
        title: t("picking.scanCodeMissingTitle", "This task is missing the expected scan code."),
        body: t("picking.scanCodeMissingBody", "The task cannot be safely confirmed by scan because the expected code is blank. Go back to the pick list and refresh tasks before touching stock."),
        actions: ["back_to_list", "refresh_tasks"] as PickRecoveryAction[],
      }
    : null);
  const pickingMobilePath = activeRecovery ? "exception" : "scan";

  const runRecoveryAction = (action: PickRecoveryAction) => {
    switch (action) {
      case "scan_again":
        setRecovery(null);
        if (phase === "confirm") {
          resetPhase();
        }
        break;
      case "adjust_quantity":
        setRecovery(null);
        setPhase("confirm");
        break;
      case "refresh_tasks":
        setRecovery(null);
        void refreshTaskViews();
        break;
      case "open_picking_list":
      case "back_to_list":
        returnToPickList();
        break;
    }
  };

  return (
    <div className="space-y-3 md:space-y-4">
      <section
        className="max-w-full overflow-hidden rounded-2xl border border-[#13212c]/8 bg-white p-3 shadow md:hidden"
        data-testid="picking-mobile-active-task"
        data-picking-path={pickingMobilePath}
      >
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={returnToPickList}
            className="inline-flex min-h-[44px] shrink-0 items-center gap-1 rounded-full border border-[#13212c]/10 bg-[#fbf8f2] px-3 py-2 text-xs font-semibold text-[#13212c]"
          >
            <ArrowLeft size={14} />
            {t("picking.backToPickListShort", "Back")}
          </button>
          <p className="min-w-0 truncate text-xs font-semibold text-[#51606b]">
            {currentOrder?.order_number || task.reference_id || t("picking.pickTaskFallback", "Pick task")}
          </p>
        </div>

        <div className="mt-3 grid min-w-0 gap-1.5" style={{ gridTemplateColumns: `repeat(${pickingMobileSteps.length}, minmax(0, 1fr))` }}>
          {pickingMobileSteps.map((step) => (
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
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("picking.currentTaskEyebrow", "Current pick task")}</p>
          <p className="mt-1 text-base font-semibold leading-snug text-[#13212c]">{pickingMobileTitle}</p>
        </div>

        <div
          className="mt-3 grid grid-cols-3 gap-2 rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] p-2"
          data-testid="picking-mobile-current-object"
        >
          <PickMiniStat
            label={t("picking.mobileObjectOrder", "Order")}
            value={currentOrder?.order_number || task.reference_id || "—"}
          />
          <PickMiniStat label={t("picking.mobileObjectLocation", "Location")} value={sourceLocation} />
          <PickMiniStat label={t("picking.mobileObjectSku", "SKU")} value={skuLabel} />
        </div>
      </section>

      <section className="hidden rounded-2xl bg-white p-5 shadow md:block">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <button
              type="button"
              onClick={returnToPickList}
              className="mb-4 inline-flex items-center rounded-full border border-[#13212c]/12 bg-[#13212c] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#243545]"
            >
              {t("picking.backToPickList", "Back to pick list")}
            </button>
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
              {t("picking.currentTaskEyebrow", "Current pick task")}
            </p>
            <h2 className="mt-2 text-lg font-semibold text-[#13212c]">
              {t("picking.currentTaskTitle", "Pick one task from source to cart")}
            </h2>
          </div>
          <span className="w-fit rounded-full border border-[#13212c]/10 bg-[#f8f4ec] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
            {t("picking.taskNumber", "Task {number}", { number: currentIndex + 1 })}
          </span>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
            {currentOrder
              ? t("picking.linkedOrder", "Outbound order: {value}", { value: currentOrder.order_number })
              : t("picking.linkedOrder", "Outbound order: {value}", { value: task.reference_id || "—" })}
          </span>
          <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
            {t("picking.sourceLocation", "Source location")}: {sourceLocation}
          </span>
          <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
            {t("picking.skuLabel", "SKU:")} {skuLabel}
          </span>
          <span className="rounded-full border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-1.5 text-xs font-medium text-[#51606b]">
            {t("picking.qtyLabel", "Qty:")} {task.quantity}
          </span>
        </div>
      </section>

      <section className="hidden rounded-2xl bg-white p-4 shadow md:block">
        <div className="grid gap-3 md:grid-cols-3">
          {[
            { label: t("picking.locationStep", "Location"), done: locationConfirmed, active: phase === "location" },
            { label: t("picking.skuStep", "SKU"), done: skuConfirmed, active: phase === "sku" },
            { label: t("picking.confirmStep", "Confirm"), done: false, active: phase === "confirm" },
          ].map((step, index) => (
            <PickStep
              key={step.label}
              index={index + 1}
              label={step.label}
              done={step.done}
              active={step.active}
            />
          ))}
        </div>
      </section>

      <section className="rounded-2xl bg-white p-3 shadow sm:p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
              {t("picking.scanWorkEyebrow", "Scan and confirm")}
            </p>
            <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
              {phase === "location"
                ? t("picking.scanLocationWorkTitle", "Confirm the source location")
                : phase === "sku"
                ? t("picking.scanSkuWorkTitle", "Confirm the SKU")
                : t("picking.confirmWorkTitle", "Confirm picked quantity")}
            </h3>
            <p className="mt-2 hidden text-sm leading-6 text-[#61717d] md:block">
              {phase === "location"
                ? t("picking.scanLocationInstruction", "Scan the location barcode to confirm you are at the correct slot.")
                : phase === "sku"
                ? t("picking.scanSkuInstruction", "Scan the SKU barcode to confirm the correct product.")
                : t("picking.confirmWorkBody", "Review the quantity picked for this task before sending it to shipping.")}
            </p>
          </div>
          <div className="hidden grid-cols-2 gap-2 text-sm sm:grid lg:min-w-[18rem]">
            <PickMiniStat label={t("picking.expectedLocationShort", "Location")} value={sourceLocation} />
            <PickMiniStat label={t("common.qty", "Qty")} value={String(task.quantity)} />
          </div>
        </div>

        <div className="mt-3 grid gap-2 text-sm md:hidden">
          <div className="grid grid-cols-[minmax(0,1fr)_5.5rem] gap-2">
            <PickMiniStat label={mobileStepObjectLabel} value={mobileStepObjectValue} />
            <PickMiniStat label={t("common.qty", "Qty")} value={String(task.quantity)} />
          </div>
          <details className="rounded-xl border border-[#13212c]/8 bg-[#fffdfa] px-3 py-2">
            <summary className="cursor-pointer list-none text-xs font-semibold text-[#51606b]">
              {t("picking.mobileTaskContext", "Task context")}
            </summary>
            <div className="mt-2 grid gap-2">
              <PickMiniStat label={t("picking.expectedLocationShort", "Location")} value={sourceLocation} />
              <PickMiniStat label={t("picking.skuLabel", "SKU")} value={skuLabel} />
            </div>
          </details>
        </div>

        {activeRecovery ? (
          <div className="mt-4">
            <PickRecoveryPanel
              code={activeRecovery.code}
              title={activeRecovery.title}
              body={activeRecovery.body}
              actions={activeRecovery.actions}
              onAction={runRecoveryAction}
              t={t}
            />
          </div>
        ) : null}

        {!activeRecovery && (phase === "location" || phase === "sku") && !currentScanCodeMissing && (
          <div className="mt-5 space-y-3">
            <BarcodeScanner
              key={`${task.id}-${phase}`}
              onScan={handleScan}
              context="picking"
              placeholder={
                phase === "location"
                  ? t("picking.scanLocationPlaceholder", "Scan location barcode...")
                  : t("picking.scanSkuPlaceholder", "Scan SKU barcode...")
              }
              suggestedCodes={scannerSuggestedCodes}
              manualHintTitle={t("picking.scanManualHintTitle", "Expected code")}
              manualHintBody={
                phase === "location"
                  ? t("picking.scanLocationManualHint", "Scan or type the location code shown on this task before touching the stock.")
                  : t("picking.scanSkuManualHint", "Scan or type the SKU code shown on this task before confirming quantity.")
              }
              deviceHint={t("picking.scanDeviceHint", "Scanner guns can type here directly. Press Enter or Use code to submit, or use Scan for the phone camera.")}
            />
            {scanSuccessMessage ? (
              <div className="rounded-xl border border-[#9ed4b7] bg-[#edf8f1] px-4 py-3 text-sm font-medium text-[#1b5f38]">
                {scanSuccessMessage}
              </div>
            ) : null}
            <div className="hidden flex-col gap-2 rounded-xl border border-[#13212c]/10 bg-[#fffdfa] p-3 md:flex md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">
                  {phase === "location"
                    ? t("picking.expectedLocationChip", "Expected location")
                    : t("picking.expectedSkuChip", "Expected SKU")}
                </p>
                <p className="mt-1 break-all font-mono text-sm font-semibold text-[#13212c]">
                  {expectedScanCode || "—"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => expectedScanCode && handleScan(expectedScanCode)}
                disabled={!expectedScanCode}
                className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-[#13212c] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#243545] disabled:cursor-not-allowed disabled:bg-[#cbd5e1] disabled:text-[#51606b]"
              >
                {phase === "location"
                  ? t("picking.confirmExpectedLocation", "Confirm source location")
                  : t("picking.confirmExpectedSku", "Confirm SKU")}
              </button>
            </div>
          </div>
        )}

        {!activeRecovery && phase === "confirm" && (
          <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              {scanSuccessMessage ? (
                <div className="mb-3 rounded-xl border border-[#9ed4b7] bg-[#edf8f1] px-4 py-3 text-sm font-medium text-[#1b5f38]">
                  {scanSuccessMessage}
                </div>
              ) : null}
              <label className="mb-1.5 block text-sm font-medium text-[#334351]">
                {t("picking.quantityPicked", "Quantity picked")}
              </label>
              <input
                type="number"
                value={pickedQty}
                onChange={(e) => setPickedQty(Number(e.target.value))}
                min={0}
                max={task.quantity}
                className="w-full rounded-xl border border-[#d7d0c4] bg-white px-4 py-3 text-lg font-semibold text-[#13212c] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={handleConfirmPick}
                disabled={confirmMutation.isPending || pickedQty <= 0}
                className="min-h-[44px] w-full rounded-xl bg-[#13212c] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#243545] disabled:cursor-not-allowed disabled:bg-[#cbd5e1] disabled:text-[#51606b] sm:w-auto"
              >
                {confirmMutation.isPending
                  ? t("picking.confirming", "Confirming...")
                  : t("picking.confirmPick", "Confirm pick ({qty})", { qty: pickedQty })}
              </button>
              <button
                type="button"
                onClick={resetPhase}
                className="min-h-[44px] w-full rounded-xl border border-[#13212c]/10 bg-white px-5 py-2 text-sm font-semibold text-[#13212c] transition hover:bg-[#f7f4ee] sm:w-auto"
              >
                {t("picking.scanAgain", "Rescan task")}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function PickStep({ index, label, done, active }: { index: number; label: string; done: boolean; active: boolean }) {
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
        <div>
          <p className={`text-sm font-semibold ${active || done ? "text-[#13212c]" : "text-[#61717d]"}`}>{label}</p>
        </div>
      </div>
    </div>
  );
}

function PickMiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#e3ddd2] bg-[#f8f4ec] px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-[#13212c]">{value}</p>
    </div>
  );
}

function PickRecoveryPanel({
  code,
  title,
  body,
  actions,
  onAction,
  t,
}: {
  code: string;
  title: string;
  body: string;
  actions: PickRecoveryAction[];
  onAction: (action: PickRecoveryAction) => void;
  t: (key: string, fallback: string, vars?: Record<string, string | number>) => string;
}) {
  const visibleActions: PickRecoveryAction[] =
    actions.length <= 2
      ? actions
      : Array.from(new Set([actions[0], actions.includes("back_to_list") ? "back_to_list" : actions[1]]));
  const safeExit =
    visibleActions.find((action) => action === "back_to_list" || action === "open_picking_list" || action === "refresh_tasks") ||
    visibleActions[visibleActions.length - 1];
  const actionLabel = (action: PickRecoveryAction) => {
    switch (action) {
      case "scan_again":
        return t("picking.recoveryActionScanAgain", "Rescan");
      case "back_to_list":
        return t("picking.recoveryActionBackToList", "Back to pick list");
      case "refresh_tasks":
        return t("picking.recoveryActionRefreshTasks", "Refresh tasks");
      case "adjust_quantity":
        return t("picking.recoveryActionAdjustQuantity", "Adjust quantity");
      case "open_picking_list":
        return t("picking.recoveryActionOpenPickingList", "Open picking list");
    }
  };

  return (
    <WorkflowRecoveryPanel
      workflow="picking"
      code={code}
      action={visibleActions[0]}
      safeExit={safeExit}
      title={title}
      body={body}
      recommendedActionLabel={actionLabel(visibleActions[0])}
      returnEntryLabel={actionLabel(safeExit)}
      labels={{
        whatHappened: t("recovery.whatHappened", "What happened"),
        whyBlocked: t("recovery.whyBlocked", "Why this cannot continue"),
        recommendedAction: t("recovery.recommendedAction", "Recommended action"),
        returnEntry: t("recovery.returnEntry", "Return entry"),
      }}
      actions={visibleActions.map((action, index) => (
          <button
            key={`${action}-${index}`}
            type="button"
            onClick={() => onAction(action)}
            data-testid={`picking-recovery-action-${action}`}
            data-recovery-action={action}
            className={
              index === 0
                ? "min-h-[44px] rounded-xl border border-[#13212c] bg-[#13212c] px-3 py-2 text-sm font-semibold text-white sm:min-h-0 sm:rounded-full sm:py-1.5 sm:text-xs"
                : "min-h-[44px] rounded-xl border border-[#13212c]/10 bg-white px-3 py-2 text-sm font-semibold text-[#13212c] sm:min-h-0 sm:rounded-full sm:py-1.5 sm:text-xs"
            }
          >
            {actionLabel(action)}
          </button>
        ))}
    />
  );
}
