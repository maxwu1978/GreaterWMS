import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, ArrowRight, Check, GripVertical, X } from "lucide-react";
import { Link } from "react-router-dom";
import { queryKeys } from "../../shared/api/queryKeys";
import { fetchInboundOrders } from "../../shared/api/inboundOrders";
import { fetchInventoryRaw } from "../../shared/api/inventory";
import { fetchSkuDirectory } from "../../shared/api/directories";
import { fetchPlannerRules, fetchWarehouseLocations, fetchWarehouses } from "../../shared/api/planner";
import { fetchTasks } from "../../shared/api/tasks";
import { suggestPutawayLocation } from "../../shared/api/putaway";
import { requestWithOutbox } from "../../shared/offline/mutations";
import { isOfflineMutationQueuedError } from "../../shared/offline/outbox";
import {
  fetchPutawayWorkbenchSummary,
  workbenchSummaryKeys,
} from "../../shared/api/workbenchSummaries";
import MetricTile from "../../shared/components/MetricTile";
import MobileFlowGuide, { type MobileFlowStepItem } from "../../shared/components/MobileFlowGuide";
import Pill from "../../shared/components/Pill";
import StatusBadge from "../../shared/components/StatusBadge";
import TaskCard from "../../shared/components/TaskCard";
import WorkflowRecoveryPanel from "../../shared/components/WorkflowRecoveryPanel";
import BarcodeScanner from "../../scanner/BarcodeScanner";
import { useI18n } from "../../shared/i18n";
import {
  describeLocationBarcode,
  getApiErrorCode,
  getApiErrorMessage,
  getExecutionModeLabel,
  getExecutionModeTone,
  getExecutionReasonLabel,
  getHandlingUnitStatusLabel,
  getInboundOrderTag,
  getSlotTone,
  getSuggestionReasonLabel,
  getSuggestionStrength,
  getTaskAgeLabel,
  getTaskCreatedAt,
  getTaskExternalCodeSummary,
  getTaskOrderKey,
  getTaskSearchText,
  keepTaskIdsInOneOrder,
  occupancyTone,
  parseStorageBarcode,
  shortId,
  toItems,
} from "./putawayWorkUtils";

const LIVE_REFRESH_MS = 5000;

type PutawayViewMode = "handling_unit" | "inbound_order" | "sku";
type PutawayExecutionFilter = "all" | "human" | "agv" | "hybrid";
type PutawayWorkspaceTab = "tasks" | "work";
type PutawayFocusContext = {
  source?: string | null;
  orderId?: string | null;
  orderNumber?: string | null;
  referenceNumber?: string | null;
  handlingUnitCode?: string | null;
  taskId?: string | null;
};
type SplitDestinationDraft = {
  locationId: string;
  quantity: string;
  zone?: string;
  aisle?: string;
  rack?: string;
  level?: string;
};
type PutawayRecoveryAction =
  | "choose_slot"
  | "back_to_list"
  | "refresh_task"
  | "open_receiving"
  | "open_inventory"
  | "fix_quantity";
type PutawayRecoveryState = {
  code: string;
  title: string;
  body: string;
  actions: PutawayRecoveryAction[];
};
type PutawayRecoveryKind =
  | "source_staging_missing"
  | "source_stock_mismatch"
  | "allocation_invalid"
  | "destination_blocked"
  | "same_sku_policy_blocked"
  | "lot_expiry_mismatch"
  | "inbound_not_released"
  | "task_not_ready";

const putawayRecoveryCodeKinds: Record<string, PutawayRecoveryKind> = {
  putaway_source_staging_missing: "source_staging_missing",
  putaway_source_staging_not_found: "source_staging_missing",
  putaway_source_stock_split: "source_stock_mismatch",
  putaway_source_inventory_short: "source_stock_mismatch",
  putaway_allocation_missing_destination: "allocation_invalid",
  putaway_allocation_invalid_quantity: "allocation_invalid",
  putaway_allocation_quantity_mismatch: "allocation_invalid",
  putaway_destination_not_found: "destination_blocked",
  putaway_destination_not_storage_slot: "destination_blocked",
  putaway_destination_blocked: "destination_blocked",
  putaway_destination_different_sku: "destination_blocked",
  putaway_destination_same_sku_disabled: "same_sku_policy_blocked",
  putaway_destination_lot_expiry_mismatch: "lot_expiry_mismatch",
  putaway_inbound_not_released: "inbound_not_released",
  putaway_task_not_available: "task_not_ready",
  putaway_task_not_pending: "task_not_ready",
  putaway_task_invalid_quantity: "task_not_ready",
};

function classifyPutawayRecoveryCode(code: string | null): PutawayRecoveryKind | null {
  if (!code) return null;
  return putawayRecoveryCodeKinds[code] || null;
}

function PutawayRecoveryPanel({
  code,
  title,
  body,
  message,
  actions,
  onAction,
  receivingPath,
  t,
}: PutawayRecoveryState & {
  message: string;
  onAction: (action: PutawayRecoveryAction) => void;
  receivingPath: string;
  t: (key: string, fallback: string, vars?: Record<string, string | number>) => string;
}) {
  const actionLabel = (action: PutawayRecoveryAction) => {
    switch (action) {
      case "choose_slot":
        return t("putaway.recoveryActionChooseSlot", "Choose another slot");
      case "back_to_list":
        return t("putaway.recoveryActionBackToList", "Back to putaway list");
      case "refresh_task":
        return t("putaway.recoveryActionRefreshTask", "Refresh task");
      case "open_receiving":
        return t("putaway.recoveryActionOpenReceiving", "Open receiving");
      case "open_inventory":
        return t("putaway.recoveryActionOpenInventory", "Open inventory");
      case "fix_quantity":
        return t("putaway.recoveryActionFixQuantity", "Fix quantity plan");
    }
  };

  const actionClass = (index: number) =>
    index === 0
      ? "min-h-[44px] rounded-xl border border-[#13212c] bg-[#13212c] px-3 py-2 text-sm font-semibold text-white sm:min-h-0 sm:rounded-full sm:py-1.5 sm:text-xs"
      : "min-h-[44px] rounded-xl border border-[#13212c]/10 bg-white px-3 py-2 text-sm font-semibold text-[#13212c] sm:min-h-0 sm:rounded-full sm:py-1.5 sm:text-xs";
  const visibleActions: PutawayRecoveryAction[] =
    actions.length <= 2
      ? actions
      : Array.from(new Set([actions[0], actions.includes("back_to_list") ? "back_to_list" : actions[1]]));
  const safeExit =
    visibleActions.find((action) => action === "back_to_list" || action === "open_receiving" || action === "open_inventory" || action === "refresh_task") ||
    visibleActions[visibleActions.length - 1];

  return (
    <WorkflowRecoveryPanel
      workflow="putaway"
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
      bodyExtra={
        <p className="mt-2 rounded-xl border border-[#d6e2ef] bg-white px-3 py-2 text-xs leading-5 text-[#61717d]">
          {t("putaway.recoverySystemReason", "System reason")}: {message}
        </p>
      }
      actions={visibleActions.map((action, index) =>
          action === "open_receiving" || action === "open_inventory" ? (
            <Link
              key={action}
              to={action === "open_receiving" ? receivingPath : "/inventory"}
              className={actionClass(index)}
              data-testid={`putaway-recovery-action-${action}`}
              data-recovery-action={action}
            >
              {actionLabel(action)}
            </Link>
          ) : (
            <button
              key={action}
              type="button"
              onClick={() => onAction(action)}
              className={actionClass(index)}
              data-testid={`putaway-recovery-action-${action}`}
              data-recovery-action={action}
            >
              {actionLabel(action)}
            </button>
          )
        )}
    />
  );
}

export default function PutawayPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<PutawayViewMode>("handling_unit");
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<PutawayWorkspaceTab>("tasks");
  const [taskSearch, setTaskSearch] = useState("");
  const [executionFilter, setExecutionFilter] = useState<PutawayExecutionFilter>("all");
  const [focusContext, setFocusContext] = useState<PutawayFocusContext | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [selectedDestinationId, setSelectedDestinationId] = useState("");
  const [mobileDestinationConfirmed, setMobileDestinationConfirmed] = useState(false);
  const [mobileDestinationScanError, setMobileDestinationScanError] = useState<string | null>(null);
  const [otherDestinationCode, setOtherDestinationCode] = useState("");
  const [primaryDestinationQuantity, setPrimaryDestinationQuantity] = useState("");
  const [splitDestinations, setSplitDestinations] = useState<SplitDestinationDraft[]>([]);
  const [selectedZoneKey, setSelectedZoneKey] = useState("");
  const [selectedAisleKey, setSelectedAisleKey] = useState("");
  const [selectedRackKey, setSelectedRackKey] = useState("");
  const [selectedLevelKey, setSelectedLevelKey] = useState("");
  const [batchResult, setBatchResult] = useState<{
    successCount: number;
    queuedCount: number;
    failedCount: number;
    failures: string[];
    failedTaskIds: string[];
  } | null>(null);
  const [batchAssignments, setBatchAssignments] = useState<Record<string, string>>({});
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [planReviewNotice, setPlanReviewNotice] = useState<string | null>(null);
  const [highlightFinalReview, setHighlightFinalReview] = useState(false);
  const [lastCompletedPutaway, setLastCompletedPutaway] = useState<{
    handlingUnitCode: string | null;
    destinationCount: number;
  } | null>(null);
  const successNoticeRef = useRef<HTMLDivElement | null>(null);
  const finalReviewRef = useRef<HTMLDivElement | null>(null);
  const putawayTasksQueryKey = queryKeys.tasks.putaway({ status: "pending", task_type: "putaway" });
  const offlineQueuedText = () =>
    t("offline.mutationQueued", "Saved offline. It will sync automatically when the connection is back.");

  const { data: tasks = [], isLoading: tasksLoading } = useQuery({
    queryKey: putawayTasksQueryKey,
    queryFn: () =>
      fetchTasks({ status: "pending", task_type: "putaway", limit: 500 }).then((data) => toItems<any>(data)),
    refetchInterval: LIVE_REFRESH_MS,
    refetchOnWindowFocus: true,
  });
  const { data: putawayWorkbenchSummary } = useQuery({
    queryKey: workbenchSummaryKeys.putaway,
    queryFn: fetchPutawayWorkbenchSummary,
    refetchInterval: LIVE_REFRESH_MS,
    refetchOnWindowFocus: true,
  });

  const { data: warehouses = [] } = useQuery({
    queryKey: queryKeys.putaway.warehouses(),
    queryFn: () =>
      fetchWarehouses({ offset: 0, limit: 200 })
        .then((data) => toItems<any>(data))
        .catch(() => []),
  });

  const warehouseIds = useMemo<string[]>(
    () => Array.from(new Set(tasks.map((task: any) => task.warehouse_id).filter(Boolean))) as string[],
    [tasks]
  );

  const { data: locations = [] } = useQuery({
    queryKey: queryKeys.putaway.locations(warehouseIds.join(",")),
    enabled: warehouseIds.length > 0,
    queryFn: async () => {
      const results = await Promise.all(
        warehouseIds.map(async (warehouseId: string) => {
          const rows = await fetchWarehouseLocations(warehouseId)
            .then((data) => toItems<any>(data))
            .catch(() => []);
          return rows.map((location: any) => ({ ...location, warehouse_id: warehouseId }));
        })
      );
      return results.flat();
    },
  });

  const { data: inboundOrders = [] } = useQuery({
    queryKey: queryKeys.putaway.inboundOrders(),
    queryFn: () =>
      fetchInboundOrders()
        .then((data) => toItems<any>(data))
        .catch(() => []),
  });

  const { data: skus = [] } = useQuery({
    queryKey: queryKeys.putaway.skus(),
    queryFn: () =>
      fetchSkuDirectory({ offset: 0, limit: 500 })
        .then((data) => toItems<any>(data))
        .catch(() => []),
  });

  const warehouseMap = useMemo(
    () =>
      new Map(
        warehouses.map((warehouse: any) => [
          warehouse.id,
          warehouse.name ? `${warehouse.code || shortId(warehouse.id)} · ${warehouse.name}` : warehouse.code || shortId(warehouse.id),
        ])
      ),
    [warehouses]
  );

  const locationMap = useMemo(
    () =>
      new Map(
        locations.map((location: any) => [
          location.id,
          {
            barcode: location.barcode || shortId(location.id),
            type: location.location_type,
            warehouse_id: location.warehouse_id,
          },
        ])
      ),
    [locations]
  );

  const inboundMap = useMemo(
    () =>
      new Map(
        inboundOrders.map((order: any) => [
          order.id,
          {
            order_number: order.order_number,
            reference_number: order.reference_number,
          },
        ])
      ),
    [inboundOrders]
  );

  const skuMap = useMemo(
    () =>
      new Map(
        skus.map((sku: any) => [
          sku.id,
          {
            code: sku.sku_code || shortId(sku.id),
            name: sku.name || sku.sku_code || shortId(sku.id),
          },
        ])
      ),
    [skus]
  );

  const enrichedTasks = useMemo(
    () =>
      tasks.map((task: any) => {
        const locationMeta = locationMap.get(task.source_location_id);
        const inboundMeta = task.reference_id ? inboundMap.get(task.reference_id) : null;
        const skuMeta = skuMap.get(task.sku_id);
        return {
          ...task,
          source_barcode: locationMeta?.barcode || shortId(task.source_location_id),
          warehouse_label: warehouseMap.get(task.warehouse_id) || shortId(task.warehouse_id),
          inbound_order_number: inboundMeta?.order_number || shortId(task.reference_id),
          reference_number: inboundMeta?.reference_number || task.reference_number || null,
          sku_label: skuMeta ? `${skuMeta.code} · ${skuMeta.name}` : shortId(task.sku_id),
        };
      }),
    [inboundMap, locationMap, skuMap, tasks, warehouseMap]
  );
  const enrichedTaskMap = useMemo(() => new Map(enrichedTasks.map((task: any) => [task.id, task])), [enrichedTasks]);
  const taskDisplayNumberMap = useMemo(
    () =>
      new Map(
        [...enrichedTasks]
          .sort((a: any, b: any) => {
            const createdDiff = getTaskCreatedAt(a) - getTaskCreatedAt(b);
            if (createdDiff !== 0) return createdDiff;
            return String(a.id || "").localeCompare(String(b.id || ""));
          })
          .map((task: any, index) => [task.id, index + 1])
      ),
    [enrichedTasks]
  );
  const taskNumberLabel = (task: any) =>
    t("putaway.taskNumber", "Task {number}", {
      number: taskDisplayNumberMap.get(task.id) || "—",
    });
  const taskGroupNumberMeta = (items: any[]) => {
    const numbers = items
      .map((task) => taskDisplayNumberMap.get(task.id))
      .filter((value): value is number => typeof value === "number")
      .sort((a, b) => a - b);
    if (!numbers.length) {
      return {
        ariaLabel: t("putaway.taskNumber", "Task {number}", { number: "—" }),
        eyebrow: t("putaway.taskNumberEyebrow", "Task"),
        value: "—",
      };
    }
    if (numbers.length === 1) {
      return {
        ariaLabel: t("putaway.taskNumber", "Task {number}", { number: numbers[0] }),
        eyebrow: t("putaway.taskNumberEyebrow", "Task"),
        value: String(numbers[0]),
      };
    }
    return {
      ariaLabel: t("putaway.taskRange", "Tasks {start}-{end}", {
        start: numbers[0],
        end: numbers[numbers.length - 1],
      }),
      eyebrow: t("putaway.taskRangeEyebrow", "Tasks"),
      value: `${numbers[0]}-${numbers[numbers.length - 1]}`,
    };
  };

  const normalizedTaskSearch = taskSearch.trim().toLowerCase();

  const searchScopedTasks = useMemo(
    () =>
      enrichedTasks.filter((task: any) => {
        if (!normalizedTaskSearch) return true;
        return getTaskSearchText(task).includes(normalizedTaskSearch);
      }),
    [enrichedTasks, normalizedTaskSearch]
  );

  const filteredTasks = useMemo(
    () =>
      searchScopedTasks.filter((task: any) => {
        const executionMatch = executionFilter === "all" || task.execution_mode === executionFilter;
        return executionMatch;
      }).sort((a: any, b: any) => {
        const createdDiff = getTaskCreatedAt(a) - getTaskCreatedAt(b);
        if (createdDiff !== 0) return createdDiff;
        return String(a.id || "").localeCompare(String(b.id || ""));
      }),
    [executionFilter, searchScopedTasks]
  );
  const visibleOrderCount = useMemo(
    () => new Set(filteredTasks.map((task: any) => getTaskOrderKey(task))).size,
    [filteredTasks]
  );

  const activeTask = useMemo(() => {
    if (filteredTasks.length === 0) return null;
    return filteredTasks.find((task: any) => task.id === selectedTaskId) || filteredTasks[0] || null;
  }, [filteredTasks, selectedTaskId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw =
      window.sessionStorage.getItem("putaway.focusContext") ||
      window.sessionStorage.getItem("putaway.focusInboundOrder");
    if (!raw) return;
    window.sessionStorage.removeItem("putaway.focusContext");
    window.sessionStorage.removeItem("putaway.focusInboundOrder");
    try {
      const parsed = JSON.parse(raw);
      if (parsed?.orderId || parsed?.orderNumber || parsed?.referenceNumber || parsed?.handlingUnitCode || parsed?.taskId) {
        setFocusContext({
          source: parsed.source ? String(parsed.source) : null,
          orderId: parsed.orderId ? String(parsed.orderId) : null,
          orderNumber: parsed.orderNumber ? String(parsed.orderNumber) : null,
          referenceNumber: parsed.referenceNumber ? String(parsed.referenceNumber) : null,
          handlingUnitCode: parsed.handlingUnitCode ? String(parsed.handlingUnitCode) : null,
          taskId: parsed.taskId ? String(parsed.taskId) : null,
        });
      }
    } catch {
      window.sessionStorage.removeItem("putaway.focusContext");
      window.sessionStorage.removeItem("putaway.focusInboundOrder");
    }
  }, []);

  useEffect(() => {
    if (!focusContext || enrichedTasks.length === 0) return;
    const focusSearch =
      focusContext.handlingUnitCode || focusContext.orderNumber || focusContext.referenceNumber || "";
    const focusViewMode = focusContext.taskId || focusContext.handlingUnitCode ? "handling_unit" : "inbound_order";
    const exactMatches = enrichedTasks.filter(
      (task: any) => {
        if (focusContext.taskId) return task.id === focusContext.taskId;
        if (focusContext.handlingUnitCode) return task.handling_unit_code === focusContext.handlingUnitCode;
        return (
          (focusContext.orderId && task.reference_id === focusContext.orderId) ||
          (focusContext.orderNumber && task.inbound_order_number === focusContext.orderNumber) ||
          (focusContext.referenceNumber && task.reference_number === focusContext.referenceNumber)
        );
      }
    );
    setViewMode(focusViewMode);
    setExecutionFilter("all");
    setTaskSearch(focusSearch);
    if (exactMatches.length === 0) {
      setSelectedTaskIds([]);
      setSelectedTaskId(null);
      clearActiveDestinationPlan();
      return;
    }
    setSelectedTaskIds(exactMatches.map((task: any) => task.id));
    setSelectedTaskId(exactMatches[0]?.id || null);
    clearActiveDestinationPlan();
  }, [enrichedTasks, focusContext]);

  const { data: inventoryContext = [] } = useQuery({
    queryKey: queryKeys.putaway.inventoryContext(activeTask?.warehouse_id),
    enabled: Boolean(activeTask?.warehouse_id),
    queryFn: () =>
      fetchInventoryRaw({
        warehouse_id: activeTask?.warehouse_id,
        offset: 0,
        limit: 500,
      })
        .then((data) => toItems<any>(data))
        .catch(() => []),
    refetchInterval: activeTask?.warehouse_id ? LIVE_REFRESH_MS : false,
    refetchOnWindowFocus: true,
  });

  const { data: plannerRules } = useQuery({
    queryKey: queryKeys.putaway.plannerRules(activeTask?.warehouse_id),
    enabled: Boolean(activeTask?.warehouse_id),
    queryFn: () => fetchPlannerRules(activeTask?.warehouse_id).then((data) => data).catch(() => ({})),
    staleTime: 60_000,
  });

  const placementPolicy = useMemo(
    () => ({
      allowSameSkuConsolidation: plannerRules?.allow_same_sku_consolidation ?? true,
      differentSkuSlotPolicy: plannerRules?.different_sku_slot_policy || "block",
      lotExpiryMismatchPolicy: plannerRules?.lot_expiry_mismatch_policy || "warn",
    }),
    [plannerRules]
  );

  const destinationCandidates = useMemo(
    () =>
      locations.filter(
        (location: any) =>
          activeTask &&
          location.warehouse_id === activeTask.warehouse_id &&
          location.location_type === "storage"
      ),
    [activeTask, locations]
  );

  const { data: suggestions = [] } = useQuery({
    queryKey: queryKeys.putaway.suggestions(activeTask?.id),
    enabled: Boolean(activeTask),
    queryFn: async () => {
      const data = await suggestPutawayLocation({
        warehouse_id: activeTask.warehouse_id,
        sku_id: activeTask.sku_id,
        quantity: activeTask.quantity,
        source_location_id: activeTask.source_location_id,
      });
      return toItems<any>(data);
    },
    refetchInterval: activeTask ? LIVE_REFRESH_MS : false,
    refetchOnWindowFocus: true,
  });

  const enrichedSuggestions = useMemo(
    () =>
      suggestions.map((suggestion: any, index: number) => ({
        ...suggestion,
        rank: index + 1,
        reasonLabel: getSuggestionReasonLabel(suggestion.reason, t),
      })),
    [suggestions, t]
  );

  const suggestionMap = useMemo(
    () =>
      new Map(
        enrichedSuggestions.map((suggestion: any) => [
          suggestion.location_id,
          suggestion,
        ]),
      ),
    [enrichedSuggestions]
  );

  const inventoryContextSummary = useMemo(() => {
    const zoneMap = new Map<string, any>();
    const aisleMap = new Map<string, any>();
    const rackMap = new Map<string, any>();
    const slotMap = new Map<string, any>();

    const ensureSummary = (map: Map<string, any>, key: string) => {
      if (!map.has(key)) {
        map.set(key, {
          units: 0,
          occupiedLocations: new Set<string>(),
          skuIds: new Set<string>(),
          skuCounts: new Map<string, { label: string; units: number }>(),
          sameSkuLotKeys: new Set<string>(),
          sameSkuUnits: 0,
        });
      }
      return map.get(key);
    };

    for (const item of inventoryContext) {
      const locationMeta = locationMap.get(item.location_id);
      const parsed = parseStorageBarcode(locationMeta?.barcode);
      if (!parsed) continue;

      const quantity = Number(item.quantity_on_hand || 0);
      const skuMeta = skuMap.get(item.sku_id);
      const skuLabel = skuMeta?.code || skuMeta?.name || shortId(item.sku_id);
      const sameSku = activeTask?.sku_id && item.sku_id === activeTask.sku_id;

      const zoneSummary = ensureSummary(zoneMap, parsed.zone);
      const aisleSummary = ensureSummary(aisleMap, `${parsed.zone}-${parsed.aisle}`);
      const rackSummary = ensureSummary(rackMap, `${parsed.zone}-${parsed.aisle}-${parsed.rack}`);
      const slotSummary = ensureSummary(slotMap, item.location_id);

      for (const summary of [zoneSummary, aisleSummary, rackSummary, slotSummary]) {
        summary.units += quantity;
        summary.occupiedLocations.add(item.location_id);
        summary.skuIds.add(item.sku_id);
        const existing = summary.skuCounts.get(item.sku_id) || { label: skuLabel, units: 0 };
        existing.units += quantity;
        summary.skuCounts.set(item.sku_id, existing);
        if (sameSku) {
          summary.sameSkuUnits += quantity;
          summary.sameSkuLotKeys.add(`${item.lot_number || ""}|${item.expiry_date || ""}`);
        }
      }
    }

    const finalize = (summary?: any) => {
      if (!summary) {
        return {
          units: 0,
          occupiedCount: 0,
          skuIds: [] as string[],
          topSkus: [] as string[],
          sameSkuLotKeys: [] as string[],
          sameSkuUnits: 0,
        };
      }
      return {
        units: summary.units,
        occupiedCount: summary.occupiedLocations.size,
        skuIds: Array.from(summary.skuIds),
        topSkus: Array.from(summary.skuCounts.values())
          .sort((a: any, b: any) => b.units - a.units)
          .slice(0, 3)
          .map((entry: any) => entry.label),
        sameSkuLotKeys: Array.from(summary.sameSkuLotKeys),
        sameSkuUnits: summary.sameSkuUnits,
      };
    };

    return {
      zone: (zone: string) => finalize(zoneMap.get(zone)),
      aisle: (zone: string, aisle: string) => finalize(aisleMap.get(`${zone}-${aisle}`)),
      rack: (zone: string, aisle: string, rack: string) => finalize(rackMap.get(`${zone}-${aisle}-${rack}`)),
      slot: (locationId: string) => finalize(slotMap.get(locationId)),
    };
  }, [activeTask?.sku_id, inventoryContext, locationMap, skuMap]);

  const confirmMutation = useMutation({
    mutationFn: async (payload: { task_id: string; destination_location_id: string; allocations?: Array<{ location_id: string; quantity: number }> }) => {
      const response = await requestWithOutbox<any>({
        url: "/fulfillment/putaway/confirm",
        data: payload,
        scope: "putaway.confirm",
        description: `Confirm putaway task ${payload.task_id}`,
      });
      if (response.data?.success === false) {
        const responseDetail =
          response.data.detail && typeof response.data.detail === "object" ? response.data.detail : null;
        const responseCode = response.data.error_code || responseDetail?.error_code || responseDetail?.code || null;
        const responseMessage =
          response.data.error ||
          responseDetail?.message ||
          responseDetail?.error ||
          t("putaway.error", "Putaway could not be completed. Check the destination and try again.");
        const error = new Error(
          responseMessage
        );
        (error as Error & { errorCode?: string }).errorCode = responseCode || undefined;
        throw error;
      }
      return response.data;
    },
    onSuccess: async (data, variables) => {
      const completedTask = enrichedTaskMap.get(variables.task_id) || activeTask;
      const destinationCount = Array.isArray(data?.allocations)
        ? data.allocations.length
        : splitAllocationRows.length || (selectedDestinationMeta ? 1 : 0);
      setLastCompletedPutaway({
        handlingUnitCode: completedTask?.handling_unit_code || null,
        destinationCount,
      });
      if (typeof window !== "undefined" && focusContext?.orderId && completedTask) {
        window.sessionStorage.setItem(
          "receiving.inboundReturnNotice",
          JSON.stringify({
            orderId: focusContext.orderId,
            handlingUnitCode: completedTask.handling_unit_code || null,
            destinationBarcode: data?.location || selectedDestinationMeta?.barcode || null,
            destinationCount,
          }),
        );
      }
      queryClient.setQueryData(putawayTasksQueryKey, (current: any) =>
        Array.isArray(current) ? current.filter((task: any) => task.id !== variables.task_id) : current
      );
      setSelectedTaskIds((current) => current.filter((id) => id !== variables.task_id));
      setSelectedTaskId(null);
      setActiveWorkspaceTab("tasks");
      clearActiveDestinationPlan();
      if (typeof window !== "undefined") {
        window.setTimeout(() => {
          successNoticeRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 0);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.putaway() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.putaway.suggestions() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.putaway.batchSuggestions() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.putaway.inventoryContext() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.list() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.summary() }),
        queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.putaway }),
        queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.inventory }),
      ]);
    },
  });

  const selectedTaskSet = useMemo(() => new Set(selectedTaskIds), [selectedTaskIds]);
  const selectedOrderKey = useMemo(
    () => getTaskOrderKey(enrichedTaskMap.get(selectedTaskIds[0])),
    [enrichedTaskMap, selectedTaskIds]
  );

  const selectedBatchTasks = useMemo(
    () => enrichedTasks.filter((task: any) => selectedTaskSet.has(task.id)),
    [enrichedTasks, selectedTaskSet]
  );

  const batchWorkspaceTaskSet = useMemo(() => {
    const ids = new Set<string>(selectedTaskIds);
    Object.keys(batchAssignments).forEach((taskId) => ids.add(taskId));
    const orderKey = selectedTaskIds.length
      ? selectedOrderKey
      : getTaskOrderKey(enrichedTaskMap.get([...ids][0]));
    ids.forEach((taskId) => {
      if (getTaskOrderKey(enrichedTaskMap.get(taskId)) !== orderKey) ids.delete(taskId);
    });
    return ids;
  }, [batchAssignments, enrichedTaskMap, selectedOrderKey, selectedTaskIds]);

  const batchWorkspaceTasks = useMemo(
    () => enrichedTasks.filter((task: any) => batchWorkspaceTaskSet.has(task.id)),
    [batchWorkspaceTaskSet, enrichedTasks]
  );

  const { data: batchSuggestions = [], isLoading: batchSuggestionsLoading } = useQuery({
    queryKey: queryKeys.putaway.batchSuggestions([...batchWorkspaceTaskSet].sort().join(",")),
    enabled: batchWorkspaceTasks.length > 0,
    queryFn: async () => {
      const results = await Promise.all(
        batchWorkspaceTasks.map(async (task: any) => {
          const response = await suggestPutawayLocation({
              warehouse_id: task.warehouse_id,
              sku_id: task.sku_id,
              quantity: task.quantity,
              source_location_id: task.source_location_id,
            })
            .then((data) => toItems<any>(data))
            .catch(() => []);
          return {
            taskId: task.id,
            suggestions: response,
          };
        })
      );
      return results;
    },
    refetchInterval: batchWorkspaceTasks.length > 0 ? LIVE_REFRESH_MS : false,
    refetchOnWindowFocus: true,
  });

  const batchSuggestionMap = useMemo(
    () =>
      new Map(
        batchSuggestions.map((item: any) => {
          const suggestions = item.suggestions.map((suggestion: any, index: number) => ({
            ...suggestion,
            rank: index + 1,
            reasonLabel: getSuggestionReasonLabel(suggestion.reason, t),
          }));
          return [
            item.taskId,
            {
              suggestions,
              topSuggestion: suggestions[0] || null,
            },
          ];
        })
      ),
    [batchSuggestions, t]
  );

  const batchReadyCount = useMemo(
    () => batchWorkspaceTasks.filter((task: any) => batchSuggestionMap.get(task.id)?.topSuggestion).length,
    [batchSuggestionMap, batchWorkspaceTasks]
  );

  const batchRackSuggestionMap = useMemo(() => {
    if (!selectedZoneKey || !selectedAisleKey || !selectedRackKey) return new Map<string, any>();
    return new Map(
      batchWorkspaceTasks.map((task: any) => {
        const suggestionsForTask = batchSuggestionMap.get(task.id)?.suggestions || [];
        const rackMatch =
          suggestionsForTask.find((suggestion: any) => {
            const parsed = parseStorageBarcode(suggestion.barcode);
            return (
              parsed &&
              parsed.zone === selectedZoneKey &&
              parsed.aisle === selectedAisleKey &&
              parsed.rack === selectedRackKey
            );
          }) || null;
        return [task.id, rackMatch];
      })
    );
  }, [batchSuggestionMap, batchWorkspaceTasks, selectedAisleKey, selectedRackKey, selectedZoneKey]);

  const batchRackReadyCount = useMemo(
    () => batchWorkspaceTasks.filter((task: any) => batchRackSuggestionMap.get(task.id)).length,
    [batchRackSuggestionMap, batchWorkspaceTasks]
  );

  const batchUnitCount = useMemo(
    () => batchWorkspaceTasks.reduce((sum: number, task: any) => sum + Number(task.quantity || 0), 0),
    [batchWorkspaceTasks]
  );

  const showBatchWorkspace = batchWorkspaceTasks.length > 1;

  const batchSkuCount = useMemo(() => {
    const skuIds = new Set(batchWorkspaceTasks.map((task: any) => task.sku_id).filter(Boolean));
    return skuIds.size;
  }, [batchWorkspaceTasks]);

  const batchAssignedCount = useMemo(
    () => batchWorkspaceTasks.filter((task: any) => Boolean(batchAssignments[task.id])).length,
    [batchAssignments, batchWorkspaceTasks]
  );

  const batchConfirmMutation = useMutation({
    mutationFn: async ({
      taskIds,
      assignments,
    }: {
      taskIds: string[];
      assignments?: Record<string, string>;
    }) => {
      const taskMap = new Map(batchWorkspaceTasks.map((task: any) => [task.id, task]));
      const failures: string[] = [];
      const failedTaskIds: string[] = [];
      let successCount = 0;
      let queuedCount = 0;

      for (const taskId of taskIds) {
        const task = taskMap.get(taskId);
        const suggested =
          assignments?.[taskId]
            ? { location_id: assignments[taskId] }
            : batchSuggestionMap.get(taskId)?.topSuggestion;
        if (!task || !suggested) {
          failures.push(task?.inbound_order_number || taskId);
          failedTaskIds.push(taskId);
          continue;
        }

        try {
          const response = await requestWithOutbox<any>({
            url: "/fulfillment/putaway/confirm",
            scope: "putaway.confirm",
            description: `Confirm putaway task ${task.id}`,
            data: {
              task_id: task.id,
              destination_location_id: suggested.location_id,
            },
          });
          if (response.data?.success === false) {
            failures.push(
              `${task.inbound_order_number || task.id}: ${
                response.data.error || t("putaway.error", "Putaway could not be completed. Check the destination and try again.")
              }`
            );
            failedTaskIds.push(task.id);
            continue;
          }
          successCount += 1;
        } catch (error) {
          if (isOfflineMutationQueuedError(error)) {
            queuedCount += 1;
            continue;
          }
          failures.push(
            `${task.inbound_order_number || task.id}: ${getApiErrorMessage(
              error,
              t("putaway.error", "Putaway could not be completed. Check the destination and try again.")
            )}`
          );
          failedTaskIds.push(task.id);
        }
      }

      return {
        successCount,
        queuedCount,
        failedCount: failures.length,
        failures,
        failedTaskIds,
      };
    },
    onSuccess: (result) => {
      setBatchResult(result);
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.putaway() });
      queryClient.invalidateQueries({ queryKey: queryKeys.putaway.suggestions() });
      queryClient.invalidateQueries({ queryKey: queryKeys.putaway.batchSuggestions() });
      queryClient.invalidateQueries({ queryKey: queryKeys.putaway.inventoryContext() });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventory.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventory.summary() });
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.putaway });
      queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.inventory });
      if (result.queuedCount === 0) {
        clearActiveDestinationPlan();
      }
      if (result.failedTaskIds.length > 0) {
        const failedTaskIds = selectedBatchTasks
          .filter((task: any) => result.failedTaskIds.includes(task.id))
          .map((task: any) => task.id);
        setSelectedTaskIds(failedTaskIds);
        setSelectedTaskId(failedTaskIds[0] || null);
        setBatchAssignments((current) =>
          Object.fromEntries(Object.entries(current).filter(([taskId]) => failedTaskIds.includes(taskId)))
        );
      } else if (result.queuedCount === 0) {
        setSelectedTaskIds([]);
        setSelectedTaskId(null);
        setBatchAssignments({});
      }
    },
  });

  const handleUseSuggestion = (locationId: string) => {
    setSelectedDestinationId(locationId);
    setOtherDestinationCode("");
  };

  const clearActiveDestinationPlan = () => {
    setSelectedDestinationId("");
    setOtherDestinationCode("");
    setPrimaryDestinationQuantity(activeTask ? String(Number(activeTask.quantity || 0)) : "");
    setSplitDestinations([]);
  };

  const handleAddSplitDestination = () => {
    const totalQuantity = Number(activeTask?.quantity || 0);
    if (
      splitDestinations.length === 0 &&
      totalQuantity > 1 &&
      (!primaryDestinationQuantity || Number(primaryDestinationQuantity) === totalQuantity)
    ) {
      setPrimaryDestinationQuantity(String(totalQuantity - 1));
    }
    setSplitDestinations((current) => {
      const defaultQuantity = totalQuantity > current.length + 1 ? "1" : "";
      return [...current, { locationId: "", quantity: defaultQuantity, zone: "", aisle: "", rack: "", level: "" }];
    });
  };

  const handleUpdateSplitDestination = (index: number, patch: Partial<SplitDestinationDraft>) => {
    setSplitDestinations((current) => current.map((entry, idx) => (idx === index ? { ...entry, ...patch } : entry)));
  };

  const handleRemoveSplitDestination = (index: number) => {
    setSplitDestinations((current) => current.filter((_, idx) => idx !== index));
  };

  const toggleTaskSelection = (taskId: string) => {
    setBatchResult(null);
    if (selectedTaskIds.includes(taskId)) {
      setBatchAssignments((current) => {
        const next = { ...current };
        delete next[taskId];
        return next;
      });
      setSelectedTaskIds((current) => current.filter((id) => id !== taskId));
      return;
    }

    const taskOrderKey = getTaskOrderKey(enrichedTaskMap.get(taskId));
    const currentOrderKey = getTaskOrderKey(enrichedTaskMap.get(selectedTaskIds[0]));
    if (selectedTaskIds.length > 0 && currentOrderKey !== taskOrderKey) {
      setSelectedTaskIds([taskId]);
      setSelectedTaskId(taskId);
      setBatchAssignments({});
      clearActiveDestinationPlan();
      return;
    }

    setSelectedTaskIds((current) => [...current, taskId]);
    setSelectedTaskId(taskId);
  };

  const focusTask = (taskId: string, selectionMode: "single" | "merge" = "merge") => {
    setSelectedTaskId(taskId);
    setActiveWorkspaceTab("work");
    if (selectionMode === "single") {
      setSelectedTaskIds([taskId]);
      setBatchAssignments({});
      clearActiveDestinationPlan();
      return;
    }
    const taskOrderKey = getTaskOrderKey(enrichedTaskMap.get(taskId));
    const currentOrderKey = getTaskOrderKey(enrichedTaskMap.get(selectedTaskIds[0]));
    if (selectedTaskIds.length > 0 && currentOrderKey !== taskOrderKey) {
      setSelectedTaskIds([taskId]);
      setBatchAssignments({});
    } else if (!selectedTaskIds.includes(taskId)) {
      setSelectedTaskIds((current) => [...current, taskId]);
    }
    clearActiveDestinationPlan();
  };

  const handleSelectAllTasks = () => {
    setBatchResult(null);
    const baseTask = enrichedTaskMap.get(selectedTaskId || "") || filteredTasks[0];
    const orderKey = getTaskOrderKey(baseTask);
    const taskIds = filteredTasks
      .filter((task: any) => getTaskOrderKey(task) === orderKey)
      .map((task: any) => task.id);
    setSelectedTaskIds(taskIds);
    setSelectedTaskId(taskIds[0] || null);
    if (taskIds.length > 0) setActiveWorkspaceTab("work");
    setBatchAssignments({});
    clearActiveDestinationPlan();
  };

  const handleClearSelection = () => {
    setBatchResult(null);
    setSelectedTaskIds([]);
    setBatchAssignments({});
    clearActiveDestinationPlan();
  };

  const handleAssignTaskToLocation = (taskId: string, locationId: string) => {
    setBatchResult(null);
    const taskOrderKey = getTaskOrderKey(enrichedTaskMap.get(taskId));
    const currentOrderKey = getTaskOrderKey(enrichedTaskMap.get(selectedTaskIds[0]));
    const isSameOrder = selectedTaskIds.length === 0 || currentOrderKey === taskOrderKey;
    setBatchAssignments((current) => (isSameOrder ? { ...current, [taskId]: locationId } : { [taskId]: locationId }));
    if (selectedTaskIds.length <= 1) {
      setSelectedTaskId(taskId);
    }
    if (!isSameOrder) {
      setSelectedTaskId(taskId);
      setSelectedTaskIds([taskId]);
    } else if (!selectedTaskIds.includes(taskId)) {
      setSelectedTaskIds((current) => [...current, taskId]);
    }
  };

  const handleAssignSelectedTasksToLevel = (startingLocationId: string) => {
    if (!activeLevel || selectedTaskIds.length <= 1) return false;

    const remainingTaskIds = selectedBatchTasks
      .filter((task: any) => selectedTaskIds.includes(task.id) && !batchAssignments[task.id])
      .map((task: any) => task.id);

    if (remainingTaskIds.length === 0) return false;

    const slotIds = activeLevel.locations.map((location: any) => location.id);
    const startIndex = slotIds.indexOf(startingLocationId);
    if (startIndex === -1) return false;

    const occupiedSlotIds = new Set(
      Object.entries(batchAssignments)
        .filter(([taskId]) => !remainingTaskIds.includes(taskId))
        .map(([, locationId]) => locationId)
    );

    const orderedSlotIds = [...slotIds.slice(startIndex), ...slotIds.slice(0, startIndex)];
    const freeSlotIds = orderedSlotIds.filter((locationId) => !occupiedSlotIds.has(locationId));
    if (freeSlotIds.length === 0) return false;

    setBatchResult(null);
    setBatchAssignments((current) => {
      const next = { ...current };
      remainingTaskIds.forEach((taskId, index) => {
        const targetLocationId = freeSlotIds[index];
        if (targetLocationId) next[taskId] = targetLocationId;
      });
      return next;
    });
    return true;
  };

  const handleUnassignTask = (taskId: string) => {
    setBatchAssignments((current) => {
      const next = { ...current };
      delete next[taskId];
      return next;
    });
  };

  const handleSelectSourceGroup = (taskIds: string[]) => {
    const sameOrderTaskIds = keepTaskIdsInOneOrder(taskIds, enrichedTaskMap);
    setSelectedTaskIds(sameOrderTaskIds);
    setSelectedTaskId(sameOrderTaskIds[0] || null);
    if (sameOrderTaskIds.length > 0) setActiveWorkspaceTab("work");
    setBatchAssignments({});
    setBatchResult(null);
    clearActiveDestinationPlan();
  };

  const handleChooseZone = (zone: string) => {
    setSelectedZoneKey(zone);
    setSelectedAisleKey("");
    setSelectedRackKey("");
    setSelectedLevelKey("");
    clearActiveDestinationPlan();
  };

  const handleChooseAisle = (aisle: string) => {
    setSelectedAisleKey(aisle);
    setSelectedRackKey("");
    setSelectedLevelKey("");
    clearActiveDestinationPlan();
  };

  const handleChooseRack = (rack: string) => {
    setSelectedRackKey(rack);
    setSelectedLevelKey("");
    clearActiveDestinationPlan();
  };

  const handleChooseLevel = (level: string) => {
    setSelectedLevelKey(level);
    clearActiveDestinationPlan();
  };

  const handleChooseSlot = (location: any) => {
    const parsed = parseStorageBarcode(location?.barcode);
    if (parsed) {
      setSelectedZoneKey(parsed.zone);
      setSelectedAisleKey(parsed.aisle);
      setSelectedRackKey(parsed.rack);
      setSelectedLevelKey(parsed.level);
    }
    setOtherDestinationCode("");
    setSelectedDestinationId(location.id);
  };

  const scrollToPutawayControl = (elementId: string) => {
    if (typeof document === "undefined") return;
    document.getElementById(elementId)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const finalSlotPickerTargetId = () =>
    typeof window !== "undefined" && window.innerWidth < 768
      ? "putaway-final-slot-picker-mobile"
      : "putaway-final-slot-picker-desktop";

  const resetPickerPath = () => {
    setSelectedZoneKey("");
    setSelectedAisleKey("");
    setSelectedRackKey("");
    setSelectedLevelKey("");
    clearActiveDestinationPlan();
  };

  const resetPickerFrom = (scope: "zone" | "aisle" | "rack" | "level") => {
    if (scope === "zone") {
      resetPickerPath();
      return;
    }
    if (scope === "aisle") {
      setSelectedAisleKey("");
      setSelectedRackKey("");
      setSelectedLevelKey("");
      clearActiveDestinationPlan();
      return;
    }
    if (scope === "rack") {
      setSelectedRackKey("");
      setSelectedLevelKey("");
      clearActiveDestinationPlan();
      return;
    }
    setSelectedLevelKey("");
    clearActiveDestinationPlan();
  };

  const handleConfirm = () => {
    if (!activeTask || !selectedDestinationId || !splitAllocationPreview.isValid || destinationPlacementBlocked) return;
    const extraAllocations = splitAllocationPreview.extraAllocations.map((entry) => ({
      location_id: entry.locationId,
      quantity: entry.quantity,
    }));
    const allocations = [{ location_id: selectedDestinationId, quantity: splitAllocationPreview.primaryQuantity }, ...extraAllocations];
    confirmMutation.mutate({
      task_id: activeTask.id,
      destination_location_id: selectedDestinationId,
      allocations: allocations.length > 1 ? allocations : undefined,
    });
  };

  const handleAutoPlanCurrentRack = () => {
    const runnableTasks = batchWorkspaceTasks
      .map((task: any) => ({
        taskId: task.id,
        suggestion: batchRackSuggestionMap.get(task.id) || null,
      }))
      .filter((entry: any) => entry.suggestion?.location_id);

    if (runnableTasks.length === 0) return;

    setBatchResult(null);
    setBatchAssignments((current) => {
      const next = { ...current };
      batchWorkspaceTasks.forEach((task: any) => {
        delete next[task.id];
      });
      for (const entry of runnableTasks) {
        next[entry.taskId] = entry.suggestion.location_id;
      }
      return next;
    });

    revealFinalReview(
      t("putaway.executionFinalRackPlanned", "{count} tasks were placed into the current rack on the board. Review them, then confirm putaway.", {
        count: runnableTasks.length,
      })
    );
  };

  const clearBatchPlannedAssignments = () => {
    setBatchAssignments((current) => {
      const next = { ...current };
      batchWorkspaceTasks.forEach((task: any) => {
        delete next[task.id];
      });
      return next;
    });
    setPlanReviewNotice(
      t(
        "putaway.executionFinalCleared",
        "The current board plan was cleared. You can now place tasks manually again."
      )
    );
    setHighlightFinalReview(true);
    window.setTimeout(() => setHighlightFinalReview(false), 2200);
  };

  const handleBatchAssignedConfirm = () => {
    const runnableTaskIds = batchWorkspaceTasks
      .filter((task: any) => batchAssignments[task.id])
      .map((task: any) => task.id);

    if (runnableTaskIds.length === 0) return;
    const approved = window.confirm(
      t(
        "putaway.batchAssignedConfirmPrompt",
        "Confirm putaway for {count} selected tasks using the locations you placed on the visual board?",
        { count: runnableTaskIds.length }
      )
    );
    if (!approved) return;
    batchConfirmMutation.mutate({ taskIds: runnableTaskIds, assignments: batchAssignments });
  };

  const revealFinalReview = (notice: string) => {
    setPlanReviewNotice(notice);
    setHighlightFinalReview(true);
    window.setTimeout(() => setHighlightFinalReview(false), 2200);
    window.setTimeout(() => {
      finalReviewRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
  };

  const handleAutoPlanBatch = () => {
    const suggestedEntries = batchWorkspaceTasks
      .map((task: any) => ({
        taskId: task.id,
        suggestion: batchSuggestionMap.get(task.id)?.topSuggestion || null,
      }))
      .filter((entry: any) => entry.suggestion?.location_id);

    if (suggestedEntries.length === 0) return;

    setBatchResult(null);
    setBatchAssignments((current) => {
      const next = { ...current };
      batchWorkspaceTasks.forEach((task: any) => {
        delete next[task.id];
      });
      for (const entry of suggestedEntries) {
        next[entry.taskId] = entry.suggestion.location_id;
      }
      return next;
    });

    const firstLocation = locationMap.get(suggestedEntries[0].suggestion.location_id);
    if (firstLocation?.barcode) {
      const parsed = parseStorageBarcode(firstLocation.barcode);
      if (parsed) {
        setSelectedZoneKey(parsed.zone);
        setSelectedAisleKey(parsed.aisle);
        setSelectedRackKey(parsed.rack);
        setSelectedLevelKey(parsed.level);
      }
    }

    revealFinalReview(
      t("putaway.executionFinalSystemPlanned", "{count} tasks were placed onto the board with system suggestions. Review them, then confirm putaway.", {
        count: suggestedEntries.length,
      })
    );
  };

  const pendingUnits =
    putawayWorkbenchSummary?.pending_units ??
    enrichedTasks.reduce((sum: number, task: any) => sum + (task.quantity || 0), 0);
  const pendingTasksCount = putawayWorkbenchSummary?.pending_tasks ?? enrichedTasks.length;
  const routeExceptionTasks = useMemo(
    () =>
      enrichedTasks.filter(
        (task: any) =>
          task.execution_mode === "hybrid" ||
          task.execution_reason === "human_to_agv_handoff_required" ||
          task.execution_reason === "unit_exceeds_agv_payload" ||
          task.execution_reason === "no_agv_storage_available",
      ),
    [enrichedTasks],
  );
  const routeSummary = useMemo(
    () => ({
      agv: enrichedTasks.filter((task: any) => task.execution_mode === "agv").length,
      worker: enrichedTasks.filter((task: any) => task.execution_mode === "human").length,
      hybrid: enrichedTasks.filter((task: any) => task.execution_mode === "hybrid").length,
    }),
    [enrichedTasks],
  );
  const batchCandidateSummary = useMemo(() => {
    const groups = new Map<string, any[]>();
    enrichedTasks.forEach((task: any) => {
      const key = `${getTaskOrderKey(task)}::${task.source_location_id || task.source_barcode || "unknown-source"}`;
      const group = groups.get(key) || [];
      group.push(task);
      groups.set(key, group);
    });
    const candidates = Array.from(groups.values())
      .filter((group) => group.length > 1)
      .sort((a, b) => getTaskCreatedAt(a[0]) - getTaskCreatedAt(b[0]));
    return {
      groupCount: candidates.length,
      taskCount: candidates.reduce((sum, group) => sum + group.length, 0),
      firstTaskIds: candidates[0]?.map((task: any) => task.id) || [],
    };
  }, [enrichedTasks]);
  const openFirstPutawayTask = () => {
    const nextTask = filteredTasks[0] || enrichedTasks[0];
    if (!nextTask) return;
    focusTask(nextTask.id, "single");
  };
  const openRouteExceptionQueue = () => {
    const nextTask = routeExceptionTasks[0];
    setTaskSearch("");
    setExecutionFilter(nextTask?.execution_mode === "hybrid" ? "hybrid" : "all");
    setActiveWorkspaceTab("tasks");
    if (nextTask) {
      setSelectedTaskId(nextTask.id);
    }
  };
  const openBatchCandidateQueue = () => {
    if (batchCandidateSummary.firstTaskIds.length === 0) return;
    setTaskSearch("");
    setExecutionFilter("all");
    setViewMode("handling_unit");
    handleSelectSourceGroup(batchCandidateSummary.firstTaskIds);
  };
  const openAllPutawayWork = () => {
    setTaskSearch("");
    setExecutionFilter("all");
    setViewMode("handling_unit");
    setActiveWorkspaceTab("tasks");
  };
  const selectedDestinationMeta = destinationCandidates.find((location: any) => location.id === selectedDestinationId) || null;
  const confirmErrorMessage = confirmMutation.error
    ? isOfflineMutationQueuedError(confirmMutation.error)
      ? offlineQueuedText()
      : getApiErrorMessage(
          confirmMutation.error,
          t("putaway.error", "Putaway could not be completed. Check the destination and try again.")
        )
    : "";
  const recoveryOrderId =
    focusContext?.orderId ||
    (activeTask?.reference_type === "inbound_order" ? activeTask.reference_id : null);
  const receivingRecoveryPath = recoveryOrderId ? `/receiving/orders/${recoveryOrderId}` : "/receiving";
  const getPutawayRecoveryState = (message: string, code: string | null = null): PutawayRecoveryState => {
    const recoveryKind = classifyPutawayRecoveryCode(code);

    if (recoveryKind === "source_staging_missing") {
      return {
        code: code || "source_staging_missing",
        title: t("putaway.recoverySourceStagingTitle", "Dock source is missing"),
        body: t("putaway.recoverySourceStagingBody", "Open the receiving record, confirm the dock or staging location, then refresh this task before putaway."),
        actions: ["open_receiving", "refresh_task", "back_to_list"],
      };
    }

    if (recoveryKind === "source_stock_mismatch") {
      return {
        code: code || "source_stock_mismatch",
        title: t("putaway.recoverySourceInventoryTitle", "Source stock does not match this task"),
        body: t("putaway.recoverySourceInventoryBody", "Correct or consolidate the staging inventory first. If the receipt changed, return to receiving before trying putaway again."),
        actions: ["open_inventory", "open_receiving", "refresh_task", "back_to_list"],
      };
    }

    if (recoveryKind === "allocation_invalid") {
      return {
        code: code || "allocation_invalid",
        title: t("putaway.recoveryAllocationTitle", "Quantity plan needs correction"),
        body: t("putaway.recoveryAllocationBody", "Fix the split plan so every destination has a positive quantity and the assigned units equal the task total."),
        actions: ["fix_quantity", "choose_slot", "back_to_list"],
      };
    }

    if (recoveryKind === "destination_blocked") {
      return {
        code: code || "destination_blocked",
        title: t("putaway.recoveryDestinationTitle", "Choose another final slot"),
        body: t("putaway.recoveryDestinationBody", "This slot cannot receive the task. Pick an available storage slot that matches the warehouse and SKU policy, then scan it again."),
        actions: ["choose_slot", "refresh_task", "back_to_list"],
      };
    }

    if (recoveryKind === "same_sku_policy_blocked") {
      return {
        code: code || "same_sku_policy_blocked",
        title: t("putaway.recoverySameSkuPolicyTitle", "Warehouse policy blocks this slot"),
        body: t("putaway.recoverySameSkuPolicyBody", "Same-SKU consolidation is not allowed here. Choose an empty final slot or ask a supervisor to change the policy."),
        actions: ["choose_slot", "back_to_list"],
      };
    }

    if (recoveryKind === "lot_expiry_mismatch") {
      return {
        code: code || "lot_expiry_mismatch",
        title: t("putaway.recoveryLotPolicyTitle", "Lot or expiry does not match"),
        body: t("putaway.recoveryLotPolicyBody", "Choose an empty slot or a slot with the same SKU, lot, and expiry before confirming putaway."),
        actions: ["choose_slot", "back_to_list"],
      };
    }

    if (recoveryKind === "inbound_not_released") {
      return {
        code: code || "inbound_not_released",
        title: t("putaway.recoveryInboundNotReleasedTitle", "Inbound is not released to putaway"),
        body: t("putaway.recoveryInboundNotReleasedBody", "Return to receiving, finish or release the inbound order, then refresh the putaway list."),
        actions: ["open_receiving", "refresh_task", "back_to_list"],
      };
    }

    if (recoveryKind === "task_not_ready") {
      return {
        code: code || "task_not_ready",
        title: t("putaway.recoveryStaleTaskTitle", "Task is no longer ready"),
        body: t("putaway.recoveryStaleTaskBody", "Refresh this task and return to the putaway list. If it disappeared, another operator or upstream correction already changed it."),
        actions: ["refresh_task", "back_to_list"],
      };
    }

    return {
      code: code || "confirm_failed",
      title: t("putaway.recoveryGenericTitle", "Putaway could not be confirmed"),
      body: t("putaway.recoveryGenericBody", "Refresh the task, check the final slot, and choose another slot if this one still fails."),
      actions: ["refresh_task", "choose_slot", "back_to_list"],
    };
  };
  const confirmErrorCode = confirmMutation.error ? getApiErrorCode(confirmMutation.error) : null;
  const confirmRecoveryState = confirmErrorMessage ? getPutawayRecoveryState(confirmErrorMessage, confirmErrorCode) : null;

  const handlePutawayRecoveryAction = (action: PutawayRecoveryAction) => {
    if (action === "choose_slot") {
      confirmMutation.reset();
      clearActiveDestinationPlan();
      window.setTimeout(() => scrollToPutawayControl(finalSlotPickerTargetId()), 0);
      return;
    }
    if (action === "back_to_list") {
      confirmMutation.reset();
      setActiveWorkspaceTab("tasks");
      return;
    }
    if (action === "fix_quantity") {
      confirmMutation.reset();
      window.setTimeout(() => scrollToPutawayControl("putaway-split-plan"), 0);
      return;
    }
    if (action === "refresh_task") {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.putaway() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.putaway.suggestions() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.putaway.inventoryContext() }),
        queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.putaway }),
      ]).then(() => confirmMutation.reset());
    }
  };

  useEffect(() => {
    setMobileDestinationConfirmed(false);
    setMobileDestinationScanError(null);
  }, [selectedDestinationId]);

  const handleMobileDestinationScan = (value: string) => {
    const expected = selectedDestinationMeta?.barcode || "";
    const normalize = (input: string) => input.trim().toLowerCase().replace(/\s+/g, "");
    if (!expected) return;
    if (normalize(value) === normalize(expected)) {
      setMobileDestinationConfirmed(true);
      setMobileDestinationScanError(null);
      return;
    }
    setMobileDestinationConfirmed(false);
    setMobileDestinationScanError(
      t("putaway.mobileDestinationMismatch", "Scanned final slot does not match {expected}.", {
        expected,
      })
    );
  };

  const splitAllocationPreview = useMemo(() => {
    const totalQuantity = Number(activeTask?.quantity || 0);
    const primaryQuantity = Number(primaryDestinationQuantity || 0);
    const extraAllocations = splitDestinations
      .map((entry) => ({
        locationId: entry.locationId,
        quantity: Number(entry.quantity || 0),
        meta: destinationCandidates.find((location: any) => location.id === entry.locationId) || null,
      }))
      .filter((entry) => entry.locationId && entry.quantity > 0);
    const extraQuantity = extraAllocations.reduce((sum, entry) => sum + entry.quantity, 0);
    const totalAssigned = primaryQuantity + extraQuantity;
    const splitEntriesComplete = splitDestinations.every((entry) => entry.locationId && Number(entry.quantity || 0) > 0);
    const locationIds = [selectedDestinationId, ...extraAllocations.map((entry) => entry.locationId)].filter(Boolean);
    const destinationsAreUnique = new Set(locationIds).size === locationIds.length;
    const quantityMatchesTotal = totalQuantity > 0 && totalAssigned === totalQuantity;
    return {
      extraAllocations,
      extraQuantity,
      primaryQuantity,
      totalAssigned,
      quantityMatchesTotal,
      splitEntriesComplete,
      destinationsAreUnique,
      isValid:
        Boolean(selectedDestinationId) &&
        totalQuantity > 0 &&
        primaryQuantity > 0 &&
        quantityMatchesTotal &&
        splitEntriesComplete &&
        destinationsAreUnique,
    };
  }, [activeTask?.quantity, destinationCandidates, primaryDestinationQuantity, selectedDestinationId, splitDestinations]);

  const splitAllocationRows = useMemo(() => {
    if (!activeTask || !selectedDestinationId || splitAllocationPreview.primaryQuantity <= 0) return [];
    const primaryMeta = destinationCandidates.find((location: any) => location.id === selectedDestinationId) || null;
    return [
      {
        locationId: selectedDestinationId,
        barcode: primaryMeta?.barcode || shortId(selectedDestinationId),
        quantity: splitAllocationPreview.primaryQuantity,
        primary: true,
      },
      ...splitAllocationPreview.extraAllocations.map((entry) => ({
        locationId: entry.locationId,
        barcode: entry.meta?.barcode || shortId(entry.locationId),
        quantity: entry.quantity,
        primary: false,
      })),
    ];
  }, [activeTask, destinationCandidates, selectedDestinationId, splitAllocationPreview]);

  const destinationPlacementIssues = useMemo(() => {
    if (!activeTask) return [];
    const sourceLotKey = `${activeTask.lot_number || ""}|${activeTask.expiry_date || ""}`;
    return splitAllocationRows
      .map((row) => {
        const summary = inventoryContextSummary.slot(row.locationId);
        if (summary.units <= 0) return null;

        const slotSkuIds = summary.skuIds as string[];
        const sameSkuLotKeys = summary.sameSkuLotKeys as string[];
        const hasDifferentSku = slotSkuIds.some((skuId) => skuId !== activeTask.sku_id);
        if (hasDifferentSku && placementPolicy.differentSkuSlotPolicy !== "allow") {
          return {
            severity: placementPolicy.differentSkuSlotPolicy === "block" ? "block" : "warn",
            barcode: row.barcode,
            title: t("putaway.slotPolicyDifferentSkuTitle", "Different SKU already in this slot"),
            body: t(
              "putaway.slotPolicyDifferentSkuBody",
              "This slot contains another SKU. Choose an empty slot or a slot with the same SKU unless your warehouse policy allows mixed SKU storage."
            ),
          };
        }

        const hasSameSku = slotSkuIds.includes(activeTask.sku_id);
        if (hasSameSku && !placementPolicy.allowSameSkuConsolidation) {
          return {
            severity: "block",
            barcode: row.barcode,
            title: t("putaway.slotPolicySameSkuDisabledTitle", "Same-SKU consolidation is disabled"),
            body: t(
              "putaway.slotPolicySameSkuDisabledBody",
              "This slot already contains the same SKU, but the warehouse rule requires a separate slot."
            ),
          };
        }

        const lotMismatch = hasSameSku && sameSkuLotKeys.some((lotKey) => lotKey !== sourceLotKey);
        if (lotMismatch && placementPolicy.lotExpiryMismatchPolicy !== "allow") {
          return {
            severity: placementPolicy.lotExpiryMismatchPolicy === "block" ? "block" : "warn",
            barcode: row.barcode,
            title: t("putaway.slotPolicyLotExpiryTitle", "Same SKU, different lot or expiry"),
            body: t(
              "putaway.slotPolicyLotExpiryBody",
              "This slot already contains the same SKU with different lot or expiry data. Continue only if that matches the warehouse policy."
            ),
          };
        }

        return null;
      })
      .filter(Boolean) as Array<{ severity: "block" | "warn"; barcode: string; title: string; body: string }>;
  }, [activeTask, inventoryContextSummary, placementPolicy, splitAllocationRows, t]);

  const destinationPlacementBlocked = destinationPlacementIssues.some((issue) => issue.severity === "block");

  const plannedDestinationCount = splitAllocationRows.length || (selectedDestinationId ? 1 : 0);
  const splitQuantityStatusLabel = splitAllocationPreview.quantityMatchesTotal
    ? t("putaway.splitQuantityMatched", "Assigned {assigned} / task total {total}", {
        assigned: splitAllocationPreview.totalAssigned,
        total: Number(activeTask?.quantity || 0),
      })
    : t("putaway.splitQuantityMismatch", "Assigned {assigned} / task total {total}", {
        assigned: splitAllocationPreview.totalAssigned,
        total: Number(activeTask?.quantity || 0),
      });
  const splitSummaryLabel =
    plannedDestinationCount > 1
      ? t("putaway.splitSummaryInline", "Primary {primary} · Extra {extra}", {
          primary: splitAllocationPreview.primaryQuantity,
          extra: splitAllocationPreview.extraQuantity,
        })
      : t("putaway.splitSummaryInlineSingle", "Single final slot");

  useEffect(() => {
    clearActiveDestinationPlan();
  }, [activeTask?.id]);
  const visualLocationTree = useMemo(() => {
    const grouped = new Map<
      string,
      {
        zone: string;
        aisles: Map<
          string,
          {
            aisle: string;
            racks: Map<string, { levels: Map<string, any[]> }>;
          }
        >;
      }
    >();

    for (const location of destinationCandidates) {
      const parsed = parseStorageBarcode(location.barcode);
      if (!parsed) continue;
      if (!grouped.has(parsed.zone)) {
        grouped.set(parsed.zone, {
          zone: parsed.zone,
          aisles: new Map(),
        });
      }
      const zoneGroup = grouped.get(parsed.zone)!;
      if (!zoneGroup.aisles.has(parsed.aisle)) {
        zoneGroup.aisles.set(parsed.aisle, {
          aisle: parsed.aisle,
          racks: new Map(),
        });
      }
      const aisleGroup = zoneGroup.aisles.get(parsed.aisle)!;
      if (!aisleGroup.racks.has(parsed.rack)) {
        aisleGroup.racks.set(parsed.rack, { levels: new Map() });
      }
      const rackGroup = aisleGroup.racks.get(parsed.rack)!;
      if (!rackGroup.levels.has(parsed.level)) {
        rackGroup.levels.set(parsed.level, []);
      }
      rackGroup.levels.get(parsed.level)!.push({ ...location, parsed });
    }

    return Array.from(grouped.values())
      .sort((a, b) => a.zone.localeCompare(b.zone))
      .map((zone) => ({
        zone: zone.zone,
        aisles: Array.from(zone.aisles.values())
          .sort((a, b) => a.aisle.localeCompare(b.aisle))
          .map((aisle) => ({
            aisle: aisle.aisle,
            racks: Array.from(aisle.racks.entries())
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([rack, rackValue]) => ({
                rack,
                levels: Array.from(rackValue.levels.entries())
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([level, levelLocations]) => ({
                    level,
                    locations: levelLocations.sort((a, b) => a.parsed.position.localeCompare(b.parsed.position)),
                  })),
              })),
          })),
      }));
  }, [destinationCandidates]);

  useEffect(() => {
    if (!activeTask || visualLocationTree.length === 0) {
      setSelectedZoneKey("");
      setSelectedAisleKey("");
      setSelectedRackKey("");
      return;
    }

    if (!selectedZoneKey) {
      setSelectedAisleKey("");
      setSelectedRackKey("");
      setSelectedLevelKey("");
      return;
    }

    const zone = visualLocationTree.find((item) => item.zone === selectedZoneKey);
    if (!zone) {
      setSelectedZoneKey("");
      setSelectedAisleKey("");
      setSelectedRackKey("");
      setSelectedLevelKey("");
      clearActiveDestinationPlan();
      return;
    }

    if (!selectedAisleKey) {
      setSelectedRackKey("");
      setSelectedLevelKey("");
      return;
    }

    const aisle = zone.aisles.find((item) => item.aisle === selectedAisleKey);
    if (!aisle) {
      setSelectedAisleKey("");
      setSelectedRackKey("");
      setSelectedLevelKey("");
      clearActiveDestinationPlan();
      return;
    }

    if (!selectedRackKey) {
      setSelectedLevelKey("");
      return;
    }

    const rack = aisle.racks.find((item) => item.rack === selectedRackKey);
    if (!rack) {
      setSelectedRackKey("");
      setSelectedLevelKey("");
      clearActiveDestinationPlan();
      return;
    }

    if (!selectedLevelKey) return;

    const level = rack.levels.find((item) => item.level === selectedLevelKey);
    if (!level) {
      setSelectedLevelKey("");
      clearActiveDestinationPlan();
    }
  }, [activeTask, selectedAisleKey, selectedLevelKey, selectedRackKey, selectedZoneKey, visualLocationTree]);

  useEffect(() => {
    if (!selectedDestinationId) return;
    const selectedLocation = destinationCandidates.find((location: any) => location.id === selectedDestinationId);
    const parsed = parseStorageBarcode(selectedLocation?.barcode);
    if (!parsed) return;
    if (parsed.zone !== selectedZoneKey) setSelectedZoneKey(parsed.zone);
    if (parsed.aisle !== selectedAisleKey) setSelectedAisleKey(parsed.aisle);
    if (parsed.rack !== selectedRackKey) setSelectedRackKey(parsed.rack);
    if (parsed.level !== selectedLevelKey) setSelectedLevelKey(parsed.level);
  }, [destinationCandidates, selectedAisleKey, selectedDestinationId, selectedLevelKey, selectedRackKey, selectedZoneKey]);

  useEffect(() => {
    if (batchWorkspaceTasks.length > 1) return;
    setSelectedZoneKey("");
    setSelectedAisleKey("");
    setSelectedRackKey("");
    setSelectedLevelKey("");
    clearActiveDestinationPlan();
  }, [activeTask?.id, batchWorkspaceTasks.length]);

  useEffect(() => {
    const validTaskIds = new Set(enrichedTasks.map((task: any) => task.id));
    setSelectedTaskIds((current) => current.filter((id) => validTaskIds.has(id)));
    setBatchAssignments((current) =>
      Object.fromEntries(Object.entries(current).filter(([taskId]) => validTaskIds.has(taskId)))
    );
  }, [enrichedTasks]);

  useEffect(() => {
    if (selectedTaskIds.length === 0) return;
    if (!selectedTaskId || !selectedTaskIds.includes(selectedTaskId)) {
      setSelectedTaskId(selectedTaskIds[0]);
    }
  }, [selectedTaskId, selectedTaskIds]);

  useEffect(() => {
    if (filteredTasks.length === 0) return;
    const visibleTaskIds = new Set(filteredTasks.map((task: any) => task.id));
    if (!selectedTaskId || !visibleTaskIds.has(selectedTaskId)) {
      setSelectedTaskId(filteredTasks[0].id);
    }
  }, [filteredTasks, selectedTaskId]);

  const activeZone = useMemo(
    () => visualLocationTree.find((zone) => zone.zone === selectedZoneKey) || null,
    [selectedZoneKey, visualLocationTree]
  );

  const activeAisle = useMemo(
    () => activeZone?.aisles.find((aisle) => aisle.aisle === selectedAisleKey) || null,
    [activeZone, selectedAisleKey]
  );

  const activeRack = useMemo(
    () => activeAisle?.racks.find((rack) => rack.rack === selectedRackKey) || null,
    [activeAisle, selectedRackKey]
  );

  const activeLevel = useMemo(
    () => activeRack?.levels.find((level) => level.level === selectedLevelKey) || null,
    [activeRack, selectedLevelKey]
  );

  const activeLevelLocations = useMemo(
    () => activeLevel?.locations || [],
    [activeLevel]
  );

  const unstructuredDestinationCandidates = useMemo(
    () => destinationCandidates.filter((location: any) => !parseStorageBarcode(location.barcode)),
    [destinationCandidates]
  );

  const normalizedOtherDestinationCode = otherDestinationCode.trim().toLowerCase();
  const otherDestinationMatch = useMemo(
    () =>
      normalizedOtherDestinationCode
        ? unstructuredDestinationCandidates.find(
            (location: any) => String(location.barcode || "").trim().toLowerCase() === normalizedOtherDestinationCode
          ) || null
        : null,
    [normalizedOtherDestinationCode, unstructuredDestinationCandidates]
  );

  const handleUseOtherDestinationCode = () => {
    if (!otherDestinationMatch) return;
    setSelectedZoneKey("");
    setSelectedAisleKey("");
    setSelectedRackKey("");
    setSelectedLevelKey("");
    setSelectedDestinationId(otherDestinationMatch.id);
  };

  const activeRackSummary = useMemo(
    () => (activeZone && activeAisle && activeRack ? inventoryContextSummary.rack(activeZone.zone, activeAisle.aisle, activeRack.rack) : null),
    [activeAisle, activeRack, activeZone, inventoryContextSummary]
  );

  const batchTaskMap = useMemo(() => new Map(batchWorkspaceTasks.map((task: any) => [task.id, task])), [batchWorkspaceTasks]);

  const batchSourceGroups = useMemo(() => {
    const groups = new Map<string, any[]>();
    batchWorkspaceTasks.forEach((task: any) => {
      if (batchAssignments[task.id]) return;
      const key = task.source_barcode || "—";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(task);
    });
    return Array.from(groups.entries()).map(([source, items]) => ({ source, items }));
  }, [batchAssignments, batchWorkspaceTasks]);

  const plannedBatchSourceGroups = useMemo(() => {
    const groups = new Map<string, any[]>();
    batchWorkspaceTasks.forEach((task: any) => {
      if (!batchAssignments[task.id]) return;
      const key = task.source_barcode || "—";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(task);
    });
    return Array.from(groups.entries()).map(([source, items]) => ({ source, items }));
  }, [batchAssignments, batchWorkspaceTasks]);

  const taskGroups = useMemo(() => {
    const groups = new Map<
      string,
      {
        key: string;
        title: string;
        subtitle: string;
        helper: string;
        source: string;
        items: any[];
        totalUnits: number;
      }
    >();

    filteredTasks.forEach((task: any) => {
      let groupKey = `${task.inbound_order_number}::${task.source_barcode}`;
      let title = task.inbound_order_number;
      let subtitle = `${t("common.from", "From")}: ${task.source_barcode || "—"}`;
      let helper = t("putaway.groupHelperInbound", "Inbound order view");

      if (viewMode === "handling_unit") {
        groupKey = task.handling_unit_code || task.id;
        title = task.handling_unit_code || shortId(task.id);
        subtitle = task.sku_label;
        helper = t("putaway.groupHelperHandlingUnit", "Package / pallet view");
      } else if (viewMode === "sku") {
        groupKey = `${task.sku_id || task.id}::${getTaskOrderKey(task)}`;
        title = task.sku_label || shortId(task.sku_id);
        subtitle = `${task.inbound_order_number} · ${t("common.from", "From")}: ${task.source_barcode || "—"}`;
        helper = t("putaway.groupHelperSku", "SKU view");
      }

      if (!groups.has(groupKey)) {
        groups.set(groupKey, {
          key: groupKey,
          title,
          subtitle,
          helper,
          source: task.source_barcode,
          items: [],
          totalUnits: 0,
        });
      }
      const group = groups.get(groupKey)!;
      group.items.push(task);
      group.totalUnits += Number(task.quantity || 0);
    });

    groups.forEach((group) => {
      group.items.sort((a: any, b: any) => {
        const aPlanned = Boolean(batchAssignments[a.id]);
        const bPlanned = Boolean(batchAssignments[b.id]);
        if (aPlanned !== bPlanned) return aPlanned ? 1 : -1;
        const createdDiff = getTaskCreatedAt(a) - getTaskCreatedAt(b);
        if (createdDiff !== 0) return createdDiff;
        return String(a.sku_label || "").localeCompare(String(b.sku_label || ""));
      });
    });

    return Array.from(groups.values()).sort((a, b) => {
      const aUnplanned = a.items.some((task) => !batchAssignments[task.id]);
      const bUnplanned = b.items.some((task) => !batchAssignments[task.id]);
      if (aUnplanned !== bUnplanned) return aUnplanned ? -1 : 1;
      const aSelected = a.items.some((task) => selectedTaskSet.has(task.id));
      const bSelected = b.items.some((task) => selectedTaskSet.has(task.id));
      if (aSelected !== bSelected) return aSelected ? -1 : 1;
      const createdDiff = getTaskCreatedAt(a.items[0]) - getTaskCreatedAt(b.items[0]);
      if (createdDiff !== 0) return createdDiff;
      return a.title.localeCompare(b.title);
    });
  }, [batchAssignments, filteredTasks, selectedTaskSet, t, viewMode]);

  const activeLevelAssignmentMap = useMemo(() => {
    const map = new Map<string, any[]>();
    Object.entries(batchAssignments).forEach(([taskId, locationId]) => {
      const task = batchTaskMap.get(taskId);
      if (!task) return;
      if (!map.has(locationId)) map.set(locationId, []);
      map.get(locationId)!.push(task);
    });
    return map;
  }, [batchAssignments, batchTaskMap]);

  const activeRackLevelOccupancy = useMemo(() => {
    if (!activeRack) return [];
    return activeRack.levels.map((levelGroup: any) => {
      const units = levelGroup.locations.reduce((sum: number, location: any) => sum + inventoryContextSummary.slot(location.id).units, 0);
      const occupiedSlots = levelGroup.locations.filter((location: any) => inventoryContextSummary.slot(location.id).units > 0).length;
      return {
        level: levelGroup.level,
        units,
        occupiedSlots,
        totalSlots: levelGroup.locations.length,
      };
    });
  }, [activeRack, inventoryContextSummary]);

  const warehouseHeatmap = useMemo(
    () =>
      visualLocationTree.map((zone) => ({
        label: zone.zone,
        units: inventoryContextSummary.zone(zone.zone).units,
        occupiedCount: inventoryContextSummary.zone(zone.zone).occupiedCount,
      })),
    [inventoryContextSummary, visualLocationTree]
  );

  const activeZoneHeatmap = useMemo(
    () =>
      activeZone
        ? activeZone.aisles.map((aisle) => ({
            label: aisle.aisle,
            units: inventoryContextSummary.aisle(activeZone.zone, aisle.aisle).units,
            occupiedCount: inventoryContextSummary.aisle(activeZone.zone, aisle.aisle).occupiedCount,
          }))
        : [],
    [activeZone, inventoryContextSummary]
  );

  const activeAisleHeatmap = useMemo(
    () =>
      activeAisle
        ? activeAisle.racks.map((rack) => ({
            label: rack.rack,
            units: inventoryContextSummary.rack(selectedZoneKey || "", activeAisle.aisle, rack.rack).units,
            occupiedCount: inventoryContextSummary.rack(selectedZoneKey || "", activeAisle.aisle, rack.rack).occupiedCount,
          }))
        : [],
    [activeAisle, inventoryContextSummary, selectedZoneKey]
  );

  const pickerStep = selectedLevelKey ? 5 : selectedRackKey ? 4 : selectedAisleKey ? 3 : selectedZoneKey ? 2 : 1;

  const batchAssignedUnitCount = useMemo(
    () =>
      batchWorkspaceTasks
        .filter((task: any) => Boolean(batchAssignments[task.id]))
        .reduce((sum: number, task: any) => sum + Number(task.quantity || 0), 0),
    [batchAssignments, batchWorkspaceTasks]
  );

  const batchExceptionCount = useMemo(
    () =>
      batchWorkspaceTasks.filter(
        (task: any) => !batchAssignments[task.id] && !batchSuggestionMap.get(task.id)?.topSuggestion
      ).length,
    [batchAssignments, batchSuggestionMap, batchWorkspaceTasks]
  );

  const batchNeedsReviewCount = useMemo(
    () =>
      batchWorkspaceTasks.filter(
        (task: any) => !batchAssignments[task.id] && Boolean(batchSuggestionMap.get(task.id)?.topSuggestion)
      ).length,
    [batchAssignments, batchSuggestionMap, batchWorkspaceTasks]
  );

  const batchAssignmentProgress = batchUnitCount > 0 ? Math.round((batchAssignedUnitCount / batchUnitCount) * 100) : 0;

  const batchTopSuggestionUnitCount = useMemo(
    () =>
      batchWorkspaceTasks
        .filter((task: any) => Boolean(batchSuggestionMap.get(task.id)?.topSuggestion))
        .reduce((sum: number, task: any) => sum + Number(task.quantity || 0), 0),
    [batchSuggestionMap, batchWorkspaceTasks]
  );

  const batchRackUnitCount = useMemo(
    () =>
      batchWorkspaceTasks
        .filter((task: any) => Boolean(batchRackSuggestionMap.get(task.id)))
        .reduce((sum: number, task: any) => sum + Number(task.quantity || 0), 0),
    [batchRackSuggestionMap, batchWorkspaceTasks]
  );

  const searchScopedExecutionSummary = useMemo(() => {
    const summary = { human: 0, agv: 0, hybrid: 0 };
    searchScopedTasks.forEach((task: any) => {
      if (task.execution_mode === "agv") summary.agv += 1;
      else if (task.execution_mode === "hybrid") summary.hybrid += 1;
      else summary.human += 1;
    });
    return summary;
  }, [searchScopedTasks]);

  const tabSwitcher = (
    <div className="flex w-fit gap-1 rounded-2xl bg-[#ebe5db] p-1.5">
      {([
        ["tasks", t("putaway.allTasks", "All Tasks")],
        ["work", t("putaway.putawayWorkTab", "Putaway Work")],
      ] as const).map(([tab, label]) => (
        <button
          key={tab}
          type="button"
          onClick={() => setActiveWorkspaceTab(tab)}
          disabled={tab === "work" && !activeTask}
          className={`rounded-[1rem] px-4 py-2 text-sm font-medium transition-colors ${
            activeWorkspaceTab === tab
              ? "bg-white text-[#13212c] shadow-sm"
              : "text-[#6c7a86] hover:text-[#13212c] disabled:cursor-not-allowed disabled:opacity-50"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );

  const activeTaskExternalCodeSummary = activeTask ? getTaskExternalCodeSummary(activeTask) : "";
  const activeTaskHasSecondaryDetails = Boolean(
    activeTaskExternalCodeSummary ||
      activeTask?.handling_unit_status ||
      activeTask?.package_count != null ||
      activeTask?.measured_weight_kg != null
  );
  const putawayMobileSteps: MobileFlowStepItem[] = [
    {
      key: "choose",
      number: "1",
      label: t("putaway.mobileStepChoose", "Choose"),
      status: activeTask ? "done" : "active",
    },
    {
      key: "slot",
      number: "2",
      label: t("putaway.mobileStepSlot", "Slot"),
      status: selectedDestinationId ? "done" : activeTask ? "active" : "pending",
    },
    {
      key: "confirm",
      number: "3",
      label: t("putaway.mobileStepConfirm", "Confirm"),
      status: selectedDestinationId ? "active" : "pending",
    },
  ];
  const putawayMobileTitle = selectedDestinationId
    ? t("putaway.mobileStepTitleConfirm", "Step 3 · Confirm final storage")
    : t("putaway.mobileStepTitleSlot", "Step 2 · Choose a final slot");
  const putawayMobileHint = selectedDestinationId
    ? t("putaway.mobileStepHintConfirm", "Review the destination and quantity before moving this task out of staging.")
    : t("putaway.mobileStepHintSlot", "Pick one suggested slot or choose a zone, aisle, rack, and level below.");
  const primaryMobileSuggestion = enrichedSuggestions[0] || null;
  const secondaryMobileSuggestions = enrichedSuggestions.slice(1);
  const mobileConfirmBlockedReason = !activeTask
    ? ""
    : !selectedDestinationId
      ? primaryMobileSuggestion
        ? t("putaway.mobileBlockedChooseSuggestedSlot", "Choose the recommended final slot before confirming.")
        : t("putaway.mobileBlockedChooseManualSlot", "No recommended slot is available. Choose a final slot manually.")
      : destinationPlacementBlocked
        ? destinationPlacementIssues[0]?.title || t("putaway.destinationBlockedTitle", "Destination needs review before confirmation")
        : !splitAllocationPreview.isValid
          ? t("putaway.mobileBlockedFixQuantity", "Fix the quantity plan so assigned units match the task total.")
          : !mobileDestinationConfirmed
            ? t("putaway.mobileBlockedScanSlot", "Scan or type the final slot code to confirm the physical location.")
            : "";
  const mobileConfirmNextStep = !activeTask
    ? ""
    : !selectedDestinationId
      ? primaryMobileSuggestion
        ? t("putaway.mobileNextUseSuggestion", "Use the recommended slot, or open manual selection.")
        : t("putaway.mobileNextChooseManual", "Open manual selection and pick zone, aisle, rack, level, and position.")
      : destinationPlacementBlocked
        ? t("putaway.mobileNextChooseAnotherSlot", "Choose another slot that follows warehouse policy.")
        : !splitAllocationPreview.isValid
          ? t("putaway.mobileNextFixQuantity", "Open split plan and correct the quantities.")
          : !mobileDestinationConfirmed
            ? t("putaway.mobileNextScanSlot", "Use the scanner field on this screen.")
            : t("putaway.mobileNextConfirmReady", "Confirm putaway now.");
  const mobilePrimaryActionLabel = !selectedDestinationId && primaryMobileSuggestion
    ? t("putaway.mobileUseRecommendedSlot", "Use recommended slot")
    : confirmMutation.isPending
      ? t("putaway.confirming", "Confirming...")
      : t("putaway.confirmPutaway", "Confirm putaway");
  const putawayMobilePath =
    confirmRecoveryState || destinationPlacementBlocked
      ? "exception"
      : !selectedDestinationId && primaryMobileSuggestion
        ? "recommended"
        : "manual";
  const mobilePrimaryActionDisabled =
    confirmMutation.isPending ||
    (selectedDestinationId
      ? !splitAllocationPreview.isValid || destinationPlacementBlocked || !mobileDestinationConfirmed
      : !primaryMobileSuggestion);
  const remainingPutawayAfterSuccess = Math.max(0, pendingTasksCount - 1);
  const putawaySuccessNextStep =
    remainingPutawayAfterSuccess > 0
      ? t("putaway.successNextTask", "Next: open the next putaway task.")
      : t("putaway.successNextInventory", "Next: review inventory or return to the inbound handoff.");
  const handleMobilePrimaryAction = () => {
    if (!selectedDestinationId && primaryMobileSuggestion) {
      handleUseSuggestion(primaryMobileSuggestion.location_id);
      return;
    }
    handleConfirm();
  };

  return (
    <div className="space-y-6">
      <div className={`${activeWorkspaceTab === "work" && activeTask ? "hidden md:flex" : "flex"} flex-col gap-3 lg:flex-row lg:items-end lg:justify-between`}>
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[#7f8d98]">{t("putaway.eyebrow", "Storage execution")}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{t("putaway.title", "Putaway")}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill as="span" tone="warning">
            {t("putaway.pendingUnits", "{count} units waiting", { count: pendingUnits })}
          </Pill>
          <Pill as="span">
            {t("putaway.pendingTasksChip", "{count} tasks open", { count: pendingTasksCount })}
          </Pill>
          {focusContext?.handlingUnitCode ? (
            <Pill as="span" tone="active">
              {focusContext.handlingUnitCode}
            </Pill>
          ) : null}
        </div>
      </div>

      {confirmMutation.data?.success && lastCompletedPutaway ? (
        <div
          ref={successNoticeRef}
          className="rounded-[1.4rem] border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-800"
          data-testid="putaway-success-next-step"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="font-semibold text-emerald-900">
                {lastCompletedPutaway.destinationCount > 1
                  ? t(
                      "putaway.successSplit",
                      "Putaway confirmed. Inventory has been split into the selected final storage locations.",
                    )
                  : t("putaway.success", "Putaway confirmed. Inventory has moved into the final location.")}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-emerald-200/80 bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-800">
                  {lastCompletedPutaway.handlingUnitCode
                    ? t("putaway.successUnitComplete", "Unit {unit} completed", {
                        unit: lastCompletedPutaway.handlingUnitCode,
                      })
                    : t("putaway.successTaskComplete", "Task completed")}
                </span>
                {lastCompletedPutaway.destinationCount > 1 ? (
                  <span className="rounded-full border border-emerald-200/80 bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-800">
                    {t("putaway.splitResult", "Split result")}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-6 text-emerald-800">{putawaySuccessNextStep}</p>
            </div>
            <div className="grid gap-2 sm:flex sm:flex-wrap">
              {remainingPutawayAfterSuccess > 0 ? (
                <button
                  type="button"
                  onClick={openFirstPutawayTask}
                  className="min-h-[44px] rounded-full border border-emerald-300 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-800"
                >
                  {t("putaway.successOpenNextTaskAction", "Open next task")}
                </button>
              ) : null}
              {focusContext?.orderId ? (
                <Link
                  to={`/receiving/orders/${focusContext.orderId}`}
                  className="min-h-[44px] rounded-full border border-emerald-300 bg-white px-3 py-2 text-center text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-800"
                >
                  {t("putaway.successBackToInboundAction", "Back to inbound detail")}
                </Link>
              ) : null}
            </div>
          </div>
          {Array.isArray(confirmMutation.data?.allocations) && confirmMutation.data.allocations.length > 1 ? (
            <div className="mt-3 grid gap-2 lg:grid-cols-2">
              {confirmMutation.data.allocations.map((allocation: any) => (
                <div
                  key={`${allocation.location_id}-${allocation.quantity}`}
                  className="flex items-center justify-between gap-3 rounded-[0.9rem] border border-emerald-200/80 bg-white/70 px-3 py-2"
                >
                  <div>
                    <p className="font-semibold text-emerald-900">{allocation.location_barcode}</p>
                    <p className="mt-1 text-xs text-emerald-700">{describeLocationBarcode(allocation.location_barcode, t)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-emerald-700">{t("common.qty", "Qty")}</p>
                    <p className="mt-1 font-semibold text-emerald-900">{allocation.quantity}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          <section className={`${activeWorkspaceTab === "work" && activeTask ? "hidden md:block" : "block"} overflow-hidden rounded-[1.85rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_58%,#253847_100%)] p-5 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]`}>
            <div className="max-w-3xl">
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">
                {t("putaway.workEyebrow", "Putaway work")}
              </p>
              <h2 className="mt-3 text-xl font-semibold tracking-[-0.03em] sm:text-2xl">
                {t("putaway.workTitle", "Move staged stock into final storage.")}
              </h2>
              <p className="mt-3 hidden text-sm leading-6 text-[#dbe4ea] sm:block">
                {t(
                  "putaway.workBody",
                  "Start with route exceptions, then continue the oldest staging work or build a batch when several tasks share the same source.",
                )}
              </p>
            </div>

            <div className="mt-5 hidden flex-wrap gap-2 md:flex">
              <Pill as="span" className="border-white/12 bg-white/10 text-[#dbe4ea]">
                {t("putaway.pendingUnits", "{count} units waiting", { count: pendingUnits })}
              </Pill>
              <Pill as="span" className="border-white/12 bg-white/10 text-[#dbe4ea]">
                {t("putaway.pendingTasksChip", "{count} tasks open", { count: pendingTasksCount })}
              </Pill>
              <Pill as="span" className="border-white/12 bg-white/10 text-[#dbe4ea]">
                {t("putaway.routeExceptionCount", "{count} route exceptions", { count: routeExceptionTasks.length })}
              </Pill>
              <Pill as="span" className="border-white/12 bg-white/10 text-[#dbe4ea]">
                {t("putaway.batchOpportunityCount", "{count} batch candidates", { count: batchCandidateSummary.taskCount })}
              </Pill>
            </div>
          </section>

          <section className="space-y-4 rounded-[1.7rem] border border-[#13212c]/8 bg-white/68 p-4 shadow-[0_18px_44px_rgba(19,33,44,0.05)]">
            <div className={`${activeWorkspaceTab === "work" && activeTask ? "hidden md:flex" : "flex"} flex-wrap items-center justify-between gap-3`}>
              {tabSwitcher}
              <div className="hidden flex-wrap items-center gap-2 text-xs text-[#61717d] md:flex">
                <span className="rounded-full border border-[#13212c]/8 bg-white/80 px-3 py-1.5 font-semibold uppercase tracking-[0.14em] text-[#5c6974]">
                  {t("putaway.pendingTasksChip", "{count} tasks open", { count: pendingTasksCount })}
                </span>
                <span className="rounded-full border border-[#13212c]/8 bg-white/80 px-3 py-1.5 font-semibold uppercase tracking-[0.14em] text-[#5c6974]">
                  {t("putaway.pendingUnits", "{count} units waiting", { count: pendingUnits })}
                </span>
              </div>
            </div>

            {activeWorkspaceTab === "tasks" ? (
        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/85 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">{t("putaway.taskList", "Pending putaway tasks")}</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-[#13212c]">{t("putaway.taskListTitle", "Continue putaway")}</h2>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                {filteredTasks.length}
              </span>
              {filteredTasks.length > 0 ? (
                <>
                  <button
                    type="button"
                    onClick={handleSelectAllTasks}
                    className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                  >
                    {visibleOrderCount > 1
                      ? t("putaway.batchSelectCurrentOrder", "Select current order")
                      : t("putaway.batchSelectAll", "Select all")}
                  </button>
                  {selectedTaskIds.length > 0 ? (
                    <button
                      type="button"
                      onClick={handleClearSelection}
                      className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                    >
                      {t("putaway.batchClear", "Clear")}
                    </button>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>

          <div className="mt-4 hidden flex-wrap items-start gap-3 md:flex">
            {focusContext ? (
              <div className="w-full rounded-[1rem] border border-[#4977c8]/20 bg-[#eff5ff] px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#4977c8]">
                      {t("putaway.focusedInboundEyebrow", "Focused from inbound detail")}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-[#13212c]">
                      {focusContext.handlingUnitCode || focusContext.orderNumber || focusContext.referenceNumber || "—"}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {focusContext.orderId ? (
                      <Link
                        to={`/receiving/orders/${focusContext.orderId}`}
                        className="rounded-full border border-[#4977c8]/20 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#4977c8]"
                      >
                        {t("putaway.backToInboundDetail", "Back to inbound detail")}
                      </Link>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => {
                        setFocusContext(null);
                        setTaskSearch("");
                      }}
                      className="rounded-full border border-[#4977c8]/20 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#4977c8]"
                    >
                      {t("putaway.clearInboundFocus", "Clear focus")}
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
            <label className="min-w-[220px] flex-1 rounded-[1rem] border border-[#13212c]/10 bg-[#fbf8f2] px-4 py-3">
              <span className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("putaway.filterSearchLabel", "Find a task")}
              </span>
              <input
                value={taskSearch}
                onChange={(event) => setTaskSearch(event.target.value)}
                placeholder={t("putaway.filterSearchPlaceholder", "Search by HU, inbound, SKU, source, or external code")}
                className="mt-2 w-full border-0 bg-transparent p-0 text-sm text-[#13212c] outline-none placeholder:text-[#9aa7b1]"
              />
            </label>
            <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("putaway.filterShowingSummary", "{visible} of {total} tasks", {
                visible: filteredTasks.length,
                total: pendingTasksCount,
              })}
            </span>
          </div>

          <details
            className="mt-4 rounded-[1.1rem] border border-[#13212c]/8 bg-[#fbf8f2] p-3 md:hidden"
            data-testid="putaway-mobile-queue-options"
          >
            <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
              {t("putaway.mobileQueueOptions", "View counts or change queue")}
            </summary>
            <div className="mt-3 space-y-3">
              <label className="block rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3">
                <span className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("putaway.filterSearchLabel", "Find a task")}
                </span>
                <input
                  value={taskSearch}
                  onChange={(event) => setTaskSearch(event.target.value)}
                  placeholder={t("putaway.filterSearchPlaceholder", "Search by HU, inbound, SKU, source, or external code")}
                  className="mt-2 w-full border-0 bg-transparent p-0 text-sm text-[#13212c] outline-none placeholder:text-[#9aa7b1]"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                {([
                  ["handling_unit", t("putaway.view.handlingUnit", "By package / pallet")],
                  ["inbound_order", t("putaway.view.inboundOrder", "By inbound order")],
                  ["sku", t("putaway.view.sku", "By SKU")],
                ] as const).map(([mode, label]) => (
                  <button
                    key={`mobile-${mode}`}
                    type="button"
                    onClick={() => setViewMode(mode)}
                    className={`min-h-[44px] rounded-xl border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition ${
                      viewMode === mode
                        ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                        : "border-[#13212c]/10 bg-white text-[#61717d] hover:bg-[#fffdfa]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {([
                  ["all", t("putaway.executionFilter.all", "All routes"), searchScopedTasks.length],
                  ["human", t("putaway.executionMode.human", "Worker"), searchScopedExecutionSummary.human],
                  ["agv", t("putaway.executionMode.agv", "AGV"), searchScopedExecutionSummary.agv],
                  ["hybrid", t("putaway.executionMode.hybrid", "Hybrid"), searchScopedExecutionSummary.hybrid],
                ] as const).map(([mode, label, count]) => (
                  <button
                    key={`mobile-exec-${mode}`}
                    type="button"
                    onClick={() => setExecutionFilter(mode)}
                    className={`min-h-[44px] rounded-xl border px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.12em] transition ${
                      executionFilter === mode
                        ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                        : "border-[#13212c]/10 bg-white text-[#61717d] hover:bg-[#fffdfa]"
                    }`}
                  >
                    <span>{label}</span>
                    <span className="ml-2">{count}</span>
                  </button>
                ))}
              </div>
            </div>
          </details>

          <div className="mt-4 hidden flex-wrap gap-2 md:flex">
            {([
              ["handling_unit", t("putaway.view.handlingUnit", "By package / pallet")],
              ["inbound_order", t("putaway.view.inboundOrder", "By inbound order")],
              ["sku", t("putaway.view.sku", "By SKU")],
            ] as const).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] transition ${
                  viewMode === mode
                    ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                    : "border-[#13212c]/10 bg-white text-[#61717d] hover:bg-[#fffdfa]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mt-3 hidden flex-wrap gap-2 md:flex">
            {([
              ["all", t("putaway.executionFilter.all", "All routes"), searchScopedTasks.length],
              ["human", t("putaway.executionMode.human", "Worker"), searchScopedExecutionSummary.human],
              ["agv", t("putaway.executionMode.agv", "AGV"), searchScopedExecutionSummary.agv],
              ["hybrid", t("putaway.executionMode.hybrid", "Hybrid"), searchScopedExecutionSummary.hybrid],
            ] as const).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setExecutionFilter(mode)}
                className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] transition ${
                  executionFilter === mode
                    ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                    : "border-[#13212c]/10 bg-white text-[#61717d] hover:bg-[#fffdfa]"
                }`}
              >
                <span>{label}</span>
                <span
                  className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    executionFilter === mode ? "bg-white/12 text-[#f4efe8]" : "bg-[#f7f4ee] text-[#13212c]"
                  }`}
                >
                  {mode === "all" ? searchScopedTasks.length : mode === "human" ? searchScopedExecutionSummary.human : mode === "agv" ? searchScopedExecutionSummary.agv : searchScopedExecutionSummary.hybrid}
                </span>
              </button>
            ))}
          </div>

          <div className="mt-4 space-y-3">
            {tasksLoading ? (
              <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-8 text-center text-sm text-[#61717d]">
                {t("common.loading", "Loading...")}
              </div>
            ) : enrichedTasks.length === 0 ? (
              <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-8 text-center">
                <p className="text-sm font-semibold text-[#13212c]">{t("putaway.emptyTitle", "No putaway tasks waiting")}</p>
                <p className="mt-2 text-sm leading-6 text-[#61717d]">
                  {t("putaway.emptyBody", "Complete receiving first, then come back here when stock is ready to leave staging.")}
                </p>
              </div>
            ) : filteredTasks.length === 0 ? (
              <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-8 text-center">
                <p className="text-sm font-semibold text-[#13212c]">{t("putaway.filterEmptyTitle", "No tasks match this filter")}</p>
                <p className="mt-2 text-sm leading-6 text-[#61717d]">
                  {t("putaway.filterEmptyBody", "Clear the search or switch the execution filter to bring more staging work back into view.")}
                </p>
              </div>
            ) : (
              taskGroups.map((group) => {
                const groupSelectedCount = group.items.filter((task) => selectedTaskSet.has(task.id)).length;
                const groupPlannedCount = group.items.filter((task) => batchAssignments[task.id]).length;
                const groupActive = group.items.some((task) => activeTask?.id === task.id);
                const groupNumberMeta = taskGroupNumberMeta(group.items);
                const representativeTask = group.items[0];
                const groupPrimaryTitle =
                  group.items.length === 1 ? representativeTask.sku_label || group.title : group.title;
                const groupSecondaryLabel =
                  group.items.length === 1
                    ? representativeTask.handling_unit_code
                      ? `${t("putaway.handlingUnitLabel", "HU")}: ${representativeTask.handling_unit_code}`
                      : `${t("putaway.inboundLabel", "Inbound")}: ${representativeTask.inbound_order_number}`
                    : group.subtitle;
                const groupAgeLabel = getTaskAgeLabel(representativeTask, t);
                const openGroupTask = () => focusTask(representativeTask.id, "single");

                return (
                  <div
                    key={group.key}
                    role="button"
                    tabIndex={0}
                    onClick={openGroupTask}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openGroupTask();
                      }
                    }}
                    className={`cursor-pointer rounded-[1.35rem] border px-4 py-4 transition hover:border-[#13212c]/24 hover:bg-[#fffdfa] ${
                      groupActive
                        ? "border-[#13212c] bg-[#fbf8f2]"
                        : "border-[#13212c]/8 bg-[#fffdfa]"
                    }`}
                  >
                    <div className="flex items-stretch gap-3">
                      <div
                        className={`flex w-14 shrink-0 flex-col items-center justify-start rounded-[1rem] border px-2 py-3 text-center ${
                          groupActive
                            ? "border-[#13212c] bg-white text-[#13212c]"
                            : "border-[#13212c]/10 bg-[#f7f4ee] text-[#13212c]"
                        }`}
                        aria-label={groupNumberMeta.ariaLabel}
                      >
                        <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">
                          {groupNumberMeta.eyebrow}
                        </span>
                        <span className="mt-1 text-lg font-semibold leading-none tracking-[0]">
                          {groupNumberMeta.value}
                        </span>
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="break-words text-sm font-semibold text-[#13212c]">{groupPrimaryTitle}</p>
                            <p className="mt-1 break-words text-xs uppercase tracking-[0.14em] text-[#7f8d98]">{groupSecondaryLabel}</p>
                          </div>
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                              {t("common.qty", "Qty")}: {group.totalUnits}
                            </span>
                            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                              {groupAgeLabel}
                            </span>
                            <StatusBadge status={representativeTask.status} />
                            {groupPlannedCount > 0 ? (
                              <span className="rounded-full border border-[#87c6a1]/24 bg-[#eef9f1] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#356b4c]">
                                {t("putaway.batchAssigned", "Placed on board")}: {groupPlannedCount}/{group.items.length}
                              </span>
                            ) : null}
                            {group.items.length > 1 ? (
                              <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                                {t("putaway.groupSummary", "{count} tasks · {units} units waiting", {
                                  count: group.items.length,
                                  units: group.totalUnits,
                                })}
                              </span>
                            ) : null}
                            {group.items.length > 1 ? (
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleSelectSourceGroup(group.items.map((task) => task.id));
                                }}
                                className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                              >
                                {t("putaway.batchSelectTasks", "Select tasks")}
                              </button>
                            ) : null}
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                openGroupTask();
                              }}
                              className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                            >
                              {t("common.open", "Open")}
                            </button>
                          </div>
                        </div>

                        {group.items.length > 1 ? (
                          <div className="mt-4 space-y-2">
                            {group.items.map((task: any) => (
                            <div
                              key={task.id}
                              role="button"
                              tabIndex={0}
                              onClick={() => {
                                focusTask(task.id, "single");
                              }}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") {
                                  event.preventDefault();
                                  focusTask(task.id, "single");
                                }
                              }}
                              className={`w-full rounded-[1rem] border px-3 py-3 text-left transition ${
                                activeTask?.id === task.id
                                  ? "border-[#13212c] bg-[#fbf8f2] shadow-[0_0_0_1px_rgba(19,33,44,0.06)]"
                                  : "border-[#13212c]/8 bg-[#fbf8f2] hover:border-[#13212c]/14 hover:bg-white"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    {group.items.length > 1 ? (
                                      <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                                        {taskNumberLabel(task)}
                                      </span>
                                    ) : null}
                                    <p className="text-sm font-semibold text-[#13212c]">{task.sku_label}</p>
                                  </div>
                              <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7f8d98]">
                                {(task.handling_unit_code
                                  ? `${t("putaway.handlingUnitLabel", "HU")}: ${task.handling_unit_code}`
                                  : task.inbound_order_number)}
                              </p>
                              <p className="mt-2 text-sm text-[#61717d]">
                                {t("putaway.inboundLabel", "Inbound")}: {task.inbound_order_number}
                              </p>
                              <p className="mt-1 text-[11px] uppercase tracking-[0.12em] text-[#7f8d98]">
                                {getTaskAgeLabel(task, t)}
                              </p>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <span
                                  className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${getExecutionModeTone(task.execution_mode, activeTask?.id === task.id)}`}
                                >
                                  {getExecutionModeLabel(task.execution_mode, t)}
                                </span>
                                <span
                                  className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[10px] font-medium text-[#61717d]"
                                >
                                  {t("putaway.sourceLabelShort", "Source")}: {task.source_barcode}
                                </span>
                                <span
                                  className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[10px] font-medium text-[#61717d]"
                                >
                                  {t("common.qty", "Qty")}: {task.quantity}
                                </span>
                                {task.package_count != null ? (
                                  <span
                                    className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[10px] font-medium text-[#61717d]"
                                  >
                                    {t("putaway.packageCountLabel", "Packages")}: {task.package_count}
                                  </span>
                                ) : null}
                                {task.measured_weight_kg != null ? (
                                  <span
                                    className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[10px] font-medium text-[#61717d]"
                                  >
                                    {t("putaway.measuredWeightLabel", "Measured weight")}: {task.measured_weight_kg} kg
                                  </span>
                                ) : null}
                                {task.handling_unit_status ? (
                                  <span
                                    className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[10px] font-medium text-[#61717d]"
                                  >
                                    {getHandlingUnitStatusLabel(task.handling_unit_status, t)}
                                  </span>
                                ) : null}
                              </div>
                              <p className="mt-2 text-xs text-[#61717d]">
                                {getExecutionReasonLabel(task.execution_reason, t)}
                              </p>
                              {getTaskExternalCodeSummary(task) ? (
                                <p className="mt-1 text-[11px] text-[#7f8d98]">
                                  {getTaskExternalCodeSummary(task)}
                                </p>
                              ) : null}
                            </div>
                            <div className="flex items-center gap-2">
                              {batchAssignments[task.id] ? (
                                <span className="rounded-full border border-[#87c6a1]/24 bg-[#eef9f1] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#356b4c]">
                                  {t("putaway.planned", "Planned")}
                                </span>
                              ) : null}
                              <StatusBadge status={task.status} />
                              {group.items.length > 1 ? (
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    toggleTaskSelection(task.id);
                                  }}
                                  className={`inline-flex h-9 w-9 items-center justify-center rounded-full border shadow-sm transition ${
                                    selectedTaskSet.has(task.id)
                                      ? "border-[#f7bf45]/28 bg-[#fff4da] text-[#8a6511] shadow-[0_10px_24px_rgba(209,144,9,0.12)]"
                                      : "border-[#13212c]/10 bg-white text-[#61717d] hover:border-[#13212c]/18 hover:bg-[#fffdfa] hover:text-[#13212c]"
                                  }`}
                                  aria-pressed={selectedTaskSet.has(task.id)}
                                  aria-label={selectedTaskSet.has(task.id) ? t("common.selected", "Selected") : t("common.select", "Select")}
                                  title={selectedTaskSet.has(task.id) ? t("common.selected", "Selected") : t("common.select", "Select")}
                                >
                                  <span
                                    className={`inline-flex h-4 w-4 items-center justify-center rounded-full border transition ${
                                    selectedTaskSet.has(task.id)
                                      ? "border-[#f7bf45]/30 bg-[#f7bf45] text-[#13212c]"
                                      : "border-[#13212c]/16 bg-transparent text-transparent"
                                  }`}
                                  >
                                    <Check size={10} strokeWidth={3} />
                                  </span>
                                </button>
                              ) : null}
                            </div>
                              </div>
                            </div>
                            ))}
                          </div>
                        ) : null}

                        {groupSelectedCount > 0 ? (
                          <p className="mt-3 text-xs leading-5 text-[#61717d]">
                            {groupSelectedCount === 1
                              ? t("putaway.groupSelectionHintSingle", "This task is selected. Choose a final slot or use the suggested location.")
                              : t("putaway.groupSelectionHint", "{count} tasks selected. Use system planning, or click one slot to place them across the current level.", {
                                  count: groupSelectedCount,
                                })}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>
            ) : (
        <section className="rounded-[2rem] border border-[#13212c]/10 bg-white/85 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
          {showBatchWorkspace ? (
            <>
            <details className="mb-4 rounded-[1.2rem] border border-[#13212c]/8 bg-[#fbf8f2] p-3 md:hidden">
              <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                {t("putaway.mobileBatchPlanToggle", "Batch plan and selected tasks")}
              </summary>
              <div className="mt-3 space-y-3">
                <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-3 py-3">
                  <p className="text-xs font-semibold text-[#13212c]">
                    {t("putaway.batchSelected", "{count} tasks selected", { count: batchWorkspaceTasks.length })}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[#61717d]">
                    {t("putaway.batchSummary", "{units} units across {skus} SKUs", {
                      units: batchUnitCount,
                      skus: batchSkuCount,
                    })}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleAutoPlanBatch}
                  disabled={batchReadyCount === 0}
                  className="min-h-[44px] w-full rounded-[1rem] bg-[#13212c] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t("putaway.batchConfirm", "Apply system suggestions")}
                </button>
                <button
                  type="button"
                  onClick={handleClearSelection}
                  className="min-h-[44px] w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#13212c]"
                >
                  {t("putaway.mobileBatchWorkSingleTask", "Work one task instead")}
                </button>
              </div>
            </details>
            <div className="mb-6 hidden rounded-[1.5rem] border border-[#13212c]/8 bg-[#fbf8f2] p-5 md:block">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">
                    {t("putaway.batchTitle", "Batch putaway")}
                  </p>
                  <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-[#13212c]">
                    {t("putaway.batchTitleBody", "Review selected putaway work")}
                  </h3>
                </div>
                <div className="rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-3">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("putaway.batchSelected", "{count} tasks selected", { count: batchWorkspaceTasks.length })}
                  </p>
                  <p className="mt-2 text-sm text-[#61717d]">
                    {t("putaway.batchSummary", "{units} units across {skus} SKUs", {
                      units: batchUnitCount,
                      skus: batchSkuCount,
                    })}
                  </p>
                </div>
              </div>

              <div className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3">
                <div className="flex flex-wrap items-center gap-3 text-sm text-[#61717d]">
                  <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 font-semibold text-[#13212c]">
                    {t("putaway.batchSelectedShort", "Selected tasks")}: {batchWorkspaceTasks.length}
                  </span>
                  <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 font-semibold text-[#13212c]">
                    {t("putaway.batchUnits", "Units in batch")}: {batchUnitCount}
                  </span>
                  <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 font-semibold text-[#13212c]">
                    {t("putaway.batchReady", "Ready with top suggestion")}: {batchReadyCount}
                  </span>
                </div>
              </div>

              <div className="mt-4 rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                      {t("putaway.batchLiveStatus", "Live batch status")}
                    </p>
                    <h4 className="mt-2 text-lg font-semibold text-[#13212c]">
                      {t("putaway.batchProgressTitle", "Assigned {assigned}/{total} units before execution", {
                        assigned: batchAssignedUnitCount,
                        total: batchUnitCount,
                      })}
                    </h4>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div className="rounded-[1rem] border border-[#13212c]/10 bg-[#fbf8f2] px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">{t("putaway.batchNeedsReview", "Needs review")}</p>
                      <p className="mt-2 text-xl font-semibold text-[#13212c]">{batchNeedsReviewCount}</p>
                    </div>
                    <div className="rounded-[1rem] border border-[#13212c]/10 bg-[#fbf8f2] px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">{t("putaway.batchExceptions", "Exceptions")}</p>
                      <p className="mt-2 text-xl font-semibold text-[#13212c]">{batchExceptionCount}</p>
                    </div>
                  </div>
                </div>
                <div className="mt-4">
                  <div className="flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                    <span>{t("putaway.batchProgress", "Assignment progress")}</span>
                    <span>{batchAssignmentProgress}%</span>
                  </div>
                  <div className="mt-2 h-3 overflow-hidden rounded-full bg-[#ece5da]">
                    <div
                      className="h-full rounded-full bg-[linear-gradient(90deg,#13212c_0%,#4977c8_55%,#87c6a1_100%)]"
                      style={{ width: `${batchAssignmentProgress}%` }}
                    />
                  </div>
                </div>

              </div>

              <div className="mt-4 rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                      {t("putaway.batchBoard", "Visual batch board")}
                    </p>
                    <h4 className="mt-2 text-lg font-semibold text-[#13212c]">
                      {t("putaway.batchBoardTitle", "Compare staging now vs. planned rack outcome")}
                    </h4>
                  </div>
                  <div className="rounded-[1rem] border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                      {t("putaway.batchAssigned", "Placed on board")}
                    </p>
                    <p className="mt-2 text-xl font-semibold text-[#13212c]">{batchAssignedCount}</p>
                  </div>
                </div>

                <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
                  <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4">
                    <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                      {t("putaway.batchBefore", "Before putaway")}
                    </p>
                    <div className="mt-4 space-y-3">
                      {batchSourceGroups.length === 0 ? (
                        <div className="space-y-3 rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-4">
                          <div>
                            <p className="text-sm font-semibold text-[#13212c]">
                              {t("putaway.batchBeforeReadyTitle", "This staging group is already planned on the board.")}
                            </p>
                          </div>
                          <div className="grid gap-3 sm:grid-cols-2">
                            <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-3">
                              <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                                {t("putaway.batchAssigned", "Placed on board")}
                              </p>
                              <p className="mt-2 text-xl font-semibold text-[#13212c]">{batchAssignedCount}</p>
                              <p className="mt-1 text-xs leading-5 text-[#61717d]">
                                {t("putaway.batchAssignedUnits", "{count} units already have a planned slot.", {
                                  count: batchAssignedUnitCount,
                                })}
                              </p>
                            </div>
                            <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-3">
                              <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                                {t("putaway.batchNeedsReview", "Needs review")}
                              </p>
                              <p className="mt-2 text-xl font-semibold text-[#13212c]">{batchNeedsReviewCount + batchExceptionCount}</p>
                            </div>
                          </div>
                          <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#fff7e8] px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.14em] text-[#8a6511]">
                              {t("putaway.batchNextAction", "Next best action")}
                            </p>
                            <p className="mt-2 text-sm font-semibold text-[#13212c]">
                              {batchExceptionCount > 0 || batchNeedsReviewCount > 0
                                ? t("putaway.batchNextReview", "Review the remaining exceptions, then confirm execution.")
                                : t("putaway.batchNextConfirm", "Everything is planned. You can confirm execution now.")}
                            </p>
                          </div>
                          {plannedBatchSourceGroups.map((group) => (
                            <div key={`planned-source-${group.source}`} className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-3">
                              <div className="flex items-center justify-between gap-3">
                                <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                                  {t("common.from", "From")}: {group.source}
                                </p>
                                <div className="flex items-center gap-2">
                                  {group.items.length > 1 ? (
                                    <button
                                      type="button"
                                      onClick={() => handleSelectSourceGroup(group.items.map((task: any) => task.id))}
                                      className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                                    >
                                      {t("putaway.batchSelectTasks", "Select tasks")}
                                    </button>
                                  ) : null}
                                  <button
                                    type="button"
                                    onClick={() => group.items.forEach((task: any) => handleUnassignTask(task.id))}
                                    className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                                  >
                                    {t("putaway.batchUnassign", "Remove planned move")}
                                  </button>
                                </div>
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {group.items.map((task: any) => (
                                  <button
                                    key={`planned-board-task-${task.id}`}
                                    type="button"
                                    onClick={() => focusTask(task.id)}
                                    className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] transition ${
                                      selectedTaskId === task.id
                                        ? "border-[#13212c] bg-[#fffdfa] text-[#13212c] shadow-[0_0_0_2px_rgba(19,33,44,0.14)]"
                                        : "border-[#13212c]/10 bg-white text-[#13212c] hover:border-[#13212c]/18"
                                    }`}
                                  >
                                    <span>{taskNumberLabel(task)}</span>
                                    <span>{task.inbound_order_number}</span>
                                    <span className="opacity-70">{task.quantity}</span>
                                    <span className="rounded-full bg-[#eef9f1] px-2 py-0.5 text-[10px] text-[#356b4c]">
                                      {t("putaway.planned", "Planned")}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        batchSourceGroups.map((group) => (
                          <div key={`source-${group.source}`} className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                                {t("common.from", "From")}: {group.source}
                              </p>
                              {group.items.length > 1 ? (
                                <button
                                  type="button"
                                  onClick={() => handleSelectSourceGroup(group.items.map((task: any) => task.id))}
                                  className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-white"
                                >
                                  {t("putaway.batchSelectTasks", "Select tasks")}
                                </button>
                              ) : null}
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {group.items.map((task: any) => (
                                <button
                                  key={`board-task-${task.id}`}
                                  type="button"
                                  onClick={() => focusTask(task.id)}
                                  draggable
                                  onDragStart={() => setDraggedTaskId(task.id)}
                                  onDragEnd={() => setDraggedTaskId(null)}
                                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] transition ${
                                    selectedTaskId === task.id
                                      ? "border-[#13212c] bg-[#13212c] text-[#f4efe8] shadow-[0_10px_24px_rgba(19,33,44,0.14)]"
                                      : draggedTaskId === task.id
                                      ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                                      : "border-[#13212c]/10 bg-[#fffdfa] text-[#13212c] hover:border-[#13212c]/18"
                                  }`}
                                >
                                  <GripVertical size={12} />
                                  <span>{taskNumberLabel(task)}</span>
                                  <span>{task.inbound_order_number}</span>
                                  <span className="opacity-70">{task.quantity}</span>
                                </button>
                              ))}
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {group.items.map((task: any) => (
                                <span
                                  key={`board-task-label-${task.id}`}
                                  className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                                    selectedTaskId === task.id
                                      ? "border-[#13212c]/18 bg-[#fffdfa] text-[#13212c]"
                                      : "border-[#13212c]/8 bg-[#f7f4ee] text-[#61717d]"
                                  }`}
                                >
                                  {taskNumberLabel(task)} · {getInboundOrderTag(task.inbound_order_number, t)}
                                </span>
                              ))}
                            </div>
                            <p className="mt-3 text-xs leading-5 text-[#61717d]">
                              {t("putaway.batchChipHint", "Tip: drag one of these task chips into the slot board on the right.")}
                            </p>
                            <p className="mt-2 text-xs leading-5 text-[#61717d]">
                              {t("putaway.batchGroupHint", "For a full order or source group, select the whole group first and then click one slot to spread the tasks across that rack level.")}
                            </p>
                            <p className="mt-2 text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                              {t("putaway.demoInboundHint", "INB-PUT is a demo inbound order number for putaway testing.")}
                            </p>
                          </div>
                        ))
                      )}

                      <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                              {t("putaway.batchWarehouseHeatmap", "Warehouse heatmap")}
                            </p>
                          </div>
                          <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                            {warehouseMap.get(activeTask?.warehouse_id || "") || activeTask?.warehouse_label || "—"}
                          </span>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-3">
                          <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                              {t("putaway.batchHeatmapZones", "Zones")}
                            </p>
                            <MiniWarehouseStrip
                              segments={warehouseHeatmap.map((segment) => ({ label: segment.label, units: segment.units }))}
                            />
                            <div className="mt-3 space-y-2">
                              {warehouseHeatmap.map((segment) => (
                                <div key={`heat-zone-${segment.label}`} className="flex items-center justify-between gap-3 text-xs text-[#61717d]">
                                  <span>{t("putaway.visualZoneLabel", "Zone {zone}", { zone: segment.label })}</span>
                                  <span>{t("putaway.visualUnitsStoredShort", "{count} units", { count: segment.units })}</span>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                              {t("putaway.batchHeatmapAisles", "Focused zone aisles")}
                            </p>
                            {activeZoneHeatmap.length ? (
                              <>
                                <MiniWarehouseStrip
                                  segments={activeZoneHeatmap.map((segment) => ({ label: segment.label, units: segment.units }))}
                                />
                                <div className="mt-3 space-y-2">
                                  {activeZoneHeatmap.map((segment) => (
                                    <div key={`heat-aisle-${segment.label}`} className="flex items-center justify-between gap-3 text-xs text-[#61717d]">
                                      <span>{t("putaway.visualAisleLabel", "Zone {zone} / Aisle {aisle}", { zone: activeZone?.zone || "—", aisle: segment.label })}</span>
                                      <span>{t("putaway.visualOccupiedSlotsShort", "{count} slots used", { count: segment.occupiedCount })}</span>
                                    </div>
                                  ))}
                                </div>
                              </>
                            ) : (
                              <p className="mt-3 text-sm leading-6 text-[#61717d]">
                                {t("putaway.batchHeatmapChooseZone", "Choose a zone on the right to see aisle heat across that part of the warehouse.")}
                              </p>
                            )}
                          </div>

                          <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                              {t("putaway.batchHeatmapRacks", "Focused aisle racks")}
                            </p>
                            {activeAisleHeatmap.length ? (
                              <>
                                <MiniWarehouseStrip
                                  segments={activeAisleHeatmap.map((segment) => ({ label: segment.label, units: segment.units }))}
                                />
                                <div className="mt-3 space-y-2">
                                  {activeAisleHeatmap.map((segment) => (
                                    <div key={`heat-rack-${segment.label}`} className="flex items-center justify-between gap-3 text-xs text-[#61717d]">
                                      <span>{t("putaway.visualRackLabel", "Rack {rack}", { rack: segment.label })}</span>
                                      <span>{t("putaway.visualUnitsStoredShort", "{count} units", { count: segment.units })}</span>
                                    </div>
                                  ))}
                                </div>
                              </>
                            ) : (
                              <p className="mt-3 text-sm leading-6 text-[#61717d]">
                                {t("putaway.batchHeatmapChooseAisle", "Choose an aisle on the right to see which racks are already carrying the most stock.")}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fff7e8] px-4 py-4">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div>
                            <p className="text-[11px] uppercase tracking-[0.16em] text-[#8a6511]">
                              {t("putaway.executionStep3", "Step 3 · Plan this batch")}
                            </p>
                            <p className="mt-2 text-sm font-semibold text-[#13212c]">
                              {t("putaway.executionStep3Title", "Use system suggestions to place this batch first")}
                            </p>
                          </div>
                          <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                              {t("putaway.batchAssigned", "Placed on board")}
                            </p>
                            <p className="mt-2 text-lg font-semibold text-[#13212c]">{batchAssignedCount}</p>
                          </div>
                        </div>
                        <div className="mt-4">
                          <button
                            type="button"
                            onClick={handleAutoPlanBatch}
                            disabled={batchReadyCount === 0}
                            className="w-full rounded-[1.05rem] bg-[#13212c] px-4 py-4 text-left transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8]">
                              {t("putaway.batchConfirm", "Apply system suggestions")}
                            </p>
                          </button>
                        </div>
                        <div
                          ref={finalReviewRef}
                          className={`mt-4 rounded-[1rem] border px-4 py-4 transition ${highlightFinalReview ? "border-[#d19009] bg-[#fff8ea] shadow-[0_0_0_3px_rgba(209,144,9,0.10)]" : "border-[#13212c]/8 bg-white"}`}
                        >
                          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                            <div>
                              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                                {t("putaway.executionFinalTitle", "Final review")}
                              </p>
                              <p className="mt-2 text-sm font-semibold text-[#13212c]">
                                {t("putaway.executionFinalBody", "{count} tasks / {units} units are ready to be put away.", {
                                  count: batchAssignedCount,
                                  units: batchAssignedUnitCount,
                                })}
                              </p>
                              {planReviewNotice ? (
                                <p className="mt-2 text-xs font-medium leading-5 text-[#8a6511]">{planReviewNotice}</p>
                              ) : null}
                            </div>
                            <button
                              type="button"
                              onClick={handleBatchAssignedConfirm}
                              disabled={batchAssignedCount === 0 || batchConfirmMutation.isPending}
                              className="rounded-[1.05rem] bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {batchConfirmMutation.isPending
                                ? t("putaway.batchConfirming", "Confirming batch...")
                                : t("putaway.executionFinalConfirm", "Confirm putaway now")}
                            </button>
                          </div>
                          {batchAssignedCount > 0 ? (
                            <div className="mt-3 border-t border-[#13212c]/8 pt-3">
                              <button
                                type="button"
                                onClick={clearBatchPlannedAssignments}
                                className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-white"
                              >
                                {t("putaway.executionFinalClear", "Clear current plan")}
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>

                    </div>
                  </div>

                  <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4">
                    <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                      {t("putaway.batchAfter", "Planned after-state")}
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <SnapshotStat label={t("putaway.batchAssigned", "Placed on board")} value={batchAssignedCount} />
                      <SnapshotStat label={t("putaway.batchReady", "Ready with top suggestion")} value={batchReadyCount} />
                      <SnapshotStat label={t("putaway.batchRackReady", "Fit current rack")} value={batchRackReadyCount} />
                    </div>
                    <div className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                            {t("putaway.batchPlanner", "Batch rack planner")}
                          </p>
                        </div>
                        <div className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                          {t("putaway.visualStep", "Step {step} of 5", { step: pickerStep })}
                        </div>
                      </div>
                      <div className="mt-4 space-y-3">
                        <div className="grid gap-3 md:grid-cols-2">
                          <label className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">{t("putaway.visualSelectZone", "Zone")}</p>
                              <span className="rounded-full bg-[#f7f4ee] px-2.5 py-1 text-[11px] font-medium text-[#61717d]">
                                {visualLocationTree.length} {t("putaway.visualChoices", "choices")}
                              </span>
                            </div>
                            <div className="relative mt-3">
                              <select
                                value={selectedZoneKey}
                                onChange={(event) => handleChooseZone(event.target.value)}
                                className="h-12 w-full appearance-none rounded-[0.95rem] border border-[#13212c]/10 bg-[#fbf8f2] px-4 pr-10 text-[15px] font-semibold leading-none text-[#13212c] outline-none transition focus:border-[#13212c] focus:bg-white"
                              >
                                <option value="" disabled>
                                  {t("putaway.batchChooseZone", "Choose zone")}
                                </option>
                                {visualLocationTree.map((zone) => (
                                  <option key={`batch-zone-option-${zone.zone}`} value={zone.zone}>
                                    {t("putaway.visualZoneLabel", "Zone {zone}", { zone: zone.zone })}
                                  </option>
                                ))}
                              </select>
                              <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-[#61717d]">▾</span>
                            </div>
                            {selectedZoneKey ? (() => {
                              const zoneSummary = inventoryContextSummary.zone(selectedZoneKey);
                              return (
                                <div className="mt-3 rounded-[0.85rem] border border-[#13212c]/6 bg-[#f7f4ee] px-3 py-3">
                                  <div className="h-2 overflow-hidden rounded-full bg-[#ece5da]">
                                    <div className={`${occupancyTone(zoneSummary.units)} h-full rounded-full`} style={{ width: `${Math.max(zoneSummary.occupiedCount ? 14 : 8, Math.min(100, zoneSummary.occupiedCount * 12))}%` }} />
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-[#61717d]">
                                    {t("putaway.visualUnitsStoredShort", "{count} units", { count: zoneSummary.units })} · {t("putaway.visualOccupiedSlotsShort", "{count} slots used", { count: zoneSummary.occupiedCount })}
                                  </p>
                                </div>
                              );
                            })() : (
                              null
                            )}
                          </label>

                          <label className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">{t("putaway.visualAisle", "Aisle group")}</p>
                              <span className="rounded-full bg-[#f7f4ee] px-2.5 py-1 text-[11px] font-medium text-[#61717d]">
                                {(activeZone?.aisles || []).length} {t("putaway.visualChoices", "choices")}
                              </span>
                            </div>
                            <div className="relative mt-3">
                              <select
                                value={selectedAisleKey}
                                onChange={(event) => handleChooseAisle(event.target.value)}
                                disabled={!activeZone}
                                className="h-12 w-full appearance-none rounded-[0.95rem] border border-[#13212c]/10 bg-[#fbf8f2] px-4 pr-10 text-[15px] font-semibold leading-none text-[#13212c] outline-none transition focus:border-[#13212c] focus:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                <option value="" disabled>
                                  {t("putaway.batchChooseAisle", "Choose aisle")}
                                </option>
                                {(activeZone?.aisles || []).map((aisle) => (
                                  <option key={`batch-aisle-option-${aisle.aisle}`} value={aisle.aisle}>
                                    {t("putaway.visualAisleLabel", "Zone {zone} / Aisle {aisle}", {
                                      zone: selectedZoneKey || "—",
                                      aisle: aisle.aisle,
                                    })}
                                  </option>
                                ))}
                              </select>
                              <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-[#61717d]">▾</span>
                            </div>
                            {selectedAisleKey ? (() => {
                              const aisleSummary = inventoryContextSummary.aisle(selectedZoneKey || "", selectedAisleKey);
                              return (
                                <div className="mt-3 rounded-[0.85rem] border border-[#13212c]/6 bg-[#f7f4ee] px-3 py-3">
                                  <div className="h-2 overflow-hidden rounded-full bg-[#ece5da]">
                                    <div className={`${occupancyTone(aisleSummary.units)} h-full rounded-full`} style={{ width: `${Math.max(aisleSummary.occupiedCount ? 14 : 8, Math.min(100, aisleSummary.occupiedCount * 12))}%` }} />
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-[#61717d]">
                                    {t("putaway.visualUnitsStoredShort", "{count} units", { count: aisleSummary.units })} · {t("putaway.visualOccupiedSlotsShort", "{count} slots used", { count: aisleSummary.occupiedCount })}
                                  </p>
                                </div>
                              );
                            })() : (
                              null
                            )}
                          </label>

                          <label className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">{t("putaway.visualSelectRack", "Rack")}</p>
                              <span className="rounded-full bg-[#f7f4ee] px-2.5 py-1 text-[11px] font-medium text-[#61717d]">
                                {(activeAisle?.racks || []).length} {t("putaway.visualChoices", "choices")}
                              </span>
                            </div>
                            <div className="relative mt-3">
                              <select
                                value={selectedRackKey}
                                onChange={(event) => handleChooseRack(event.target.value)}
                                disabled={!activeAisle}
                                className="h-12 w-full appearance-none rounded-[0.95rem] border border-[#13212c]/10 bg-[#fbf8f2] px-4 pr-10 text-[15px] font-semibold leading-none text-[#13212c] outline-none transition focus:border-[#13212c] focus:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                <option value="" disabled>
                                  {t("putaway.batchChooseRack", "Choose rack")}
                                </option>
                                {(activeAisle?.racks || []).map((rack) => (
                                  <option key={`batch-rack-option-${rack.rack}`} value={rack.rack}>
                                    {t("putaway.visualRackLabel", "Rack {rack}", { rack: rack.rack })}
                                  </option>
                                ))}
                              </select>
                              <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-[#61717d]">▾</span>
                            </div>
                            {selectedRackKey ? (() => {
                              const rackSummary = inventoryContextSummary.rack(selectedZoneKey || "", selectedAisleKey || "", selectedRackKey);
                              return (
                                <div className="mt-3 rounded-[0.85rem] border border-[#13212c]/6 bg-[#f7f4ee] px-3 py-3">
                                  <div className="h-2 overflow-hidden rounded-full bg-[#ece5da]">
                                    <div className={`${occupancyTone(rackSummary.units)} h-full rounded-full`} style={{ width: `${Math.max(rackSummary.occupiedCount ? 14 : 8, Math.min(100, rackSummary.occupiedCount * 14))}%` }} />
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-[#61717d]">
                                    {t("putaway.visualUnitsStoredShort", "{count} units", { count: rackSummary.units })} · {t("putaway.visualOccupiedSlotsShort", "{count} slots used", { count: rackSummary.occupiedCount })}
                                  </p>
                                </div>
                              );
                            })() : (
                              null
                            )}
                          </label>

                          <label className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">{t("putaway.visualSelectLevel", "Level")}</p>
                              <span className="rounded-full bg-[#f7f4ee] px-2.5 py-1 text-[11px] font-medium text-[#61717d]">
                                {(activeRack?.levels || []).length} {t("putaway.visualChoices", "choices")}
                              </span>
                            </div>
                            <div className="relative mt-3">
                              <select
                                value={selectedLevelKey}
                                onChange={(event) => handleChooseLevel(event.target.value)}
                                disabled={!activeRack}
                                className="h-12 w-full appearance-none rounded-[0.95rem] border border-[#13212c]/10 bg-[#fbf8f2] px-4 pr-10 text-[15px] font-semibold leading-none text-[#13212c] outline-none transition focus:border-[#13212c] focus:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                <option value="" disabled>
                                  {t("putaway.visualChangeLevel", "Choose level")}
                                </option>
                                {(activeRack?.levels || []).map((level) => (
                                  <option key={`batch-level-option-${level.level}`} value={level.level}>
                                    {t("putaway.visualLevelLabel", "Level {level}", { level: level.level })}
                                  </option>
                                ))}
                              </select>
                              <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-[#61717d]">▾</span>
                            </div>
                            {selectedLevelKey ? (() => {
                              const level = activeRack?.levels.find((item: any) => item.level === selectedLevelKey);
                              const levelUnits = (level?.locations || []).reduce((sum: number, location: any) => sum + inventoryContextSummary.slot(location.id).units, 0);
                              const occupiedSlots = (level?.locations || []).filter((location: any) => inventoryContextSummary.slot(location.id).units > 0).length;
                              return (
                                <div className="mt-3 rounded-[0.85rem] border border-[#13212c]/6 bg-[#f7f4ee] px-3 py-3">
                                  <div className="h-2 overflow-hidden rounded-full bg-[#ece5da]">
                                    <div className={`${occupancyTone(levelUnits)} h-full rounded-full`} style={{ width: `${Math.max(occupiedSlots ? 14 : 8, Math.min(100, (occupiedSlots / Math.max(1, level?.locations?.length || 1)) * 100))}%` }} />
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-[#61717d]">
                                    {t("putaway.visualLevelLoad", "{units} units across {count} positions", {
                                      units: levelUnits,
                                      count: level?.locations?.length || 0,
                                    })}
                                  </p>
                                </div>
                              );
                            })() : (
                              null
                            )}
                          </label>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 rounded-[1rem] border border-dashed border-[#13212c]/12 bg-white px-4 py-4">
                      {activeLevel ? (
                        <>
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                                {t("putaway.batchLiveBoard", "Live slot board")}
                              </p>
                            </div>
                            <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                              {t("putaway.visualRackFocusLabel", "{zone} / aisle {aisle} / rack {rack}", {
                                zone: selectedZoneKey || "—",
                                aisle: selectedAisleKey || "—",
                                rack: selectedRackKey || "—",
                              })} · {t("putaway.visualLevelLabel", "Level {level}", { level: activeLevel.level })}
                            </div>
                          </div>
                          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                            {activeLevel.locations.map((location: any) => {
                              const assigned = activeLevelAssignmentMap.get(location.id) || [];
                              const suggestionMeta = suggestionMap.get(location.id);
                              return (
                                <div
                                  key={`batch-live-${location.id}`}
                                  role="button"
                                  tabIndex={0}
                                  onClick={() => {
                                    const usedBatchPlacement =
                                      !draggedTaskId &&
                                      selectedTaskIds.length > 1 &&
                                      handleAssignSelectedTasksToLevel(location.id);
                                    if (usedBatchPlacement) return;

                                    const focusTaskId = draggedTaskId || selectedTaskId;
                                    if (focusTaskId) {
                                      handleAssignTaskToLocation(focusTaskId, location.id);
                                      setDraggedTaskId(null);
                                    }
                                  }}
                                  onKeyDown={(event) => {
                                    if ((event.key === "Enter" || event.key === " ") && (draggedTaskId || selectedTaskId || selectedTaskIds.length > 1)) {
                                      event.preventDefault();
                                      const usedBatchPlacement =
                                        !draggedTaskId &&
                                        selectedTaskIds.length > 1 &&
                                        handleAssignSelectedTasksToLevel(location.id);
                                      if (!usedBatchPlacement && (draggedTaskId || selectedTaskId)) {
                                        handleAssignTaskToLocation((draggedTaskId || selectedTaskId) as string, location.id);
                                        setDraggedTaskId(null);
                                      }
                                    }
                                  }}
                                  onDragOver={(event) => {
                                    if (selectedBatchTasks.length > 1) event.preventDefault();
                                  }}
                                  onDrop={(event) => {
                                    event.preventDefault();
                                    if (draggedTaskId) {
                                      handleAssignTaskToLocation(draggedTaskId, location.id);
                                      setDraggedTaskId(null);
                                    }
                                  }}
                                  className={`rounded-[0.95rem] border px-3 py-3 ${
                                    assigned.length
                                      ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                                      : suggestionMeta
                                        ? "border-[#d19009]/20 bg-[#fff7e8]"
                                        : "border-[#13212c]/8 bg-[#fbf8f2]"
                                  }`}
                                >
                                  <div className="flex items-start justify-between gap-2">
                                    <div>
                                      <p className={`text-sm font-semibold ${assigned.length ? "text-[#f4efe8]" : "text-[#13212c]"}`}>
                                        {t("putaway.visualPositionLabel", "Position {position}", { position: location.parsed.position })}
                                      </p>
                                      <p className={`mt-1 text-xs uppercase tracking-[0.14em] ${assigned.length ? "text-[#d0dbe2]" : "text-[#7f8d98]"}`}>
                                        {location.barcode}
                                      </p>
                                    </div>
                                    {suggestionMeta ? (
                                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                                        assigned.length
                                          ? "border-[#f7bf45]/28 bg-[#f7bf45]/12 text-[#f7bf45]"
                                          : "border-[#f7bf45]/24 bg-[#fff4da] text-[#8a6511]"
                                      }`}>
                                        {t("putaway.visualSuggestedRank", "Suggested {rank}", { rank: suggestionMeta.rank })}
                                      </span>
                                    ) : null}
                                  </div>
                                  {assigned.length ? (
                                    <div className="mt-3 space-y-2">
                                      {assigned.map((task: any) => (
                                        <div key={`mini-assigned-${location.id}-${task.id}`} className="rounded-[0.8rem] border border-white/12 bg-white/8 px-2 py-2">
                                          <div className="flex items-start justify-between gap-2">
                                            <div>
                                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#f4efe8]">{taskNumberLabel(task)}</p>
                                              <p className="mt-1 text-[11px] text-[#d0dbe2]">{task.inbound_order_number}</p>
                                            </div>
                                            <button
                                              type="button"
                                              onClick={() => handleUnassignTask(task.id)}
                                              className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/16 bg-white/10 text-white/80"
                                              aria-label={t("putaway.batchUnassign", "Remove planned move")}
                                            >
                                              <X size={10} />
                                            </button>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <p className="mt-3 text-xs leading-5 text-[#61717d]">
                                      {t("putaway.batchDropHere", "Drop a task chip here to preview this slot.")}
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </>
                      ) : (
                        <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4 text-sm font-semibold text-[#13212c]">
                          {t("putaway.batchLiveBoard", "Live slot board")}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {batchResult ? (
                <div className={`mt-4 rounded-[1rem] border px-4 py-4 text-sm ${batchResult.failedCount > 0 || batchResult.queuedCount > 0 ? "border-amber-200 bg-amber-50 text-amber-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
                  {batchResult.queuedCount > 0
                    ? t("putaway.batchQueued", "{queued} tasks were saved offline and will sync automatically. Keep this batch selected until the sync banner clears.", {
                        queued: batchResult.queuedCount,
                      })
                    : batchResult.failedCount > 0
                    ? t("putaway.batchPartial", "{success} tasks confirmed, {failed} still need attention.", {
                        success: batchResult.successCount,
                        failed: batchResult.failedCount,
                      })
                    : t("putaway.batchDone", "All selected tasks were confirmed successfully.")}
                  {batchResult.failedCount > 0 && batchResult.failures.length > 0 ? (
                    <p className="mt-2 text-xs leading-relaxed">
                      {batchResult.failures.slice(0, 3).join(" · ")}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
            </>
          ) : null}

          {!showBatchWorkspace && activeTask ? (
            <div className="space-y-5">
              <MobileFlowGuide
                eyebrow={t("putaway.activeTask", "Active task")}
                contextTitle={`${taskNumberLabel(activeTask)} · ${activeTask.sku_label}`}
                title={putawayMobileTitle}
                hint={putawayMobileHint}
                steps={putawayMobileSteps}
                onBack={() => setActiveWorkspaceTab("tasks")}
                backLabel={t("putaway.mobileBackShort", "Back")}
                compact
              />

              {confirmRecoveryState ? (
                <PutawayRecoveryPanel
                  code={confirmRecoveryState.code}
                  title={confirmRecoveryState.title}
                  body={confirmRecoveryState.body}
                  message={confirmErrorMessage}
                  actions={confirmRecoveryState.actions}
                  onAction={handlePutawayRecoveryAction}
                  receivingPath={receivingRecoveryPath}
                  t={t}
                />
              ) : (
                <>
              <div id="putaway-final-slot-picker-mobile" className="space-y-3 md:hidden">
                <div className="rounded-2xl bg-white p-3 shadow">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[10px] uppercase tracking-[0.16em] text-[#7f8d98]">
                        {t("putaway.activeTask", "Active task")}
                      </p>
                      <h3 className="mt-1 break-words text-base font-semibold leading-5 text-[#13212c]">
                        {taskNumberLabel(activeTask)} · {activeTask.handling_unit_code || activeTask.inbound_order_number}
                      </h3>
                      <p className="mt-1 truncate text-xs text-[#61717d]">{activeTask.sku_label}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-[#13212c]/10 bg-[#fbf8f2] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#13212c]">
                      {t("putaway.qtyShort", "Qty")} {activeTask.quantity}
                    </span>
                  </div>

                  <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-stretch gap-2">
                    <div className="min-w-0 rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.14em] text-[#7f8d98]">{t("putaway.decisionFrom", "From")}</p>
                      <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">{activeTask.source_barcode}</p>
                    </div>
                    <div className="flex items-center">
                      <ArrowRight className="text-[#7f8d98]" size={14} />
                    </div>
                    <div className="min-w-0 rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-2">
                      <p className="text-[10px] uppercase tracking-[0.14em] text-[#7f8d98]">{t("putaway.decisionTo", "To")}</p>
                      <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">
                        {selectedDestinationMeta?.barcode || t("putaway.noDestinationSelected", "No slot selected")}
                      </p>
                    </div>
                  </div>

                  <div
                    className={`mt-3 rounded-xl border px-3 py-2 ${
                      mobileConfirmBlockedReason
                        ? "border-[#f7bf45]/30 bg-[#fff7e8] text-[#8a6511]"
                        : "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]"
                    }`}
                  >
                    <p className="text-xs font-semibold">
                      {mobileConfirmBlockedReason || t("putaway.mobileReadyBlocker", "Ready to confirm.")}
                    </p>
                    <p className="mt-1 text-xs leading-5">{mobileConfirmNextStep}</p>
                    {destinationPlacementBlocked ? (
                      <button
                        type="button"
                        onClick={clearActiveDestinationPlan}
                        className="mt-2 min-h-[44px] w-full rounded-xl border border-[#d19009]/28 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#8a6511]"
                      >
                        {t("putaway.mobileChooseAnotherSlotAction", "Choose another slot")}
                      </button>
                    ) : null}
                  </div>

                  {selectedDestinationMeta ? (
                    <div className="mt-3 rounded-xl border border-[#13212c]/8 bg-[#fbf8f2] p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-[#13212c]">{selectedDestinationMeta.barcode}</p>
                          <p className="mt-1 text-xs leading-5 text-[#51606b]">
                            {describeLocationBarcode(selectedDestinationMeta.barcode, t)}
                          </p>
                        </div>
                        <span className="shrink-0 rounded-full border border-[#13212c]/10 bg-white px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#61717d]">
                          {splitSummaryLabel}
                        </span>
                      </div>
                      <div className="mt-3">
                        <BarcodeScanner
                          key={`putaway-destination-${selectedDestinationId}`}
                          context="putaway-destination"
                          onScan={handleMobileDestinationScan}
                          placeholder={t("putaway.mobileScanDestinationPlaceholder", "Scan or type final slot code...")}
                          manualHintTitle={t("putaway.mobileExpectedDestination", "Expected final slot")}
                          manualHintBody={selectedDestinationMeta.barcode}
                          deviceHint={t("putaway.mobileScanDestinationHint", "Scan the physical slot barcode, or type the exact final slot code before confirming putaway.")}
                        />
                        {mobileDestinationConfirmed ? (
                          <p className="mt-2 rounded-[0.8rem] border border-[#9ed4b7] bg-[#edf8f1] px-3 py-2 text-xs font-semibold text-[#1b5f38]">
                            {t("putaway.mobileDestinationConfirmed", "Final slot confirmed.")}
                          </p>
                        ) : mobileDestinationScanError ? (
                          <p className="mt-2 rounded-[0.8rem] border border-[#e4c1b8] bg-[#fff1ed] px-3 py-2 text-xs font-semibold text-[#8f3627]">
                            {mobileDestinationScanError}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  ) : primaryMobileSuggestion ? (
                    <div className="mt-3 rounded-xl border border-[#d19009]/28 bg-[#fff7e8] px-3 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a6511]">
                            {t("putaway.mobileRecommendedSlot", "Recommended slot")}
                          </p>
                          <p className="mt-1 truncate text-sm font-semibold text-[#13212c]">{primaryMobileSuggestion.barcode}</p>
                          <p className="mt-1 text-xs leading-5 text-[#61717d]">
                            {describeLocationBarcode(primaryMobileSuggestion.barcode, t)}
                          </p>
                        </div>
                        <span className="shrink-0 rounded-full border border-[#d19009]/28 bg-white px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8a6511]">
                          {primaryMobileSuggestion.reasonLabel}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-dashed border-[#13212c]/12 bg-[#fbf8f2] px-3 py-3 text-sm leading-6 text-[#61717d]">
                      {t("putaway.noSuggestions", "No automatic suggestion yet. Choose a valid storage location manually below.")}
                    </div>
                  )}
                </div>

                {secondaryMobileSuggestions.length > 0 ? (
                  <details
                    className="rounded-2xl border border-[#13212c]/8 bg-[#fbf8f2] p-3"
                    data-testid="putaway-mobile-other-suggestions"
                  >
                    <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                      {t("putaway.mobileOtherSuggestionsToggle", "Show other suggested slots")}
                    </summary>
                    <div className="mt-3 space-y-2">
                      {secondaryMobileSuggestions.map((suggestion: any) => (
                        <button
                          key={`mobile-secondary-suggestion-${suggestion.location_id}`}
                          type="button"
                          onClick={() => handleUseSuggestion(suggestion.location_id)}
                          className="min-h-[44px] w-full rounded-xl border border-[#13212c]/8 bg-white px-3 py-3 text-left transition hover:border-[#13212c]/14"
                        >
                          <p className="truncate text-sm font-semibold text-[#13212c]">{suggestion.barcode}</p>
                          <p className="mt-1 text-xs leading-5 text-[#61717d]">
                            {describeLocationBarcode(suggestion.barcode, t)}
                          </p>
                        </button>
                      ))}
                    </div>
                  </details>
                ) : null}

                <details
                  className="rounded-2xl border border-[#13212c]/8 bg-[#fbf8f2] p-3"
                  data-testid="putaway-mobile-manual-slot"
                >
                  <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                    {t("putaway.mobileManualSlotToggle", "Choose final slot manually")}
                  </summary>
                  <div className="mt-3 space-y-3">
                    <DestinationStepSelector
                      t={t}
                      tree={visualLocationTree}
                      value={{
                        locationId: selectedDestinationId,
                        zone: selectedZoneKey,
                        aisle: selectedAisleKey,
                        rack: selectedRackKey,
                        level: selectedLevelKey,
                        quantity: primaryDestinationQuantity,
                      }}
                      unavailableLocationIds={new Set(splitDestinations.map((destination) => destination.locationId).filter(Boolean))}
                      onChange={(nextValue) => {
                        if (nextValue.zone !== undefined) setSelectedZoneKey(nextValue.zone || "");
                        if (nextValue.aisle !== undefined) setSelectedAisleKey(nextValue.aisle || "");
                        if (nextValue.rack !== undefined) setSelectedRackKey(nextValue.rack || "");
                        if (nextValue.level !== undefined) setSelectedLevelKey(nextValue.level || "");
                        if (nextValue.locationId) {
                          const location = destinationCandidates.find((item: any) => item.id === nextValue.locationId);
                          if (location) handleChooseSlot(location);
                        } else {
                          setSelectedDestinationId("");
                        }
                      }}
                    />
                    <details className="rounded-[1rem] border border-[#13212c]/8 bg-white">
                      <summary className="cursor-pointer list-none px-3 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                        {t("putaway.otherDestinationCodes", "Other location codes")}
                      </summary>
                      <div className="space-y-2 border-t border-[#13212c]/8 px-3 py-3">
                        <input
                          value={otherDestinationCode}
                          onChange={(event) => setOtherDestinationCode(event.target.value)}
                          placeholder={t("putaway.otherDestinationPlaceholder", "Type exact location code")}
                          className="min-h-[44px] w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                        />
                        <button
                          type="button"
                          onClick={handleUseOtherDestinationCode}
                          disabled={!otherDestinationMatch}
                          className="min-h-[44px] w-full rounded-[1rem] bg-[#13212c] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {t("putaway.useOtherDestination", "Use location code")}
                        </button>
                        <p className={`text-xs leading-5 ${normalizedOtherDestinationCode && !otherDestinationMatch ? "text-[#8f3627]" : "text-[#61717d]"}`}>
                          {normalizedOtherDestinationCode && !otherDestinationMatch
                            ? t("putaway.otherDestinationNoMatch", "No matching storage location code found.")
                            : t("putaway.otherDestinationHelp", "Use this only for existing location codes that cannot be split into zone, aisle, rack, level, and position.")}
                        </p>
                      </div>
                    </details>
                  </div>
                </details>
              </div>

              <div id="putaway-final-slot-picker-desktop" className="hidden rounded-[1.5rem] border border-[#13212c]/8 bg-[#fbf8f2] p-5 md:block">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <button
                      type="button"
                      onClick={() => setActiveWorkspaceTab("tasks")}
                      className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                    >
                      <ArrowLeft size={14} />
                      {t("putaway.backToTaskQueue", "Back to task queue")}
                    </button>
                    <p className="mt-4 text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">{t("putaway.activeTask", "Active task")}</p>
                    <h2 className="mt-2 text-xl font-semibold text-[#13212c]">
                      {taskNumberLabel(activeTask)} · {activeTask.sku_label}
                    </h2>
                    <p className="mt-2 text-sm leading-6 text-[#61717d]">
                      {activeTask.inbound_order_number}
                      {activeTask.handling_unit_code ? ` · ${t("putaway.handlingUnitLabel", "HU")}: ${activeTask.handling_unit_code}` : ""}
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 lg:min-w-[320px]">
                    <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.decisionFrom", "From")}</p>
                      <p className="mt-1 text-sm font-semibold text-[#13212c]">{activeTask.source_barcode}</p>
                      <p className="mt-1 text-xs leading-5 text-[#61717d]">{activeTask.warehouse_label}</p>
                    </div>
                    <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.decisionTo", "To")}</p>
                      <p className="mt-1 text-sm font-semibold text-[#13212c]">
                        {selectedDestinationMeta?.barcode || t("putaway.noDestinationYet", "Choose a final storage slot below")}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[#61717d]">{splitSummaryLabel}</p>
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                    {t("putaway.qtyWaiting", "Qty waiting in staging")}: {activeTask.quantity}
                  </span>
                  <span
                    className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${getExecutionModeTone(activeTask.execution_mode)}`}
                  >
                    {getExecutionModeLabel(activeTask.execution_mode, t)}
                  </span>
                  <span className="rounded-full border border-[#13212c]/8 bg-white px-3 py-1 text-[11px] text-[#61717d]">
                    {getExecutionReasonLabel(activeTask.execution_reason, t)}
                  </span>
                  <span
                    className={`rounded-full border px-3 py-1 text-[11px] ${
                      activeTask.agv_eligible
                        ? "border-[#87c6a1]/28 bg-[#eef9f1] text-[#356b4c]"
                        : "border-[#d19009]/28 bg-[#fff7e8] text-[#8a6511]"
                    }`}
                  >
                    {activeTask.agv_eligible
                      ? t("putaway.agvEligible", "AGV eligible")
                      : t("putaway.workerOnly", "Worker only")}
                  </span>
                </div>
              </div>

              {activeTaskHasSecondaryDetails ? (
                <details className="rounded-[1.2rem] border border-[#13212c]/8 bg-white">
                  <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-[#13212c]">
                    {t("putaway.taskDetailsToggle", "Task details")}
                  </summary>
                  <div className="border-t border-[#13212c]/8 px-4 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      {activeTask.handling_unit_status ? (
                        <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                          {getHandlingUnitStatusLabel(activeTask.handling_unit_status, t)}
                        </span>
                      ) : null}
                      {activeTask.package_count != null ? (
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                          {t("putaway.packageCountLabel", "Packages")}: {activeTask.package_count}
                        </span>
                      ) : null}
                      {activeTask.measured_weight_kg != null ? (
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                          {t("putaway.measuredWeightLabel", "Measured weight")}: {activeTask.measured_weight_kg} kg
                        </span>
                      ) : null}
                      {activeTaskExternalCodeSummary ? (
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                          {activeTaskExternalCodeSummary}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </details>
              ) : null}

              {batchWorkspaceTasks.length <= 1 ? (
              <div className="hidden rounded-[1.5rem] border border-[#13212c]/8 bg-[#fbf8f2] p-5 md:block">
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">{t("putaway.destinationLabel", "Final storage location")}</p>
                    <h3 className="mt-2 text-lg font-semibold text-[#13212c]">{t("putaway.chooseDestination", "Choose final storage location")}</h3>
                  </div>
                  <span className="w-fit rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                    {t("putaway.destinationCount", "Suggested slots")}: {enrichedSuggestions.length || "—"}
                  </span>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {enrichedSuggestions.length === 0 ? (
                    <div className="md:col-span-3 rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4 text-sm text-[#61717d]">
                      {t("putaway.noSuggestions", "No automatic suggestion yet. Choose a valid storage location manually below.")}
                    </div>
                  ) : (
                    enrichedSuggestions.map((suggestion: any) => (
                      <button
                        key={suggestion.location_id}
                        onClick={() => handleUseSuggestion(suggestion.location_id)}
                        className={`rounded-[1.2rem] border px-4 py-4 text-left transition ${
                          selectedDestinationId === suggestion.location_id
                            ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                            : "border-[#13212c]/8 bg-white hover:border-[#13212c]/14"
                        }`}
                        >
                        <p className="text-sm font-semibold">{suggestion.barcode}</p>
                        <p className={`mt-1 text-sm leading-6 ${selectedDestinationId === suggestion.location_id ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                          {describeLocationBarcode(suggestion.barcode, t)}
                        </p>
                        <p className={`mt-2 text-xs uppercase tracking-[0.16em] ${selectedDestinationId === suggestion.location_id ? "text-[#d0dbe2]" : "text-[#7f8d98]"}`}>
                          {suggestion.reasonLabel}
                        </p>
                      </button>
                    ))
                  )}
                </div>
                <div className="mt-4 rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4">
                  <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">
                        {t("putaway.manualDestinationLabel", "Manual slot")}
                      </p>
                      <p className="mt-1 text-sm text-[#61717d]">
                        {t("putaway.manualDestinationHint", "Pick the location step by step instead of scrolling through full slot codes.")}
                      </p>
                    </div>
                    <span className="w-fit rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                      {selectedDestinationMeta?.barcode || t("putaway.noDestinationSelected", "No slot selected")}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-5">
                    <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                      {t("putaway.destinationZone", "Zone")}
                      <select
                        value={selectedZoneKey}
                        onChange={(e) => handleChooseZone(e.target.value)}
                        className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                      >
                        <option value="">{t("putaway.destinationZonePlaceholder", "Select zone")}</option>
                        {visualLocationTree.map((zone) => (
                          <option key={zone.zone} value={zone.zone}>
                            {zone.zone}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                      {t("putaway.destinationAisle", "Aisle")}
                      <select
                        value={selectedAisleKey}
                        onChange={(e) => handleChooseAisle(e.target.value)}
                        disabled={!activeZone}
                        className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
                      >
                        <option value="">{t("putaway.destinationAislePlaceholder", "Select aisle")}</option>
                        {(activeZone?.aisles || []).map((aisle) => (
                          <option key={aisle.aisle} value={aisle.aisle}>
                            {aisle.aisle}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                      {t("putaway.destinationRack", "Rack")}
                      <select
                        value={selectedRackKey}
                        onChange={(e) => handleChooseRack(e.target.value)}
                        disabled={!activeAisle}
                        className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
                      >
                        <option value="">{t("putaway.destinationRackPlaceholder", "Select rack")}</option>
                        {(activeAisle?.racks || []).map((rack) => (
                          <option key={rack.rack} value={rack.rack}>
                            {rack.rack}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                      {t("putaway.destinationLevel", "Level")}
                      <select
                        value={selectedLevelKey}
                        onChange={(e) => handleChooseLevel(e.target.value)}
                        disabled={!activeRack}
                        className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
                      >
                        <option value="">{t("putaway.destinationLevelPlaceholder", "Select level")}</option>
                        {(activeRack?.levels || []).map((level) => (
                          <option key={level.level} value={level.level}>
                            {level.level}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                      {t("putaway.destinationPosition", "Position")}
                      <select
                        value={selectedDestinationId}
                        onChange={(e) => {
                          const location = activeLevelLocations.find((item: any) => item.id === e.target.value);
                          if (location) {
                            handleChooseSlot(location);
                            return;
                          }
                          setSelectedDestinationId("");
                        }}
                        disabled={!activeLevel}
                        className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
                      >
                        <option value="">{t("putaway.destinationPositionPlaceholder", "Select position")}</option>
                        {activeLevelLocations.map((location: any) => {
                          const parsed = parseStorageBarcode(location.barcode);
                          return (
                            <option key={location.id} value={location.id}>
                              {parsed?.position || location.barcode}
                            </option>
                          );
                        })}
                      </select>
                    </label>
                  </div>

                  {selectedDestinationMeta ? (
                    <p className="mt-3 text-sm leading-6 text-[#61717d]">
                      {describeLocationBarcode(selectedDestinationMeta.barcode, t)}
                    </p>
                  ) : null}

                  {unstructuredDestinationCandidates.length > 0 ? (
                    <details className="mt-3 rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2]">
                      <summary className="cursor-pointer list-none px-3 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                        {t("putaway.otherDestinationCodes", "Other location codes")}
                      </summary>
                      <div className="border-t border-[#13212c]/8 px-3 py-3">
                        <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                          <input
                            value={otherDestinationCode}
                            onChange={(e) => setOtherDestinationCode(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                handleUseOtherDestinationCode();
                              }
                            }}
                            placeholder={t("putaway.otherDestinationPlaceholder", "Type exact location code")}
                            className="w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                          />
                          <button
                            type="button"
                            onClick={handleUseOtherDestinationCode}
                            disabled={!otherDestinationMatch}
                            className="rounded-[1rem] bg-[#13212c] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {t("putaway.useOtherDestinationCode", "Use code")}
                          </button>
                        </div>
                        <p className="mt-2 text-xs leading-5 text-[#61717d]">
                          {otherDestinationCode && !otherDestinationMatch
                            ? t("putaway.otherDestinationNoMatch", "No matching storage location code found.")
                            : t("putaway.otherDestinationHelp", "Use this only for existing location codes that cannot be split into zone, aisle, rack, level, and position.")}
                        </p>
                      </div>
                    </details>
                  ) : null}
                </div>
              </div>
              ) : null}

              <details className="rounded-[1.5rem] border border-[#13212c]/8 bg-[#fbf8f2]">
                <summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-[#13212c]">
                  {t("putaway.openRackView", "Open rack view")}
                </summary>

                <div className="border-t border-[#13212c]/8 px-5 py-5">
                <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.visualLegend", "Slot legend")}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <LegendChip
                          label={t("putaway.visualLegendSuggested", "Suggested slot")}
                          className="border-[#d19009]/28 bg-[#fff7e8] text-[#8a6511]"
                        />
                        <LegendChip
                          label={t("putaway.visualLegendManual", "Manual slot")}
                          className="border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d]"
                        />
                        <LegendChip
                          label={t("putaway.visualLegendSelected", "Selected slot")}
                          className="border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                        />
                      </div>
                    </div>
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.visualStrength", "Recommendation strength")}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <LegendChip
                          label={t("putaway.visualStrengthPrimary", "Strongest")}
                          className="border-[#d19009]/28 bg-[#fff7e8] text-[#8a6511]"
                        />
                        <LegendChip
                          label={t("putaway.visualStrengthSecondary", "Second choice")}
                          className="border-[#7da9ff]/28 bg-[#eff5ff] text-[#4977c8]"
                        />
                        <LegendChip
                          label={t("putaway.visualStrengthTertiary", "Fallback")}
                          className="border-[#87c6a1]/28 bg-[#eef9f1] text-[#356b4c]"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-4 space-y-4">
                  {visualLocationTree.length === 0 ? (
                    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4 text-sm text-[#61717d]">
                      {t("putaway.visualPickerEmpty", "No structured storage layout is available yet for this warehouse.")}
                    </div>
                  ) : (
                    <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-white px-4 py-4">
                      <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div>
                            <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.visualPath", "Selection path")}</p>
                            {selectedZoneKey ? (
                              <p className="mt-2 text-sm leading-6 text-[#61717d]">
                                {t("putaway.visualPathFilled", "Zone {zone} / Aisle {aisle} / Rack {rack} / Level {level}", {
                                  zone: selectedZoneKey,
                                  aisle: selectedAisleKey || "—",
                                  rack: selectedRackKey || "—",
                                  level: selectedLevelKey || "—",
                                })}
                              </p>
                            ) : null}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <LegendChip
                              label={t("putaway.visualStep", "Step {step} of 5", { step: pickerStep })}
                              className="border-[#13212c]/10 bg-white text-[#61717d]"
                            />
                            {selectedZoneKey ? (
                              <button
                                type="button"
                                onClick={resetPickerPath}
                                className="rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                              >
                                {t("putaway.visualStartOver", "Start over")}
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <StepChip index="1" label={t("putaway.visualStepZone", "Choose zone")} active={pickerStep === 1} complete={Boolean(selectedZoneKey)} />
                          <StepChip index="2" label={t("putaway.visualStepAisle", "Choose aisle")} active={pickerStep === 2} complete={Boolean(selectedAisleKey)} disabled={!selectedZoneKey} />
                          <StepChip index="3" label={t("putaway.visualStepRack", "Choose rack")} active={pickerStep === 3} complete={Boolean(selectedRackKey)} disabled={!selectedAisleKey} />
                          <StepChip index="4" label={t("putaway.visualStepLevel", "Choose level")} active={pickerStep === 4} complete={Boolean(selectedLevelKey)} disabled={!selectedRackKey} />
                          <StepChip index="5" label={t("putaway.visualStepSlot", "Choose slot")} active={pickerStep === 5} complete={Boolean(selectedDestinationId)} disabled={!selectedLevelKey} />
                        </div>
                      </div>

                      <div className="grid gap-4 lg:grid-cols-[220px_220px_minmax(0,1fr)]">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.visualSelectZone", "Zone")}</p>
                          <div className="mt-2 grid gap-2 sm:grid-cols-2">
                            {visualLocationTree.map((zone) => {
                              const zoneSummary = inventoryContextSummary.zone(zone.zone);
                              return (
                                <button
                                  key={zone.zone}
                                  type="button"
                                  onClick={() => handleChooseZone(zone.zone)}
                                  className={`rounded-[1rem] border px-3 py-3 text-left transition ${
                                    selectedZoneKey === zone.zone
                                      ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                                      : "border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d] hover:bg-white"
                                  }`}
                                >
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em]">
                                    {t("putaway.visualZoneLabel", "Zone {zone}", { zone: zone.zone })}
                                  </p>
                                  <div className={`mt-2 grid grid-cols-2 gap-2 text-xs ${selectedZoneKey === zone.zone ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                                    <div>
                                      <p className="uppercase tracking-[0.12em] opacity-70">{t("putaway.visualUnitsStored", "Units stored")}</p>
                                      <p className="mt-1 text-sm font-semibold">{zoneSummary.units}</p>
                                    </div>
                                    <div>
                                      <p className="uppercase tracking-[0.12em] opacity-70">{t("putaway.visualOccupiedSlots", "Slots used")}</p>
                                      <p className="mt-1 text-sm font-semibold">{zoneSummary.occupiedCount}</p>
                                    </div>
                                  </div>
                                  <p className={`mt-2 text-xs leading-5 ${selectedZoneKey === zone.zone ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                                    {formatTopSkuList(zoneSummary.topSkus, t)}
                                  </p>
                                  <div className="mt-3">
                                    <p className={`text-[10px] uppercase tracking-[0.16em] ${selectedZoneKey === zone.zone ? "text-[#d0dbe2]" : "text-[#7f8d98]"}`}>
                                      {t("putaway.visualHeat", "Occupancy heat")}
                                    </p>
                                    <MiniWarehouseStrip
                                      active={selectedZoneKey === zone.zone}
                                      segments={zone.aisles.map((aisle: any) => ({
                                        label: aisle.aisle,
                                        units: inventoryContextSummary.aisle(zone.zone, aisle.aisle).units,
                                      }))}
                                    />
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.visualAisle", "Aisle group")}</p>
                          <div className="mt-2 grid gap-2">
                            {(activeZone?.aisles || []).map((aisle) => {
                              const aisleSummary = inventoryContextSummary.aisle(activeZone?.zone || "", aisle.aisle);
                              return (
                                <button
                                  key={`${activeZone?.zone}-${aisle.aisle}`}
                                  type="button"
                                  onClick={() => handleChooseAisle(aisle.aisle)}
                                  disabled={!selectedZoneKey}
                                  className={`rounded-[1rem] border px-3 py-3 text-left transition ${
                                    selectedAisleKey === aisle.aisle
                                      ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                                      : "border-[#13212c]/10 bg-[#f7f4ee] text-[#61717d] hover:bg-white disabled:cursor-not-allowed disabled:opacity-45"
                                  }`}
                                >
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em]">
                                    {t("putaway.visualAisleLabel", "Zone {zone} / Aisle {aisle}", {
                                      zone: activeZone?.zone || "—",
                                      aisle: aisle.aisle,
                                    })}
                                  </p>
                                  <div className={`mt-2 flex flex-wrap gap-2 text-xs ${selectedAisleKey === aisle.aisle ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                                    <span>{t("putaway.visualUnitsStoredShort", "{count} units", { count: aisleSummary.units })}</span>
                                    <span>•</span>
                                    <span>{t("putaway.visualOccupiedSlotsShort", "{count} slots used", { count: aisleSummary.occupiedCount })}</span>
                                  </div>
                                  <p className={`mt-2 text-xs leading-5 ${selectedAisleKey === aisle.aisle ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                                    {formatTopSkuList(aisleSummary.topSkus, t)}
                                  </p>
                                  {aisleSummary.sameSkuUnits > 0 ? (
                                    <p className={`mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] ${selectedAisleKey === aisle.aisle ? "text-[#f7d472]" : "text-[#8a6511]"}`}>
                                      {t("putaway.visualSameSkuNearby", "Same SKU nearby")}
                                    </p>
                                  ) : null}
                                  <div className="mt-3">
                                    <p className={`text-[10px] uppercase tracking-[0.16em] ${selectedAisleKey === aisle.aisle ? "text-[#d0dbe2]" : "text-[#7f8d98]"}`}>
                                      {t("putaway.visualAisleStrip", "Aisle picture")}
                                    </p>
                                    <MiniWarehouseStrip
                                      active={selectedAisleKey === aisle.aisle}
                                      segments={aisle.racks.map((rack: any) => ({
                                        label: rack.rack,
                                        units: inventoryContextSummary.rack(activeZone?.zone || "", aisle.aisle, rack.rack).units,
                                      }))}
                                    />
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        <div>
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{t("putaway.visualSelectRack", "Rack")}</p>
                              {activeAisle ? (
                                <p className="mt-1 text-base font-semibold text-[#13212c]">
                                  {t("putaway.visualAisleFocus", "{count} racks in this aisle", { count: activeAisle.racks.length })}
                                </p>
                              ) : null}
                            </div>
                            {activeAisle ? (
                              <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-[#61717d]">
                                {t("putaway.visualRackCount", "{count} racks", { count: activeAisle.racks.length })}
                              </div>
                            ) : null}
                          </div>

                          <div className="relative mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4">
                            <div className="absolute left-8 right-8 top-1/2 h-px -translate-y-1/2 bg-[linear-gradient(90deg,rgba(19,33,44,0.08),rgba(19,33,44,0.22),rgba(19,33,44,0.08))]" />
                            <div className="relative grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                              {(activeAisle?.racks || []).map((rackGroup) => {
                                const rackSummary = inventoryContextSummary.rack(activeZone?.zone || "", activeAisle?.aisle || "", rackGroup.rack);
                                return (
                                  <button
                                    key={`${activeZone?.zone}-${activeAisle?.aisle}-${rackGroup.rack}`}
                                    type="button"
                                    onClick={() => handleChooseRack(rackGroup.rack)}
                                    disabled={!selectedAisleKey}
                                    className={`rounded-[1rem] border px-3 py-3 text-left transition ${
                                      selectedRackKey === rackGroup.rack
                                        ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                                        : "border-[#13212c]/10 bg-white text-[#61717d] hover:bg-[#fffdfa] disabled:cursor-not-allowed disabled:opacity-45"
                                    }`}
                                  >
                                    <div className="flex items-start justify-between gap-2">
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em]">
                                        {t("putaway.visualRackLabel", "Rack {rack}", { rack: rackGroup.rack })}
                                      </p>
                                      <span className={`mt-1 h-2.5 w-2.5 rounded-full ${selectedRackKey === rackGroup.rack ? "bg-[#f7bf45]" : "bg-[#13212c]"}`} />
                                    </div>
                                    <div className={`mt-2 grid grid-cols-2 gap-2 text-xs ${selectedRackKey === rackGroup.rack ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                                      <div>
                                        <p className="uppercase tracking-[0.12em] opacity-70">{t("putaway.visualUnitsStored", "Units stored")}</p>
                                        <p className="mt-1 text-sm font-semibold">{rackSummary.units}</p>
                                      </div>
                                      <div>
                                        <p className="uppercase tracking-[0.12em] opacity-70">{t("putaway.visualOccupiedSlots", "Slots used")}</p>
                                        <p className="mt-1 text-sm font-semibold">{rackSummary.occupiedCount}</p>
                                      </div>
                                    </div>
                                    <p className={`mt-2 text-xs leading-5 ${selectedRackKey === rackGroup.rack ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                                      {formatTopSkuList(rackSummary.topSkus, t)}
                                    </p>
                                    <div className="mt-3">
                                      <p className={`text-[10px] uppercase tracking-[0.16em] ${selectedRackKey === rackGroup.rack ? "text-[#d0dbe2]" : "text-[#7f8d98]"}`}>
                                        {t("putaway.visualRackStrip", "Rack levels")}
                                      </p>
                                      <div className="mt-2 flex items-end gap-1.5">
                                        {rackGroup.levels.map((levelGroup: any) => {
                                          const levelUnits = levelGroup.locations.reduce((sum: number, location: any) => sum + inventoryContextSummary.slot(location.id).units, 0);
                                          return (
                                            <div key={levelGroup.level} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                                              <span
                                                className={`w-full rounded-t-md ${selectedRackKey === rackGroup.rack ? "bg-[#f7bf45]" : occupancyTone(levelUnits)}`}
                                                style={{ height: `${Math.max(10, Math.min(36, 10 + levelUnits / 8))}px` }}
                                              />
                                              <span className={`text-[10px] ${selectedRackKey === rackGroup.rack ? "text-[#d0dbe2]" : "text-[#7f8d98]"}`}>
                                                {levelGroup.level}
                                              </span>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      </div>

                      {activeRack ? (
                        <div className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] p-4">
                          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                            <div>
                              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                                {t("putaway.visualRackFocus", "Focused rack")}
                              </p>
                              <p className="mt-1 text-base font-semibold text-[#13212c]">
                                {t("putaway.visualRackFocusLabel", "{zone} / aisle {aisle} / rack {rack}", {
                                  zone: activeZone?.zone || "—",
                                  aisle: activeAisle?.aisle || "—",
                                  rack: activeRack.rack,
                                })}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => resetPickerFrom("level")}
                                className="rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                              >
                                {t("putaway.visualChangeLevel", "Change level")}
                              </button>
                              <button
                                type="button"
                                onClick={() => resetPickerFrom("rack")}
                                className="rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                              >
                                {t("putaway.visualChangeRack", "Change rack")}
                              </button>
                              <button
                                type="button"
                                onClick={() => resetPickerFrom("aisle")}
                                className="rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                              >
                                {t("putaway.visualChangeAisle", "Change aisle")}
                              </button>
                              <button
                                type="button"
                                onClick={() => resetPickerFrom("zone")}
                                className="rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                              >
                                {t("putaway.visualChangeZone", "Change zone")}
                              </button>
                            </div>
                          </div>

                          <div className="mt-3 space-y-3">
                            <div className="rounded-[0.95rem] border border-[#13212c]/6 bg-white px-3 py-3">
                              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                                {t("putaway.visualRackStockTitle", "What is already stored in this rack")}
                              </p>
                              <div className="mt-3 grid gap-3 md:grid-cols-3">
                                <SnapshotStat
                                  label={t("putaway.visualUnitsStored", "Units stored")}
                                  value={activeRackSummary?.units || 0}
                                />
                                <SnapshotStat
                                  label={t("putaway.visualOccupiedSlots", "Slots used")}
                                  value={activeRackSummary?.occupiedCount || 0}
                                />
                                <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4">
                                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                                    {t("putaway.visualTopSkus", "Top SKUs")}
                                  </p>
                                  <p className="mt-2 text-sm leading-6 text-[#13212c]">
                                    {formatTopSkuList(activeRackSummary?.topSkus || [], t)}
                                  </p>
                                  {activeRackSummary && activeRackSummary.sameSkuUnits > 0 ? (
                                    <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#8a6511]">
                                      {t("putaway.visualSameSkuNearby", "Same SKU nearby")}
                                    </p>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                            <div className="rounded-[0.95rem] border border-[#13212c]/6 bg-white px-3 py-3">
                              <div className="flex items-center justify-between gap-3">
                                <div>
                                  <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                                    {t("putaway.visualSelectLevel", "Level")}
                                  </p>
                                </div>
                                <div className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-[#61717d]">
                                  {t("putaway.visualLevelCount", "{count} levels", { count: activeRack.levels.length })}
                                </div>
                              </div>
                              <div className="mt-3 grid gap-2 md:grid-cols-3">
                                {activeRackLevelOccupancy.map((level) => (
                                  <button
                                    key={level.level}
                                    type="button"
                                    onClick={() => handleChooseLevel(level.level)}
                                    className={`rounded-[0.95rem] border px-3 py-3 text-left transition ${
                                      selectedLevelKey === level.level
                                        ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                                        : "border-[#13212c]/8 bg-[#fbf8f2] text-[#61717d] hover:bg-[#fffdfa]"
                                    }`}
                                  >
                                    <div className="flex items-center justify-between gap-2">
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em]">
                                        {t("putaway.visualLevelLabel", "Level {level}", { level: level.level })}
                                      </p>
                                      {selectedLevelKey === level.level ? (
                                        <span className="rounded-full border border-[#f7bf45]/28 bg-[#f7bf45]/12 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#f7bf45]">
                                          {t("putaway.visualSelectedNow", "Selected")}
                                        </span>
                                      ) : null}
                                    </div>
                                    <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-[#ece5da]">
                                      <div
                                        className={`h-full rounded-full ${selectedLevelKey === level.level ? "bg-[#f7bf45]" : occupancyTone(level.units)}`}
                                        style={{ width: `${Math.max(level.occupiedSlots ? 14 : 8, Math.min(100, (level.occupiedSlots / Math.max(1, level.totalSlots)) * 100))}%` }}
                                      />
                                    </div>
                                    <p className={`mt-2 text-xs leading-5 ${selectedLevelKey === level.level ? "text-[#d0dbe2]" : "text-[#61717d]"}`}>
                                      {t("putaway.visualLevelLoad", "{units} units across {count} positions", {
                                        units: level.units,
                                        count: level.totalSlots,
                                      })}
                                    </p>
                                  </button>
                                ))}
                              </div>
                            </div>
                            {activeLevel ? (
                              <div key={`${activeZone?.zone}-${activeAisle?.aisle}-${activeRack.rack}-${activeLevel.level}`} className="relative rounded-[0.95rem] border border-[#13212c]/6 bg-white px-3 py-3">
                                <div className="absolute left-4 right-4 top-[38px] h-px bg-[linear-gradient(90deg,rgba(19,33,44,0.06),rgba(19,33,44,0.18),rgba(19,33,44,0.06))]" />
                                <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                                  {t("putaway.visualLevelLabel", "Level {level}", { level: activeLevel.level })}
                                </p>
                                <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#8a6511]">
                                  {t("putaway.visualClickSlotHint", "Click one slot cell below to select it directly")}
                                </p>
                                <div className="relative mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
                                  {activeLevel.locations.map((location: any) => {
                                    const suggestionMeta = suggestionMap.get(location.id);
                                    const selected = selectedDestinationId === location.id;
                                    const strength = getSuggestionStrength(suggestionMeta?.rank);
                                    const tone = getSlotTone(strength, selected);
                                    const slotSummary = inventoryContextSummary.slot(location.id);
                                    return (
                                      <button
                                        key={location.id}
                                        type="button"
                                        onClick={() => handleChooseSlot(location)}
                                        onDragOver={(event) => {
                                          if (selectedBatchTasks.length > 1) event.preventDefault();
                                        }}
                                        onDrop={(event) => {
                                          event.preventDefault();
                                          if (draggedTaskId) {
                                            handleAssignTaskToLocation(draggedTaskId, location.id);
                                            setDraggedTaskId(null);
                                          }
                                        }}
                                        className={`rounded-[0.95rem] border px-3 py-3 text-left transition hover:-translate-y-[1px] ${tone.shell} ${selected ? "ring-2 ring-[#f7bf45]/70" : ""}`}
                                      >
                                        <div className="flex items-start justify-between gap-2">
                                          <p className="text-sm font-semibold">
                                            {t("putaway.visualPositionLabel", "Position {position}", { position: location.parsed.position })}
                                          </p>
                                          {selected ? (
                                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${tone.badge}`}>
                                              {t("putaway.visualSelectedNow", "Selected")}
                                            </span>
                                          ) : suggestionMeta ? (
                                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${tone.badge}`}>
                                              {t("putaway.visualSuggestedRank", "Suggested {rank}", { rank: suggestionMeta.rank })}
                                            </span>
                                          ) : null}
                                        </div>
                                        <p className={`mt-1 text-xs uppercase tracking-[0.14em] ${tone.meta}`}>
                                          {location.barcode}
                                        </p>
                                        <p className={`mt-2 text-sm leading-6 ${tone.subtext}`}>
                                          {describeLocationBarcode(location.barcode, t)}
                                        </p>
                                        <p className={`mt-2 text-xs leading-5 ${tone.subtext}`}>
                                          {slotSummary.units > 0
                                            ? t("putaway.visualSlotStock", "{count} units already in this slot", { count: slotSummary.units })
                                            : t("putaway.visualSlotEmpty", "No stock in this slot yet")}
                                        </p>
                                        {slotSummary.topSkus.length > 0 ? (
                                          <p className={`mt-1 text-xs leading-5 ${tone.subtext}`}>
                                            {formatTopSkuList(slotSummary.topSkus, t)}
                                          </p>
                                        ) : null}
                                        {activeLevelAssignmentMap.get(location.id)?.length ? (
                                          <div className="mt-2 flex flex-wrap gap-1.5">
                                            {activeLevelAssignmentMap.get(location.id)!.map((task: any) => (
                                              <span
                                                key={`assigned-${location.id}-${task.id}`}
                                                className="inline-flex items-center gap-1 rounded-full border border-[#13212c]/12 bg-[#13212c] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#f4efe8]"
                                              >
                                                <span>{taskNumberLabel(task)}</span>
                                                <button
                                                  type="button"
                                                  onClick={(event) => {
                                                    event.stopPropagation();
                                                    handleUnassignTask(task.id);
                                                  }}
                                                  className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-white/20 bg-white/10"
                                                  aria-label={t("putaway.batchUnassign", "Remove planned move")}
                                                >
                                                  <X size={9} />
                                                </button>
                                              </span>
                                            ))}
                                          </div>
                                        ) : null}
                                        {suggestionMeta ? (
                                          <p className={`mt-2 text-xs uppercase tracking-[0.14em] ${tone.meta}`}>
                                            {suggestionMeta.reasonLabel}
                                          </p>
                                        ) : (
                                          <p className={`mt-2 text-xs uppercase tracking-[0.14em] ${tone.meta}`}>
                                            {t("putaway.visualManualSlot", "Manual storage slot")}
                                          </p>
                                        )}
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
                </div>
                </details>

              {destinationPlacementIssues.length > 0 ? (
                <div className="space-y-2">
                  <div className="rounded-[1rem] border border-[#f2c2b4] bg-[#fff1eb] px-4 py-3 text-sm leading-6 text-[#8f3e23]">
                    <p className="font-semibold text-[#7f321d]">
                      {t("putaway.destinationBlockedTitle", "Destination needs review before confirmation")}
                    </p>
                    <p className="mt-1">
                      {t("putaway.destinationBlockedBody", "The selected slot conflicts with warehouse storage rules. Choose another slot or update the warehouse policy before confirming.")}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        clearActiveDestinationPlan();
                        window.setTimeout(() => scrollToPutawayControl(finalSlotPickerTargetId()), 0);
                      }}
                      className="mt-3 min-h-[44px] rounded-xl border border-[#8f3e23]/20 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#7f321d] md:min-h-0 md:rounded-full md:py-1.5"
                    >
                      {t("putaway.mobileChooseAnotherSlotAction", "Choose another slot")}
                    </button>
                  </div>
                  {destinationPlacementIssues.map((issue) => (
                    <div
                      key={`${issue.barcode}-${issue.title}`}
                      className={`rounded-[1rem] border px-4 py-3 text-sm leading-6 ${
                        issue.severity === "block"
                          ? "border-red-200 bg-red-50 text-red-700"
                          : "border-[#f7bf45]/35 bg-[#fff7e8] text-[#76560f]"
                      }`}
                    >
                      <p className="font-semibold">
                        {issue.barcode}: {issue.title}
                      </p>
                      <p className="mt-1">{issue.body}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
                <div>
                  <details
                    id="putaway-split-plan"
                    className="rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2]"
                    open={splitDestinations.length > 0 || splitAllocationRows.length > 1}
                  >
                      <summary className="cursor-pointer list-none px-4 py-4 text-sm font-semibold text-[#13212c]">
                        {t("putaway.splitPlan", "Split putaway plan")}
                      </summary>
                      <div className="border-t border-[#13212c]/8 px-4 py-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <button
                        type="button"
                        onClick={handleAddSplitDestination}
                        className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                      >
                        {t("putaway.addDestination", "Add another destination")}
                      </button>
                      <span
                        className={`w-fit rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                          splitAllocationPreview.quantityMatchesTotal
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                            : "border-[#f7bf45]/30 bg-[#fff7e8] text-[#8a6511]"
                        }`}
                      >
                        {splitQuantityStatusLabel}
                      </span>
                    </div>

                    <div className="mt-4 space-y-3">
                      <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_150px]">
                          <div>
                          <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                            {t("putaway.primaryDestination", "Primary final storage location")}
                          </p>
                          <p className="mt-2 text-sm font-semibold text-[#13212c]">{selectedDestinationMeta?.barcode || t("putaway.chooseDestination", "Choose final storage location")}</p>
                          {selectedDestinationMeta ? (
                            <p className="mt-1 text-sm leading-6 text-[#61717d]">{describeLocationBarcode(selectedDestinationMeta.barcode, t)}</p>
                          ) : null}
                          </div>
                          <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                            {t("common.qty", "Qty")}
                            <input
                              type="number"
                              min={1}
                              max={Number(activeTask.quantity || 0)}
                              step={1}
                              value={primaryDestinationQuantity}
                              onChange={(e) => setPrimaryDestinationQuantity(e.target.value)}
                              className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                            />
                          </label>
                        </div>
                      </div>

                      {splitDestinations.map((entry, index) => {
                        const splitMeta = destinationCandidates.find((location: any) => location.id === entry.locationId) || null;
                        const unavailableLocationIds = new Set(
                          [
                            selectedDestinationId,
                            ...splitDestinations
                              .filter((_, itemIndex) => itemIndex !== index)
                              .map((destination) => destination.locationId),
                          ].filter(Boolean)
                        );
                        return (
                          <div key={`split-destination-${index}`} className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                            <div className="flex flex-col gap-3">
                              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                <div>
                                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                                  {t("putaway.extraDestination", "Extra destination")}
                                  </p>
                                  <p className="mt-1 text-sm font-semibold text-[#13212c]">
                                    {splitMeta?.barcode || t("putaway.noDestinationSelected", "No slot selected")}
                                  </p>
                                </div>
                                <div className="flex items-end gap-2">
                                  <label className="w-32 text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                                  {t("common.qty", "Qty")}
                                    <input
                                      type="number"
                                      min={1}
                                      max={Number(activeTask.quantity || 0)}
                                      step={1}
                                      value={entry.quantity}
                                      onChange={(e) => handleUpdateSplitDestination(index, { quantity: e.target.value })}
                                      className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                                    />
                                  </label>
                                  <button
                                    type="button"
                                    onClick={() => handleRemoveSplitDestination(index)}
                                    className="rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d] transition hover:bg-[#fffdfa]"
                                  >
                                    {t("common.remove", "Remove")}
                                  </button>
                                </div>
                              </div>

                              <DestinationStepSelector
                                t={t}
                                tree={visualLocationTree}
                                value={entry}
                                unavailableLocationIds={unavailableLocationIds}
                                onChange={(nextValue) => handleUpdateSplitDestination(index, nextValue)}
                              />
                            </div>
                            {splitMeta ? (
                              <p className="mt-2 text-sm leading-6 text-[#61717d]">{describeLocationBarcode(splitMeta.barcode, t)}</p>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>

                    {splitDestinations.length > 0 && !splitAllocationPreview.quantityMatchesTotal ? (
                      <p className="mt-3 rounded-[0.95rem] border border-[#f7bf45]/30 bg-[#fff7e8] px-3 py-3 text-sm leading-6 text-[#8a6511]">
                        {t("putaway.splitQuantityHelp", "Adjust the primary and extra quantities so their sum equals the task total before confirming.")}
                      </p>
                    ) : null}

                    {splitAllocationRows.length > 1 ? (
                      <div className="mt-4 rounded-[0.95rem] border border-[#13212c]/8 bg-white px-3 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                              {t("putaway.splitSummary", "Split summary")}
                            </p>
                          </div>
                          <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                            {t("putaway.splitDestinationsCount", "{count} destinations", { count: splitAllocationRows.length })}
                          </span>
                        </div>

                        <div className="mt-3 space-y-2">
                          {splitAllocationRows.map((row) => (
                            <div
                              key={`${row.locationId}-${row.primary ? "primary" : "extra"}`}
                              className="flex items-center justify-between gap-3 rounded-[0.9rem] border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-2"
                            >
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <p className="text-sm font-semibold text-[#13212c]">{row.barcode}</p>
                                  <span
                                    className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                                      row.primary
                                        ? "border-[#f7bf45]/28 bg-[#fff4da] text-[#8a6511]"
                                        : "border-[#13212c]/10 bg-white text-[#61717d]"
                                    }`}
                                  >
                                    {row.primary ? t("putaway.primaryDestination", "Primary final storage location") : t("putaway.extraDestination", "Extra destination")}
                                  </span>
                                </div>
                                <p className="mt-1 text-xs text-[#61717d]">{describeLocationBarcode(row.barcode, t)}</p>
                              </div>
                              <div className="text-right">
                                <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">{t("common.qty", "Qty")}</p>
                                <p className="mt-1 text-sm font-semibold text-[#13212c]">{row.quantity}</p>
                              </div>
                            </div>
                          ))}
                        </div>

                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                          <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 font-semibold text-[#61717d]">
                            {t("putaway.splitPrimaryRemaining", "Primary gets {count}", {
                              count: splitAllocationPreview.primaryQuantity,
                            })}
                          </span>
                          <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 font-semibold text-[#61717d]">
                            {t("putaway.splitExtraAssigned", "Extra gets {count}", {
                              count: splitAllocationPreview.extraQuantity,
                            })}
                          </span>
                          <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 font-semibold text-[#13212c]">
                            {t("putaway.splitTotalUnits", "Task total {count}", { count: activeTask.quantity })}
                          </span>
                        </div>
                      </div>
                    ) : null}
                      </div>
                  </details>
                </div>
                {!confirmRecoveryState ? (
                  <button
                    onClick={handleConfirm}
                    disabled={!splitAllocationPreview.isValid || destinationPlacementBlocked || confirmMutation.isPending}
                    className="hidden self-end rounded-[1.1rem] bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-50 md:block"
                  >
                    {confirmMutation.isPending
                      ? t("putaway.confirming", "Confirming...")
                      : t("putaway.confirmPutaway", "Confirm putaway")}
                  </button>
                ) : null}
              </div>

              {!confirmRecoveryState ? (
                <div className="space-y-2 md:hidden">
                  <button
                    onClick={handleMobilePrimaryAction}
                    disabled={mobilePrimaryActionDisabled}
                    data-testid="putaway-mobile-primary-action"
                    data-putaway-primary-action={!selectedDestinationId ? "use_recommended_slot" : "confirm_putaway"}
                    data-putaway-path={putawayMobilePath}
                    className="min-h-[44px] w-full rounded-[1.1rem] bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.12em] text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {mobilePrimaryActionLabel}
                  </button>
                </div>
              ) : null}
                </>
              )}
            </div>
          ) : (
            <div className="rounded-[1.5rem] border border-[#13212c]/8 bg-[#fbf8f2] px-6 py-10 text-center">
              <AlertCircle className="mx-auto text-[#7f8d98]" size={22} />
              <p className="mt-4 text-lg font-semibold text-[#13212c]">{t("putaway.selectTaskTitle", "Select a putaway task")}</p>
            </div>
          )}
        </section>
            )}
          </section>
        </div>

        <aside className="2xl:sticky 2xl:top-4 2xl:self-start">
          <section className="rounded-[1.85rem] border border-[#13212c]/10 bg-white/88 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("putaway.queueEyebrow", "Work queue")}</p>
            <h2 className="mt-2 text-[1.35rem] font-semibold tracking-[-0.03em] text-[#13212c]">
              {t("putaway.queueTitle", "Putaway priority")}
            </h2>
            <p className="mt-3 text-sm leading-6 text-[#61717d]">
              {t("putaway.queuePriorityHint", "Work from top to bottom when staging has several putaway paths.")}
            </p>

            <div className="mt-4 space-y-4">
              <PutawayQueuePriorityGroup label={t("putaway.queuePriorityExceptions", "1. Resolve route exceptions")}>
                <PutawayQueueCard
                  title={t("putaway.queueRouteExceptions", "Route exceptions")}
                  count={routeExceptionTasks.length}
                  actionLabel={t("putaway.queueActionReviewRoutes", "Review routes")}
                  onAction={routeExceptionTasks.length > 0 ? openRouteExceptionQueue : undefined}
                />
              </PutawayQueuePriorityGroup>

              <PutawayQueuePriorityGroup label={t("putaway.queuePriorityCurrent", "2. Continue putaway")}>
                <PutawayQueueCard
                  title={t("putaway.queueContinueWork", "Open putaway tasks")}
                  count={filteredTasks.length}
                  actionLabel={t("putaway.queueActionContinue", "Continue work")}
                  onAction={filteredTasks.length > 0 ? openFirstPutawayTask : undefined}
                />
              </PutawayQueuePriorityGroup>

              <PutawayQueuePriorityGroup label={t("putaway.queuePriorityBatch", "3. Build efficient batches")}>
                <PutawayQueueCard
                  title={t("putaway.queueBatchCandidates", "Same-source batch candidates")}
                  count={batchCandidateSummary.taskCount}
                  actionLabel={t("putaway.queueActionBuildBatch", "Build batch")}
                  onAction={batchCandidateSummary.firstTaskIds.length > 0 ? openBatchCandidateQueue : undefined}
                />
              </PutawayQueuePriorityGroup>

              <PutawayQueuePriorityGroup label={t("putaway.queuePriorityAll", "4. Route overview")}>
                <PutawayQueueCard
                  title={t("putaway.queueReadyTasks", "Ready to put away")}
                  count={pendingTasksCount}
                  actionLabel={t("putaway.queueActionReviewAll", "Review all")}
                  onAction={enrichedTasks.length > 0 ? openAllPutawayWork : undefined}
                />
                <PutawayQueueCard
                  title={t("putaway.queueAgvReady", "AGV-ready routes")}
                  count={routeSummary.agv}
                />
                <PutawayQueueCard
                  title={t("putaway.queueWorkerRoutes", "Worker routes")}
                  count={routeSummary.worker + routeSummary.hybrid}
                />
              </PutawayQueuePriorityGroup>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function DestinationStepSelector({
  t,
  tree,
  value,
  unavailableLocationIds,
  onChange,
}: {
  t: (key: string, fallback?: string, values?: Record<string, string | number>) => string;
  tree: any[];
  value: SplitDestinationDraft;
  unavailableLocationIds?: Set<string>;
  onChange: (nextValue: Partial<SplitDestinationDraft>) => void;
}) {
  const activeZone = tree.find((zone) => zone.zone === value.zone) || null;
  const activeAisle = activeZone?.aisles.find((aisle: any) => aisle.aisle === value.aisle) || null;
  const activeRack = activeAisle?.racks.find((rack: any) => rack.rack === value.rack) || null;
  const activeLevel = activeRack?.levels.find((level: any) => level.level === value.level) || null;
  const activeLevelLocations = activeLevel?.locations || [];

  return (
    <div className="grid gap-3 md:grid-cols-5">
      <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
        {t("putaway.destinationZone", "Zone")}
        <select
          value={value.zone || ""}
          onChange={(e) =>
            onChange({
              zone: e.target.value,
              aisle: "",
              rack: "",
              level: "",
              locationId: "",
            })
          }
          className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
        >
          <option value="">{t("putaway.destinationZonePlaceholder", "Select zone")}</option>
          {tree.map((zone) => (
            <option key={zone.zone} value={zone.zone}>
              {zone.zone}
            </option>
          ))}
        </select>
      </label>

      <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
        {t("putaway.destinationAisle", "Aisle")}
        <select
          value={value.aisle || ""}
          onChange={(e) =>
            onChange({
              aisle: e.target.value,
              rack: "",
              level: "",
              locationId: "",
            })
          }
          disabled={!activeZone}
          className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
        >
          <option value="">{t("putaway.destinationAislePlaceholder", "Select aisle")}</option>
          {(activeZone?.aisles || []).map((aisle: any) => (
            <option key={aisle.aisle} value={aisle.aisle}>
              {aisle.aisle}
            </option>
          ))}
        </select>
      </label>

      <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
        {t("putaway.destinationRack", "Rack")}
        <select
          value={value.rack || ""}
          onChange={(e) =>
            onChange({
              rack: e.target.value,
              level: "",
              locationId: "",
            })
          }
          disabled={!activeAisle}
          className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
        >
          <option value="">{t("putaway.destinationRackPlaceholder", "Select rack")}</option>
          {(activeAisle?.racks || []).map((rack: any) => (
            <option key={rack.rack} value={rack.rack}>
              {rack.rack}
            </option>
          ))}
        </select>
      </label>

      <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
        {t("putaway.destinationLevel", "Level")}
        <select
          value={value.level || ""}
          onChange={(e) =>
            onChange({
              level: e.target.value,
              locationId: "",
            })
          }
          disabled={!activeRack}
          className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
        >
          <option value="">{t("putaway.destinationLevelPlaceholder", "Select level")}</option>
          {(activeRack?.levels || []).map((level: any) => (
            <option key={level.level} value={level.level}>
              {level.level}
            </option>
          ))}
        </select>
      </label>

      <label className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
        {t("putaway.destinationPosition", "Position")}
        <select
          value={value.locationId || ""}
          onChange={(e) => {
            const location = activeLevelLocations.find((item: any) => item.id === e.target.value);
            const parsed = parseStorageBarcode(location?.barcode);
            onChange({
              locationId: e.target.value,
              zone: parsed?.zone || value.zone || "",
              aisle: parsed?.aisle || value.aisle || "",
              rack: parsed?.rack || value.rack || "",
              level: parsed?.level || value.level || "",
            });
          }}
          disabled={!activeLevel}
          className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-3 py-3 text-sm normal-case tracking-[0] text-[#13212c] focus:border-[#7da9ff] focus:outline-none disabled:bg-[#f7f4ee] disabled:text-[#a0acb6]"
        >
          <option value="">{t("putaway.destinationPositionPlaceholder", "Select position")}</option>
          {activeLevelLocations
            .filter((location: any) => !unavailableLocationIds?.has(location.id) || location.id === value.locationId)
            .map((location: any) => {
              const parsed = parseStorageBarcode(location.barcode);
              return (
                <option key={location.id} value={location.id}>
                  {parsed?.position || location.barcode}
                </option>
              );
            })}
        </select>
      </label>
    </div>
  );
}

function PutawayQueueCard({
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
  return (
    <TaskCard
      title={title}
      meta={actionLabel}
      action={<Pill as="span">{count}</Pill>}
      onClick={onAction ? () => onAction() : undefined}
      className="bg-[#f7f4ee] hover:border-[#24507a]/20 hover:bg-[#f2f7fb]"
    />
  );
}

function PutawayQueuePriorityGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2 border-t border-[#13212c]/8 pt-3 first:border-t-0 first:pt-0">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      {children}
    </div>
  );
}

function SnapshotStat({ label, value }: { label: string; value: string | number }) {
  return (
    <MetricTile
      label={label}
      value={value}
      density="compact"
      className="rounded-[1.2rem] border-[#13212c]/8 bg-[#fbf8f2] shadow-none"
    />
  );
}

function LegendChip({ label, className }: { label: string; className: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] ${className}`}>
      {label}
    </span>
  );
}

function StepChip({
  index,
  label,
  active,
  complete,
  disabled,
}: {
  index: string;
  label: string;
  active?: boolean;
  complete?: boolean;
  disabled?: boolean;
}) {
  const tone = active
    ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
    : complete
      ? "border-[#d19009]/28 bg-[#fff7e8] text-[#8a6511]"
      : disabled
        ? "border-[#13212c]/8 bg-white text-[#a0acb6]"
        : "border-[#13212c]/10 bg-white text-[#61717d]";

  return (
    <div className={`rounded-full border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] ${tone}`}>
      <span>{index}</span>
      <span className="ml-2">{label}</span>
    </div>
  );
}

function formatTopSkuList(
  topSkus: string[],
  t: (key: string, fallback?: string, values?: Record<string, string | number>) => string
) {
  if (!topSkus || topSkus.length === 0) {
    return t("putaway.visualNoStock", "Mostly open storage");
  }
  return t("putaway.visualTopSkuList", "Common here: {skus}", { skus: topSkus.join(", ") });
}

function MiniWarehouseStrip({
  segments,
  active,
}: {
  segments: { label: string; units: number }[];
  active?: boolean;
}) {
  return (
    <div className="mt-2 rounded-[0.95rem] border border-[#13212c]/8 px-2 py-2">
      <div className={`mb-2 h-px ${active ? "bg-white/18" : "bg-[#e4ddd2]"}`} />
      <div className="flex items-end gap-1.5">
        {segments.map((segment) => (
          <div key={segment.label} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <div
              className={`w-full rounded-t-md ${active ? "bg-[#f7bf45]" : occupancyTone(segment.units)}`}
              style={{ height: `${Math.max(12, Math.min(34, 12 + segment.units / 8))}px` }}
            />
            <span className={`text-[10px] uppercase tracking-[0.12em] ${active ? "text-[#d0dbe2]" : "text-[#7f8d98]"}`}>
              {segment.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
