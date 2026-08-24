import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../shared/api/queryKeys";
import {
  adjustInventory,
  fetchActivityReport,
  fetchInventoryList,
  generateCycleCount,
  recordCycleCount,
} from "../../shared/api/inventory";
import { fetchInboundOrders } from "../../shared/api/inboundOrders";
import { fetchClientDirectory, fetchSkuDirectory } from "../../shared/api/directories";
import { fetchTasks } from "../../shared/api/tasks";
import { fetchWarehouseLocations, fetchWarehouses } from "../../shared/api/planner";
import { fetchSetupProgress } from "../../shared/api/setup";
import { getApiErrorMessage } from "../../shared/api/error-message";
import {
  fetchInventoryWorkbenchSummary,
  workbenchSummaryKeys,
} from "../../shared/api/workbenchSummaries";
import DataTable from "../../shared/components/DataTable";
import Pill from "../../shared/components/Pill";
import TaskCard from "../../shared/components/TaskCard";
import { useAuthStore } from "../../shared/hooks/useAuth";
import {
  AlertCircle,
  ArrowRight,
  Boxes,
  ChevronDown,
  Layers3,
  MapPinned,
  Radar,
  ScanSearch,
  ShieldCheck,
  Siren,
  Warehouse,
} from "lucide-react";
import { useI18n } from "../../shared/i18n";
import { checklistHref } from "../../shared/utils/checklistHref";

type InventoryView = "sku" | "location" | "client";
type InventoryFocus = "all" | "available" | "allocated" | "staging";
type InventorySkuLocationSummary = { id: string; label: string; detail: string; on_hand: number };
type InventorySortField =
  | "primary"
  | "secondary"
  | "location_label"
  | "flow_state"
  | "sku_count"
  | "location_count"
  | "on_hand"
  | "allocated"
  | "available";

const INVENTORY_SORT_FIELDS_BY_VIEW: Record<InventoryView, InventorySortField[]> = {
  sku: ["primary", "secondary", "location_label", "on_hand", "allocated", "available"],
  location: ["primary", "flow_state", "sku_count", "on_hand", "allocated", "available"],
  client: ["primary", "sku_count", "location_count", "on_hand", "allocated", "available"],
};

function getInventorySortComparable(row: any, field: InventorySortField) {
  const value = row?.[field];
  if (["sku_count", "location_count", "on_hand", "allocated", "available"].includes(field)) {
    return Number(value || 0);
  }
  return String(value || "").toLowerCase();
}

function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? value.slice(0, 12) : value;
}

function inventoryRecordKey(row: any) {
  return String(row?.id || row?.primary || "");
}

function toItems<T>(payload: any): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object" && Array.isArray(payload.items)) return payload.items as T[];
  return [];
}

function parseLocationLabel(label?: string | null) {
  if (!label) return null;
  const cleaned = label.trim().toUpperCase();
  if (cleaned.startsWith("DOCK")) {
    const parts = cleaned.split("-");
    return {
      family: "dock",
      zone: parts[0] || "DOCK",
      aisle: parts[1] || "01",
      rack: null,
      level: null,
      slot: null,
    };
  }

  const parts = cleaned.split("-");
  if (parts.length >= 5) {
    return {
      family: "rack",
      zone: parts[0],
      aisle: parts[1],
      rack: parts[2],
      level: parts[3],
      slot: parts[4],
    };
  }

  if (parts.length >= 3) {
    return {
      family: "rack",
      zone: parts[0],
      aisle: parts[1],
      rack: parts[2],
      level: parts[3] || null,
      slot: parts[4] || null,
    };
  }

  return {
    family: "other",
    zone: cleaned,
    aisle: null,
    rack: null,
    level: null,
    slot: null,
  };
}

function buildLocationGroupKey(parsed: ReturnType<typeof parseLocationLabel>) {
  if (!parsed) return "other";
  if (parsed.family === "rack") return `${parsed.zone || "?"}-${parsed.aisle || "?"}`;
  if (parsed.family === "dock") return "dock";
  return "other";
}

const ACTIVITY_TYPE_KEY: Record<string, string> = {
  receive: "inventory.activityTypeReceive",
  putaway: "inventory.activityTypePutaway",
  pick: "inventory.activityTypePick",
  pack: "inventory.activityTypePack",
  ship: "inventory.activityTypeShip",
  adjust: "inventory.activityTypeAdjust",
  move: "inventory.activityTypeMove",
  cycle_count: "inventory.activityTypeCycleCount",
  return: "inventory.activityTypeReturn",
};

const ACTIVITY_TYPE_FALLBACK: Record<string, string> = {
  receive: "Receive",
  putaway: "Putaway",
  pick: "Pick",
  pack: "Pack",
  ship: "Ship",
  adjust: "Adjust",
  move: "Move",
  cycle_count: "Cycle count",
  return: "Return",
};

function locationTypeTone(type?: string | null, isAwaitingPutaway?: boolean) {
  if (isAwaitingPutaway || type === "staging") {
    return {
      chip: "bg-[#fff1d6] text-[#b97300]",
      bar: "bg-[#f0a63a]",
      surface: "bg-[#fff9ef]",
    };
  }

  if (type === "dock") {
    return {
      chip: "bg-[#e9f1ff] text-[#3469d6]",
      bar: "bg-[#5b87e5]",
      surface: "bg-[#f6f9ff]",
    };
  }

  if (type === "blocked" || type === "quality") {
    return {
      chip: "bg-[#fdecec] text-[#b34b4b]",
      bar: "bg-[#d97070]",
      surface: "bg-[#fff7f7]",
    };
  }

  return {
    chip: "bg-[#eef3f7] text-[#61717d]",
    bar: "bg-[#13212c]",
    surface: "bg-[#fcfaf6]",
  };
}

function sortNumericCode(value?: string | null) {
  if (!value) return 0;
  const digits = String(value).replace(/\D/g, "");
  return Number(digits || "0");
}

export default function InventoryPage() {
  const { t } = useI18n();
  const { role, permissions } = useAuthStore();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [toolHint, setToolHint] = useState<"cycle" | "adjust" | null>(null);
  const [view, setView] = useState<InventoryView>("sku");
  const [focus, setFocus] = useState<InventoryFocus>("all");
  const [inventorySortField, setInventorySortField] = useState<InventorySortField>("primary");
  const [inventorySortDirection, setInventorySortDirection] = useState<"asc" | "desc">("asc");
  const [warehouseFilter, setWarehouseFilter] = useState("all");
  const [clientFilter, setClientFilter] = useState("all");
  const [locationTypeFilter, setLocationTypeFilter] = useState("all");
  const [issueFilter, setIssueFilter] = useState<"blocked" | null>(null);
  const [activityExpanded, setActivityExpanded] = useState(false);
  const [mobileDetailsExpanded, setMobileDetailsExpanded] = useState(false);
  const [mobileSelectedRecordId, setMobileSelectedRecordId] = useState<string | null>(null);
  const [locationGraphicSelection, setLocationGraphicSelection] = useState<{
    type: "group" | "location";
    key: string;
  } | null>(null);
  const [toolActionError, setToolActionError] = useState<string | null>(null);
  const [toolActionSuccess, setToolActionSuccess] = useState<string | null>(null);
  const [cycleBatch, setCycleBatch] = useState<{
    reference: string;
    warehouseId: string;
    locations: Array<{
      id: string;
      label: string;
      warehouseLabel: string;
      systemUnits: number;
      rows: Array<{ sku_id: string; sku_label: string; systemQty: number }>;
    }>;
    completedLocationIds: string[];
  } | null>(null);
  const [activeCycleLocationId, setActiveCycleLocationId] = useState<string | null>(null);
  const [cycleCountDrafts, setCycleCountDrafts] = useState<Record<string, string>>({});
  const [adjustDraft, setAdjustDraft] = useState<{ inventoryId: string; newQuantity: string; reason: string }>({
    inventoryId: "",
    newQuantity: "",
    reason: "",
  });
  const toolPanelRef = useRef<HTMLDivElement | null>(null);
  const [toolPanelPulse, setToolPanelPulse] = useState(false);
  const limit = 100;
  const inventoryQueryParams = useMemo(
    () => ({
      offset,
      limit,
      ...(warehouseFilter !== "all" ? { warehouse_id: warehouseFilter } : {}),
      ...(clientFilter !== "all" ? { client_id: clientFilter } : {}),
      ...(locationTypeFilter !== "all" ? { location_type: locationTypeFilter } : {}),
      ...(focus !== "all" ? { focus } : {}),
      ...(issueFilter ? { issue: issueFilter } : {}),
      ...(search.trim() ? { search: search.trim() } : {}),
    }),
    [clientFilter, focus, issueFilter, locationTypeFilter, offset, search, warehouseFilter]
  );

  useEffect(() => {
    setOffset(0);
  }, [clientFilter, focus, issueFilter, locationTypeFilter, search, warehouseFilter]);

  const formatActivityType = (value?: string | null) => {
    const normalized = (value || "").toLowerCase();
    if (!normalized) return t("inventory.activityTypeUnknown", "Activity");
    return t(
      ACTIVITY_TYPE_KEY[normalized] || "inventory.activityTypeUnknown",
      ACTIVITY_TYPE_FALLBACK[normalized] || normalized.toUpperCase()
    );
  };

  const formatActivityNotes = (entry: any) => {
    if (!entry?.notes) return null;
    const adjustMatch = String(entry.notes).match(/^Adjustment:\s*(-?\d+)\s*→\s*(-?\d+)\.\s*Reason:\s*(.+)$/i);
    if (adjustMatch) {
      const [, fromQty, toQty, reason] = adjustMatch;
      return t(
        "inventory.activityAdjustNote",
        "Adjustment: {from} -> {to}. Reason: {reason}",
        { from: fromQty, to: toQty, reason }
      );
    }

    const cycleMatch = String(entry.notes).match(/^Cycle count:\s*system=(-?\d+)\s+counted=(-?\d+)\s+variance=(-?\d+)$/i);
    if (cycleMatch) {
      const [, systemQty, countedQty, variance] = cycleMatch;
      return t(
        "inventory.activityCycleCountNote",
        "Cycle count: system {system}, counted {counted}, variance {variance}",
        { system: systemQty, counted: countedQty, variance }
      );
    }

    return entry.notes;
  };

  const canSeeActivity =
    role === "tenant_admin" ||
    role === "platform_admin" ||
    permissions.includes("*") ||
    permissions.includes("users.manage");

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.inventory.list(inventoryQueryParams),
    queryFn: () => fetchInventoryList(inventoryQueryParams),
  });

  const { data: inventoryWorkbenchSummary } = useQuery({
    queryKey: workbenchSummaryKeys.inventory,
    queryFn: fetchInventoryWorkbenchSummary,
  });

  const { data: warehouses = [] } = useQuery({
    queryKey: queryKeys.inventory.warehouses(),
    queryFn: () =>
      fetchWarehouses({ offset: 0, limit: 200 })
        .then((data) => toItems<any>(data))
        .catch(() => []),
  });

  const { data: tasks = [] } = useQuery({
    queryKey: queryKeys.tasks.putaway({ status: "pending", task_type: "putaway" }),
    queryFn: () =>
      fetchTasks({ status: "pending", task_type: "putaway", limit: 500 }).then((data) => toItems<any>(data)),
  });

  const { data: inboundOrders = [] } = useQuery({
    queryKey: queryKeys.inventory.inboundOrders(),
    queryFn: () =>
      fetchInboundOrders({
        offset: 0,
        limit: 500,
        statuses: "expected,arrived,receiving,putaway",
      })
        .then((data) => toItems<any>(data))
        .catch(() => []),
  });

  const { data: activity = [] } = useQuery({
    queryKey: queryKeys.inventory.activity(),
    enabled: canSeeActivity,
    queryFn: () => fetchActivityReport(7).then((data) => toItems<any>(data)),
  });

  const { data: skuDirectory = [] } = useQuery({
    queryKey: queryKeys.inventory.skuDirectory(),
    queryFn: () =>
      fetchSkuDirectory({ offset: 0, limit: 500 })
        .then((data) => toItems<any>(data))
        .catch(() => []),
  });

  const { data: clientDirectory = [] } = useQuery({
    queryKey: queryKeys.inventory.clientDirectory(),
    queryFn: () =>
      fetchClientDirectory({ offset: 0, limit: 500 })
        .then((data) => toItems<any>(data))
        .catch(() => []),
  });

  const { data: setupProgress } = useQuery({
    queryKey: queryKeys.setup.progressFor("inventory"),
    queryFn: fetchSetupProgress,
  });

  const inventory = data?.items || [];
  const total = data?.total || 0;
  const hasMore = data?.has_more || false;
  const totalIsEstimate = Boolean(data?.total_is_estimate);
  const warehouseIds = useMemo<string[]>(
    () => Array.from(new Set(inventory.map((item: any) => item.warehouse_id).filter(Boolean))) as string[],
    [inventory]
  );
  const setupSteps = setupProgress?.steps || [];
  const missingRequiredSteps = useMemo(
    () => setupSteps.filter((step: any) => ["warehouse", "locations", "client", "skus"].includes(step.name) && !step.done),
    [setupSteps]
  );
  const inventoryReady = missingRequiredSteps.length === 0;

  const { data: locationDirectory = [] } = useQuery({
    queryKey: queryKeys.inventory.locationDirectory(warehouseIds.join(",")),
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

  const warehouseMap = useMemo(
    () =>
      new Map(
        warehouses.map((warehouse: any) => [
          warehouse.id,
          {
            code: warehouse.code || shortId(warehouse.id),
            name: warehouse.name || warehouse.code || shortId(warehouse.id),
          },
        ])
      ),
    [warehouses]
  );

  const inboundOrderMap = useMemo(
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

  const locationMap = useMemo(
    () =>
      new Map(
        locationDirectory.map((location: any) => [
          location.id,
          {
            barcode: location.barcode || shortId(location.id),
            type: location.location_type,
            status: location.current_status,
            warehouse_id: location.warehouse_id,
          },
        ])
      ),
    [locationDirectory]
  );

  const skuMap = useMemo(
    () =>
      new Map(
        skuDirectory.map((sku: any) => [
          sku.id,
          {
            code: sku.sku_code || shortId(sku.id),
            name: sku.name || sku.sku_code || shortId(sku.id),
            requires_lot: Boolean(sku.requires_lot),
            requires_expiry: Boolean(sku.requires_expiry),
          },
        ])
      ),
    [skuDirectory]
  );

  const clientMap = useMemo(
    () =>
      new Map(
        clientDirectory.map((client: any) => [
          client.id,
          {
            code: client.code || shortId(client.id),
            name: client.name || client.code || shortId(client.id),
          },
        ])
      ),
    [clientDirectory]
  );

  const pendingPutawayTasks = useMemo(
    () => tasks.filter((task: any) => task.task_type === "putaway" && task.status === "pending"),
    [tasks]
  );
  const pendingPutawayLocationIds = useMemo(
    () => new Set(pendingPutawayTasks.map((task: any) => task.source_location_id).filter(Boolean)),
    [pendingPutawayTasks]
  );

  const locationTypeLabel = (type?: string | null) => {
    switch (type) {
      case "blocked":
        return t("inventory.locationTypeBlocked", "Blocked");
      case "staging":
        return t("inventory.locationTypeStaging", "Staging");
      case "dock":
        return t("inventory.locationTypeDock", "Dock");
      case "quality":
        return t("inventory.locationTypeQuality", "Quality");
      case "packing":
        return t("inventory.locationTypePacking", "Packing");
      case "charging":
        return t("inventory.locationTypeCharging", "Charging");
      case "storage":
      default:
        return t("inventory.locationTypeStorage", "Storage");
    }
  };

  const detailedInventory = useMemo(
    () =>
      inventory.map((item: any) => {
        const skuMeta = skuMap.get(item.sku_id);
        const clientMeta = clientMap.get(item.client_id);
        const locationMeta = locationMap.get(item.location_id);
        const warehouseMeta = warehouseMap.get(item.warehouse_id);
        return {
          ...item,
          sku_label: skuMeta ? `${skuMeta.code} · ${skuMeta.name}` : shortId(item.sku_id),
          sku_code: skuMeta?.code || shortId(item.sku_id),
          requires_lot: Boolean(skuMeta?.requires_lot),
          requires_expiry: Boolean(skuMeta?.requires_expiry),
          client_label: clientMeta ? `${clientMeta.name} (${clientMeta.code})` : shortId(item.client_id),
          client_name: clientMeta?.name || shortId(item.client_id),
          location_label: locationMeta?.barcode || shortId(item.location_id),
          location_type_label: locationTypeLabel(locationMeta?.type),
          warehouse_label: warehouseMeta ? `${warehouseMeta.code} · ${warehouseMeta.name}` : shortId(item.warehouse_id),
          flow_state: pendingPutawayLocationIds.has(item.location_id)
            ? t("inventory.awaitingPutaway", "Awaiting putaway")
            : item.quantity_allocated > 0
            ? t("inventory.readyForPicking", "Allocated to outbound")
            : t("inventory.sourceTruth", "Source of truth"),
          is_staging_pressure: pendingPutawayLocationIds.has(item.location_id),
        };
      }),
    [clientMap, inventory, locationMap, pendingPutawayLocationIds, skuMap, t, warehouseMap]
  );

  const stagingSpotlight = useMemo(() => {
    const grouped = new Map<string, any>();
    for (const task of pendingPutawayTasks) {
      const locationMeta = locationMap.get(task.source_location_id);
      const warehouseMeta = warehouseMap.get(task.warehouse_id);
      const orderMeta = task.reference_id ? inboundOrderMap.get(task.reference_id) : null;
      const key = task.source_location_id || task.id;
      const existing = grouped.get(key) || {
        id: key,
        barcode: locationMeta?.barcode || shortId(task.source_location_id),
        location_type: locationTypeLabel(locationMeta?.type),
        warehouse_label: warehouseMeta ? `${warehouseMeta.code} · ${warehouseMeta.name}` : shortId(task.warehouse_id),
        quantity: 0,
        order_numbers: new Set<string>(),
      };
      existing.quantity += task.quantity || 0;
      if (orderMeta?.order_number) existing.order_numbers.add(orderMeta.order_number);
      grouped.set(key, existing);
    }
    return Array.from(grouped.values()).map((row) => ({ ...row, order_numbers: Array.from(row.order_numbers) }));
  }, [inboundOrderMap, locationMap, pendingPutawayTasks, t, warehouseMap]);

  const filteredInventory = useMemo(() => {
    const term = search.trim().toLowerCase();
    return detailedInventory.filter((item: any) => {
      const matchesSearch =
        !term ||
        [
          item.sku_label,
          item.sku_code,
          item.client_label,
          item.client_name,
          item.location_label,
          item.location_id,
          item.location_type_label,
          item.warehouse_label,
          item.flow_state,
          item.lot_number,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(term));

      const matchesFocus =
        focus === "all" ||
        (focus === "available" && item.quantity_available > 0) ||
        (focus === "allocated" && item.quantity_allocated > 0) ||
        (focus === "staging" && item.is_staging_pressure);

      const matchesIssue =
        issueFilter === null ||
        (issueFilter === "blocked" &&
          (["blocked", "quality"].includes(String(locationMap.get(item.location_id)?.type || "").toLowerCase()) ||
            String(locationMap.get(item.location_id)?.status || "").toLowerCase() === "blocked"));

      const locationType = String(locationMap.get(item.location_id)?.type || "storage").toLowerCase();
      const matchesWarehouse = warehouseFilter === "all" || item.warehouse_id === warehouseFilter;
      const matchesClient = clientFilter === "all" || item.client_id === clientFilter;
      const matchesLocationType = locationTypeFilter === "all" || locationType === locationTypeFilter;
      return matchesSearch && matchesFocus && matchesIssue && matchesWarehouse && matchesClient && matchesLocationType;
    });
  }, [clientFilter, detailedInventory, focus, issueFilter, locationMap, locationTypeFilter, search, warehouseFilter]);

  const filteredInventorySkuIds = useMemo(
    () => new Set(filteredInventory.map((item: any) => item.sku_id).filter(Boolean)),
    [filteredInventory]
  );

  const filteredInventoryLocationIds = useMemo(
    () => new Set(filteredInventory.map((item: any) => item.location_id).filter(Boolean)),
    [filteredInventory]
  );

  const groupedSkuRows = useMemo(() => {
    const grouped = new Map<string, any>();
    for (const item of filteredInventory) {
      const existing = grouped.get(item.sku_id) || {
        id: item.sku_id,
        primary: item.sku_label,
        secondary: item.client_name,
        on_hand: 0,
        allocated: 0,
        available: 0,
        locations: new Map<string, InventorySkuLocationSummary>(),
        staging: 0,
      };
      existing.on_hand += item.quantity_on_hand || 0;
      existing.allocated += item.quantity_allocated || 0;
      existing.available += item.quantity_available || 0;
      const locationId = item.location_id || "unknown";
      const location = existing.locations.get(locationId) || {
        id: locationId,
        label: item.location_label || shortId(item.location_id),
        detail: [item.location_type_label, item.warehouse_label].filter(Boolean).join(" · "),
        on_hand: 0,
      };
      location.on_hand += item.quantity_on_hand || 0;
      existing.locations.set(locationId, location);
      if (item.is_staging_pressure) existing.staging += item.quantity_on_hand || 0;
      grouped.set(item.sku_id, existing);
    }
    return Array.from(grouped.values()).map((row) => {
      const locations = Array.from(row.locations.values() as IterableIterator<InventorySkuLocationSummary>).sort((a, b) => {
        const quantityDelta = (b.on_hand || 0) - (a.on_hand || 0);
        if (quantityDelta !== 0) return quantityDelta;
        return String(a.label || "").localeCompare(String(b.label || ""), undefined, {
          numeric: true,
          sensitivity: "base",
        });
      });
      const primaryLocation = locations[0] || null;
      return {
        ...row,
        locations,
        location_count: locations.length,
        location_label: primaryLocation?.label || "—",
        location_detail: primaryLocation?.detail || "",
      };
    });
  }, [filteredInventory]);

  const groupedLocationRows = useMemo(() => {
    const grouped = new Map<string, any>();
    for (const item of filteredInventory) {
      const existing = grouped.get(item.location_id) || {
        id: item.location_id,
        primary: item.location_label,
        secondary: `${item.location_type_label} · ${item.warehouse_label}`,
        location_type: locationMap.get(item.location_id)?.type || null,
        location_type_label: item.location_type_label,
        warehouse_label: item.warehouse_label,
        flow_state: item.is_staging_pressure
          ? t("inventory.awaitingPutaway", "Awaiting putaway")
          : t("inventory.locationControl", "Location control"),
        on_hand: 0,
        allocated: 0,
        available: 0,
        sku_count: new Set<string>(),
      };
      existing.on_hand += item.quantity_on_hand || 0;
      existing.allocated += item.quantity_allocated || 0;
      existing.available += item.quantity_available || 0;
      existing.sku_count.add(item.sku_id);
      grouped.set(item.location_id, existing);
    }
    return Array.from(grouped.values()).map((row) => ({
      ...row,
      sku_count: row.sku_count.size,
    }));
  }, [filteredInventory, locationMap, t]);

  const groupedClientRows = useMemo(() => {
    const grouped = new Map<string, any>();
    for (const item of filteredInventory) {
      const existing = grouped.get(item.client_id) || {
        id: item.client_id,
        primary: item.client_label,
        secondary: t("inventory.clientCount", "Client footprint"),
        on_hand: 0,
        allocated: 0,
        available: 0,
        sku_count: new Set<string>(),
        location_count: new Set<string>(),
      };
      existing.on_hand += item.quantity_on_hand || 0;
      existing.allocated += item.quantity_allocated || 0;
      existing.available += item.quantity_available || 0;
      existing.sku_count.add(item.sku_id);
      existing.location_count.add(item.location_id);
      grouped.set(item.client_id, existing);
    }
    return Array.from(grouped.values()).map((row) => ({
      ...row,
      sku_count: row.sku_count.size,
      location_count: row.location_count.size,
    }));
  }, [filteredInventory, t]);

  const tableData = useMemo(() => {
    switch (view) {
      case "location":
        return groupedLocationRows;
      case "client":
        return groupedClientRows;
      case "sku":
      default:
        return groupedSkuRows;
    }
  }, [groupedClientRows, groupedLocationRows, groupedSkuRows, view]);

  const enrichedLocationRows = useMemo(
    () =>
      groupedLocationRows.map((row: any) => {
        const parsed = parseLocationLabel(row.primary);
        return {
          ...row,
          parsed,
          groupKey: buildLocationGroupKey(parsed),
        };
      }),
    [groupedLocationRows]
  );

  const totalOnHand = useMemo(
    () =>
      inventoryWorkbenchSummary?.on_hand_units ??
      detailedInventory.reduce((sum: number, item: any) => sum + (item.quantity_on_hand || 0), 0),
    [detailedInventory, inventoryWorkbenchSummary]
  );
  const totalAllocated = useMemo(
    () =>
      inventoryWorkbenchSummary?.allocated_units ??
      detailedInventory.reduce((sum: number, item: any) => sum + (item.quantity_allocated || 0), 0),
    [detailedInventory, inventoryWorkbenchSummary]
  );
  const totalAvailable = useMemo(
    () =>
      inventoryWorkbenchSummary?.available_units ??
      detailedInventory.reduce(
        (sum: number, item: any) => sum + (item.quantity_available || 0),
        0
      ),
    [detailedInventory, inventoryWorkbenchSummary]
  );
  const stagingPressureUnits = useMemo(
    () =>
      detailedInventory
        .filter((item: any) => item.is_staging_pressure)
        .reduce((sum: number, item: any) => sum + (item.quantity_on_hand || 0), 0),
    [detailedInventory]
  );

  const stagingLocationCount = useMemo(
    () => new Set(pendingPutawayTasks.map((task: any) => task.source_location_id).filter(Boolean)).size,
    [pendingPutawayTasks]
  );

  const allocatedRowCount = useMemo(
    () => detailedInventory.filter((item: any) => item.quantity_allocated > 0).length,
    [detailedInventory]
  );

  const blockedStockUnits = useMemo(
    () =>
      detailedInventory
        .filter((item: any) => {
          const locationMeta = locationMap.get(item.location_id);
          return (
            String(locationMeta?.type || "").toLowerCase() === "quality" ||
            String(locationMeta?.status || "").toLowerCase() === "blocked"
          );
        })
        .reduce((sum: number, item: any) => sum + (item.quantity_on_hand || 0), 0),
    [detailedInventory, locationMap]
  );

  const filteredActivity = useMemo(() => {
    const term = search.trim().toLowerCase();
    return activity
      .filter((entry: any) => {
        const matchesInventoryContext =
          filteredInventorySkuIds.has(entry.sku_id) || filteredInventoryLocationIds.has(entry.location);

        const matchesSearch =
          !term ||
          [entry.type, entry.reference, entry.location, entry.sku_id]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(term));

        return matchesInventoryContext && matchesSearch;
      })
      .slice(0, 6);
  }, [activity, filteredInventoryLocationIds, filteredInventorySkuIds, search]);

  const resetInventoryControls = () => {
    setView("sku");
    setFocus("all");
    setIssueFilter(null);
    setLocationGraphicSelection(null);
    setWarehouseFilter("all");
    setClientFilter("all");
    setLocationTypeFilter("all");
    setSearch("");
  };

  const summaryCards = [
    {
      label: t("inventory.onHand", "On hand"),
      value: totalOnHand,
      tone: "bg-white/84 text-[#13212c] border-[#13212c]/10",
      detail: t("inventory.onHandDetail", "Physical units currently recorded in warehouse locations."),
      icon: Boxes,
      onClick: () => {
        resetInventoryControls();
      },
    },
    {
      label: t("inventory.availableNow", "Available now"),
      value: totalAvailable,
      tone: "bg-white/84 text-[#13212c] border-[#13212c]/10",
      detail: t("inventory.availableNowDetail", "Pickable units after allocations and damaged stock are removed."),
      icon: ShieldCheck,
      onClick: () => {
        resetInventoryControls();
        setFocus("available");
      },
    },
    {
      label: t("inventory.allocated", "Allocated"),
      value: totalAllocated,
      tone: "bg-white/84 text-[#13212c] border-[#13212c]/10",
      detail: t("inventory.allocatedDetail", "Units reserved for outbound orders or work."),
      icon: Layers3,
      onClick: () => {
        resetInventoryControls();
        setFocus("allocated");
      },
    },
    {
      label: t("inventory.stagingPressure", "Staging pressure"),
      value: stagingPressureUnits,
      tone: "bg-white/84 text-[#13212c] border-[#13212c]/10",
      detail: t("inventory.stagingPressureDetail", "On-hand units sitting in locations with open putaway work."),
      icon: Warehouse,
      onClick: () => {
        resetInventoryControls();
        setView("location");
        setFocus("staging");
      },
    },
  ];

  const tableColumns = useMemo(() => {
    const rowNumberColumn = {
      key: "__row_number",
      header: t("common.rowNumber", "No."),
      className: "w-[72px] text-[#7f8d98]",
      render: (_row: any, index: number) => index + 1,
    };

    if (view === "location") {
      return [
        rowNumberColumn,
        {
          key: "primary",
          header: t("common.location", "Location"),
          sortable: true,
          render: (row: any) => (
            <div>
              <p className="font-medium text-[#13212c]">{row.primary}</p>
              <p className="mt-1 text-xs leading-5 text-[#73818d]">{row.secondary}</p>
            </div>
          ),
        },
        { key: "flow_state", header: t("inventory.flowState", "Flow state"), sortable: true },
        { key: "sku_count", header: t("inventory.skuCount", "SKUs"), sortable: true },
        { key: "on_hand", header: t("inventory.onHand", "On hand"), className: "font-medium", sortable: true },
        { key: "allocated", header: t("inventory.allocated", "Allocated"), sortable: true },
        { key: "available", header: t("inventory.availableNow", "Available now"), className: "font-medium text-green-700", sortable: true },
      ];
    }
    if (view === "client") {
      return [
        rowNumberColumn,
        { key: "primary", header: t("common.client", "Client"), sortable: true },
        { key: "sku_count", header: t("inventory.skuCount", "SKUs"), sortable: true },
        { key: "location_count", header: t("inventory.locationCount", "Locations"), sortable: true },
        { key: "on_hand", header: t("inventory.onHand", "On hand"), className: "font-medium", sortable: true },
        { key: "allocated", header: t("inventory.allocated", "Allocated"), sortable: true },
        { key: "available", header: t("inventory.availableNow", "Available now"), className: "font-medium text-green-700", sortable: true },
      ];
    }
    return [
      rowNumberColumn,
      { key: "primary", header: t("common.sku", "SKU"), sortable: true },
      { key: "secondary", header: t("common.client", "Client"), sortable: true },
      {
        key: "location_label",
        header: t("common.location", "Location"),
        sortable: true,
        render: (row: any) => (
          <div>
            <p className="font-medium text-[#13212c]">{row.location_label}</p>
            <p className="mt-1 text-xs leading-5 text-[#73818d]">
              {row.location_count > 1
                ? t("inventory.moreLocations", "+{count} more", { count: row.location_count - 1 })
                : row.location_detail || t("inventory.singleLocation", "Single location")}
            </p>
          </div>
        ),
      },
      { key: "on_hand", header: t("inventory.onHand", "On hand"), className: "font-medium", sortable: true },
      { key: "allocated", header: t("inventory.allocated", "Allocated"), sortable: true },
      { key: "available", header: t("inventory.availableNow", "Available now"), className: "font-medium text-green-700", sortable: true },
    ];
  }, [t, view]);

  const focusChips = [
    { key: "all" as const, label: t("inventory.focusAll", "All stock") },
    { key: "available" as const, label: t("inventory.focusAvailable", "Available now") },
    { key: "allocated" as const, label: t("inventory.focusAllocated", "Allocated") },
    { key: "staging" as const, label: t("inventory.focusStaging", "Awaiting putaway") },
  ];

  const viewCards = [
    { key: "sku" as const, title: t("inventory.viewSku", "By SKU"), detail: t("inventory.viewSkuDetail", "Group stock by item to compare on-hand, allocated, and available units.") },
    { key: "location" as const, title: t("inventory.viewLocation", "By location"), detail: t("inventory.viewLocationDetail", "Group stock by storage spot to see where units sit and what still needs putaway.") },
    { key: "client" as const, title: t("inventory.viewClient", "By client"), detail: t("inventory.viewClientDetail", "Group stock by customer account to review on-hand, allocated, and available units.") },
  ];
  const activeFocusChip = focusChips.find((chip) => chip.key === focus);
  const activeIssueChip =
    issueFilter === "blocked"
      ? t("inventory.issueBlocked", "Blocked or quality")
      : null;

  const warehouseFilterOptions = useMemo(() => {
    return warehouses
      .map((warehouse: any) => [
        warehouse.id,
        `${warehouse.code || shortId(warehouse.id)} · ${warehouse.name || warehouse.code || shortId(warehouse.id)}`,
      ])
      .sort((a: any, b: any) => String(a[1]).localeCompare(String(b[1])));
  }, [warehouses]);

  const clientFilterOptions = useMemo(() => {
    return clientDirectory
      .map((client: any) => [
        client.id,
        `${client.name || client.code || shortId(client.id)}${client.code ? ` (${client.code})` : ""}`,
      ])
      .sort((a: any, b: any) => String(a[1]).localeCompare(String(b[1])));
  }, [clientDirectory]);

  const locationTypeFilterOptions = useMemo(() => {
    const grouped = new Map<string, string>([
      ["storage", locationTypeLabel("storage")],
      ["staging", locationTypeLabel("staging")],
      ["dock", locationTypeLabel("dock")],
      ["quality", locationTypeLabel("quality")],
      ["packing", locationTypeLabel("packing")],
      ["charging", locationTypeLabel("charging")],
    ]);
    for (const location of locationDirectory) {
      const type = String(location.location_type || "storage").toLowerCase();
      grouped.set(type, locationTypeLabel(type));
    }
    return Array.from(grouped.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [locationDirectory, t]);

  const activeFilterCount =
    (search.trim() ? 1 : 0) +
    (warehouseFilter !== "all" ? 1 : 0) +
    (clientFilter !== "all" ? 1 : 0) +
    (locationTypeFilter !== "all" ? 1 : 0) +
    (focus !== "all" ? 1 : 0) +
    (issueFilter ? 1 : 0) +
    (locationGraphicSelection ? 1 : 0);

  const locationGraphicGroups = useMemo(() => {
    const maxOnHand = Math.max(...enrichedLocationRows.map((row) => row.on_hand || 0), 1);
    const groups = new Map<string, any>();

    enrichedLocationRows.forEach((row: any) => {
      const parsed = row.parsed;
      const groupKey = row.groupKey;

      const groupLabel =
        parsed?.family === "rack"
          ? `${parsed.zone || "?"} / ${t("inventory.aisle", "Aisle")} ${parsed.aisle || "?"}`
          : parsed?.family === "dock"
          ? t("inventory.dockArea", "Dock area")
          : t("inventory.otherLocations", "Other locations");

      const existing = groups.get(groupKey) || {
        key: groupKey,
        label: groupLabel,
        totalUnits: 0,
        locations: [],
      };

      existing.totalUnits += row.on_hand || 0;
      existing.locations.push({
        ...row,
        intensity: Math.max(0.16, Math.min(1, (row.on_hand || 0) / maxOnHand)),
        isSelected: locationGraphicSelection?.type === "location" && locationGraphicSelection.key === row.id,
      });
      groups.set(groupKey, existing);
    });

    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        isSelected: locationGraphicSelection?.type === "group" && locationGraphicSelection.key === group.key,
        racks:
          group.key === "dock" || group.key === "other"
            ? []
            : Array.from(
                group.locations.reduce((rackMap: Map<string, any>, location: any) => {
                  const rackKey = location.parsed?.rack || "00";
                  const rack = rackMap.get(rackKey) || {
                    key: rackKey,
                    label: `${t("inventory.rack", "Rack")} ${rackKey}`,
                    levels: new Map<string, any[]>(),
                  };

                  const levelKey = location.parsed?.level || "00";
                  const levelSlots = rack.levels.get(levelKey) || [];
                  levelSlots.push(location);
                  rack.levels.set(levelKey, levelSlots);
                  rackMap.set(rackKey, rack);
                  return rackMap;
                }, new Map<string, any>()).values()
              )
                .map((rack: any) => ({
                  ...rack,
                  levels: Array.from(rack.levels.entries() as IterableIterator<[string, any[]]>)
                    .sort((a: [string, any[]], b: [string, any[]]) => sortNumericCode(b[0]) - sortNumericCode(a[0]))
                    .map(([levelKey, slots]: [string, any[]]) => ({
                      key: levelKey,
                      label: `${t("inventory.level", "Level")} ${levelKey}`,
                      slots: [...slots].sort(
                        (a: any, b: any) => sortNumericCode(a.parsed?.slot) - sortNumericCode(b.parsed?.slot)
                      ),
                    })),
                }))
                .sort((a: any, b: any) => sortNumericCode(a.key) - sortNumericCode(b.key)),
        locations: group.locations.sort((a: any, b: any) => (a.primary > b.primary ? 1 : -1)),
      }))
      .sort((a, b) => b.totalUnits - a.totalUnits);
  }, [enrichedLocationRows, locationGraphicSelection, t]);

  const locationGraphicTableRows = useMemo(() => {
    if (!locationGraphicSelection) return groupedLocationRows;
    if (locationGraphicSelection.type === "location") {
      return groupedLocationRows.filter((row: any) => row.id === locationGraphicSelection.key);
    }
    return enrichedLocationRows
      .filter((row: any) => row.groupKey === locationGraphicSelection.key)
      .map(({ parsed, groupKey, ...rest }: any) => rest);
  }, [enrichedLocationRows, groupedLocationRows, locationGraphicSelection]);

  const displayTableData = useMemo(() => {
    if (view === "location") return locationGraphicTableRows;
    return tableData;
  }, [locationGraphicTableRows, tableData, view]);

  const activeInventorySortField = INVENTORY_SORT_FIELDS_BY_VIEW[view].includes(inventorySortField)
    ? inventorySortField
    : "primary";

  const sortedDisplayTableData = useMemo(() => {
    const direction = inventorySortDirection === "asc" ? 1 : -1;
    return displayTableData
      .map((row: any, index: number) => ({ row, index }))
      .sort((a: { row: any; index: number }, b: { row: any; index: number }) => {
        const aValue = getInventorySortComparable(a.row, activeInventorySortField);
        const bValue = getInventorySortComparable(b.row, activeInventorySortField);
        if (typeof aValue === "number" || typeof bValue === "number") {
          const delta = Number(aValue || 0) - Number(bValue || 0);
          return delta === 0 ? a.index - b.index : delta * direction;
        }
        const delta = String(aValue).localeCompare(String(bValue), undefined, {
          numeric: true,
          sensitivity: "base",
        });
        return delta === 0 ? a.index - b.index : delta * direction;
      })
      .map(({ row }: { row: any }) => row);
  }, [activeInventorySortField, displayTableData, inventorySortDirection]);

  const mobileSelectedRecord = useMemo(
    () =>
      sortedDisplayTableData.find((row: any) => inventoryRecordKey(row) === mobileSelectedRecordId) ||
      sortedDisplayTableData[0] ||
      null,
    [mobileSelectedRecordId, sortedDisplayTableData]
  );
  const mobileVisibleRows = useMemo(
    () => sortedDisplayTableData.slice(0, 40),
    [sortedDisplayTableData]
  );
  const mobileRecommendedAction = !inventoryReady
    ? {
        key: "setup",
        title: t("inventory.mobileBlockedTitle", "Setup needed"),
        body: t("inventory.mobileBlockedBody", "Finish setup before counting stock."),
        question: t("inventory.mobileQuestionSetup", "Question: what setup step blocks stock control?"),
        next: t("inventory.mobileNextSetup", "Next: open setup before touching live stock."),
        label: t("inventory.mobileGoSetup", "Open setup"),
        href: missingRequiredSteps[0] ? checklistHref(missingRequiredSteps[0].name) : "/setup",
      }
    : stagingPressureUnits > 0
    ? {
        key: "staging",
        title: t("inventory.mobileStagingTitle", "Clear staging first"),
        body: t("inventory.mobileStagingBody", "{count} units are still waiting for final storage.", {
          count: stagingPressureUnits,
        }),
        question: t("inventory.mobileQuestionStaging", "Question: which staging stock is blocking storage accuracy?"),
        next: t("inventory.mobileNextStaging", "Next: open awaiting-putaway stock by location."),
        label: t("inventory.mobileOpenStaging", "Open staging stock"),
      }
    : blockedStockUnits > 0
    ? {
        key: "blocked",
        title: t("inventory.mobileBlockedStockTitle", "Review blocked stock"),
        body: t("inventory.mobileBlockedStockBody", "{count} units are in blocked or quality locations.", {
          count: blockedStockUnits,
        }),
        question: t("inventory.mobileQuestionBlocked", "Question: which blocked stock needs a recovery decision?"),
        next: t("inventory.mobileNextBlocked", "Next: show blocked stock and choose the safest record."),
        label: t("inventory.mobileOpenBlocked", "Open blocked stock"),
      }
    : totalAllocated > 0
    ? {
        key: "allocated",
        title: t("inventory.mobileAllocatedTitle", "Protect allocated stock"),
        body: t("inventory.mobileAllocatedBody", "{count} units already belong to outbound work.", {
          count: totalAllocated,
        }),
        question: t("inventory.mobileQuestionAllocated", "Question: which reserved stock should be protected from adjustment?"),
        next: t("inventory.mobileNextAllocated", "Next: review allocated rows before changing stock."),
        label: t("inventory.mobileOpenAllocated", "Open allocated stock"),
      }
    : mobileSelectedRecord
    ? {
        key: "record",
        title: t("inventory.mobileLookupTitle", "Check one record"),
        body: `${mobileSelectedRecord.primary} · ${mobileSelectedRecord.on_hand || 0} ${t("inventory.onHand", "On hand")}`,
        question: t("inventory.mobileQuestionSelected", "Question: is this the record you want to count or adjust?"),
        next: t("inventory.mobileNextCount", "Next: count this record or open details."),
        label: t("inventory.mobileStartCount", "Count this record"),
      }
    : totalAvailable > 0
    ? {
        key: "available",
        title: t("inventory.mobileLookupEmptyTitle", "Find stock"),
        body: t("inventory.mobileAvailableBody", "{count} units are available. Search or choose one row.", {
          count: totalAvailable,
        }),
        question: t("inventory.mobileQuestionLookup", "Question: which SKU, location, or client needs attention now?"),
        next: t("inventory.mobileNextSearch", "Next: search or choose the first stock row."),
        label: t("inventory.mobileOpenAvailable", "Open available stock"),
      }
    : {
        key: "empty",
        title: t("inventory.mobileLookupEmptyTitle", "Find stock"),
        body: t("inventory.mobileLookupEmptyBody", "Search a SKU, location, or client to pick the next record."),
        question: t("inventory.mobileQuestionLookup", "Question: which SKU, location, or client needs attention now?"),
        next: t("inventory.mobileNextSearch", "Next: search or choose the first stock row."),
        label: t("inventory.emptyAction", "Go to receiving"),
        href: "/receiving",
      };
  const mobileInventoryQuestion = mobileRecommendedAction.question;
  const mobileInventoryNextStep = mobileRecommendedAction.next;
  const mobileInventoryObject = mobileSelectedRecord
    ? String(mobileSelectedRecord.primary || mobileRecommendedAction.title)
    : mobileRecommendedAction.title;
  const mobileInventoryPath = ["staging", "blocked", "allocated"].includes(mobileRecommendedAction.key)
    ? "exception"
    : mobileRecommendedAction.key === "record"
      ? "record"
      : "lookup";

  useEffect(() => {
    if (!mobileSelectedRecordId) return;
    if (!sortedDisplayTableData.some((row: any) => inventoryRecordKey(row) === mobileSelectedRecordId)) {
      setMobileSelectedRecordId(null);
      setMobileDetailsExpanded(false);
    }
  }, [mobileSelectedRecordId, sortedDisplayTableData]);

  const handleInventoryHeaderClick = (key: string) => {
    const nextField = key as InventorySortField;
    if (!INVENTORY_SORT_FIELDS_BY_VIEW[view].includes(nextField)) return;
    if (activeInventorySortField === nextField) {
      setInventorySortField(nextField);
      setInventorySortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setInventorySortField(nextField);
    setInventorySortDirection("asc");
  };

  const cycleCountMutation = useMutation({
    mutationFn: async (payload: { warehouse_id: string; location_ids: string[] }) => generateCycleCount(payload),
    onSuccess: async (data: any, variables) => {
      setToolActionError(null);
      setToolActionSuccess(
        t("inventory.cycleSuccess", "Cycle count tasks created for {count} locations.").replace("{count}", String(variables.location_ids.length))
      );
      const scopedLocations = currentScopeLocations
        .filter((location) => variables.location_ids.includes(location.id))
        .map((location) => ({
          id: location.id,
          label: location.label,
          warehouseLabel: warehouseMap.get(String(location.warehouse_id || variables.warehouse_id))?.name || shortId(String(location.warehouse_id || variables.warehouse_id)),
          systemUnits: location.on_hand,
          rows: filteredInventory
            .filter((item: any) => item.location_id === location.id)
            .map((item: any) => ({
              sku_id: item.sku_id,
              sku_label: item.sku_label,
              systemQty: item.quantity_on_hand || 0,
            })),
        }));
      const nextBatch = {
        reference: data?.reference || `CC-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}`,
        warehouseId: variables.warehouse_id,
        locations: scopedLocations,
        completedLocationIds: [],
      };
      setCycleBatch(nextBatch);
      setActiveCycleLocationId(nextBatch.locations[0]?.id || null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all() }),
      ]);
    },
    onError: (error: any) => {
      setToolActionSuccess(null);
      setToolActionError(getApiErrorMessage(error, t("inventory.cycleError", "Could not create cycle count tasks.")));
    },
  });

  const adjustInventoryMutation = useMutation({
    mutationFn: async (payload: { inventory_id: string; new_quantity: number; reason: string }) => adjustInventory(payload),
    onSuccess: async (_data, variables) => {
      setToolActionError(null);
      setToolActionSuccess(
        t("inventory.adjustSuccess", "Inventory updated for the selected stock row.")
      );
      setAdjustDraft((current) => ({ ...current, newQuantity: String(variables.new_quantity), reason: "" }));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.list() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.summary() }),
        queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.inventory }),
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.activity() }),
      ]);
    },
    onError: (error: any) => {
      setToolActionSuccess(null);
      setToolActionError(getApiErrorMessage(error, t("inventory.adjustError", "Could not submit the inventory adjustment.")));
    },
  });

  const recordCycleCountMutation = useMutation({
    mutationFn: async (payload: { location_id: string; counts: Array<{ sku_id: string; counted_quantity: number }> }) =>
      recordCycleCount(payload),
    onSuccess: async (_data, variables) => {
      setToolActionError(null);
      setToolActionSuccess(t("inventory.countRecorded", "Cycle count recorded for the selected location."));
      setCycleBatch((current) =>
        current
          ? {
              ...current,
              completedLocationIds: current.completedLocationIds.includes(variables.location_id)
                ? current.completedLocationIds
                : [...current.completedLocationIds, variables.location_id],
            }
          : current
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.list() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.summary() }),
        queryClient.invalidateQueries({ queryKey: workbenchSummaryKeys.inventory }),
        queryClient.invalidateQueries({ queryKey: queryKeys.inventory.activity() }),
      ]);
    },
    onError: (error: any) => {
      setToolActionSuccess(null);
      setToolActionError(getApiErrorMessage(error, t("inventory.countRecordError", "Could not record the cycle count.")));
    },
  });

  const exceptionCards = [
    {
      key: "staging",
      title: t("inventory.exceptionStagingTitle", "Staging backlog"),
      value: stagingPressureUnits,
      meta: t("inventory.exceptionStagingMeta", "{count} source locations").replace("{count}", String(stagingLocationCount)),
      detail: t("inventory.exceptionStagingDetail", "Receiving has created stock that still needs a believable final bin."),
      icon: Warehouse,
      tone: "warning" as const,
      onClick: () => {
        setIssueFilter(null);
        setLocationGraphicSelection(null);
        setView("location");
        setFocus("staging");
        setSearch("");
      },
    },
    {
      key: "allocated",
      title: t("inventory.exceptionAllocatedTitle", "Allocated stock"),
      value: totalAllocated,
      meta: t("inventory.exceptionAllocatedMeta", "{count} rows reserved").replace("{count}", String(allocatedRowCount)),
      detail: t("inventory.exceptionAllocatedDetail", "This stock already belongs to outbound work and should be protected before any adjustment."),
      icon: Layers3,
      tone: "neutral" as const,
      onClick: () => {
        setIssueFilter(null);
        setLocationGraphicSelection(null);
        setView("sku");
        setFocus("allocated");
        setSearch("");
      },
    },
    {
      key: "blocked",
      title: t("inventory.exceptionBlockedTitle", "Blocked stock"),
      value: blockedStockUnits,
      meta: t("inventory.exceptionBlockedMeta", "stock sitting in blocked locations"),
      detail: t("inventory.exceptionBlockedDetail", "If this grows, quality holds or maintenance locations are becoming part of the inventory story."),
      icon: AlertCircle,
      tone: "danger" as const,
      onClick: () => {
        setIssueFilter("blocked");
        setLocationGraphicSelection(null);
        setView("location");
        setFocus("all");
        setSearch("");
      },
    },
  ];

  const currentScopeLocations = useMemo(() => {
    const grouped = new Map<string, { id: string; label: string; warehouse_id: string | null; on_hand: number; skuCount: Set<string> }>();
    filteredInventory.forEach((item: any) => {
      if (!item.location_id) return;
      const existing = grouped.get(item.location_id) || {
        id: item.location_id,
        label: item.location_label || shortId(item.location_id),
        warehouse_id: item.warehouse_id || null,
        on_hand: 0,
        skuCount: new Set<string>(),
      };
      existing.on_hand += item.quantity_on_hand || 0;
      existing.skuCount.add(item.sku_id);
      grouped.set(item.location_id, existing);
    });
    return Array.from(grouped.values()).map((row) => ({
      ...row,
      sku_count: row.skuCount.size,
    }));
  }, [filteredInventory]);

  const cycleScopeWarehouseId = useMemo(
    () => currentScopeLocations.find((location) => location.warehouse_id)?.warehouse_id || null,
    [currentScopeLocations]
  );

  const adjustCandidates = useMemo(
    () =>
      filteredInventory
        .slice()
        .sort((a: any, b: any) => String(a.sku_label || "").localeCompare(String(b.sku_label || "")))
        .map((item: any) => ({
          ...item,
          optionLabel: `${item.sku_label} · ${item.location_label} · ${t("inventory.onHand", "On hand")}: ${item.quantity_on_hand}`,
        })),
    [filteredInventory, t]
  );

  const selectedAdjustCandidate = useMemo(
    () => adjustCandidates.find((item: any) => item.id === adjustDraft.inventoryId) || adjustCandidates[0] || null,
    [adjustCandidates, adjustDraft.inventoryId]
  );

  const cycleScopeWarehouseIds = useMemo(
    () => Array.from(new Set(currentScopeLocations.map((location) => location.warehouse_id).filter(Boolean))),
    [currentScopeLocations]
  );

  useEffect(() => {
    if (!adjustDraft.inventoryId && selectedAdjustCandidate) {
      setAdjustDraft((current) => ({
        ...current,
        inventoryId: selectedAdjustCandidate.id,
        newQuantity: String(selectedAdjustCandidate.quantity_on_hand ?? ""),
      }));
    }
  }, [adjustDraft.inventoryId, selectedAdjustCandidate]);

  useEffect(() => {
    if (!toolHint || !inventoryReady) return;
    setToolPanelPulse(true);
    toolPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = window.setTimeout(() => setToolPanelPulse(false), 1600);
    return () => window.clearTimeout(timer);
  }, [toolHint, inventoryReady]);

  useEffect(() => {
    if (!cycleBatch) return;
    const remaining = cycleBatch.locations.filter((location) => !cycleBatch.completedLocationIds.includes(location.id));
    if (remaining.length === 0) {
      setActiveCycleLocationId(null);
      return;
    }
    if (!activeCycleLocationId || cycleBatch.completedLocationIds.includes(activeCycleLocationId)) {
      setActiveCycleLocationId(remaining[0].id);
    }
  }, [activeCycleLocationId, cycleBatch]);

  const activeCycleLocation = useMemo(
    () => cycleBatch?.locations.find((location) => location.id === activeCycleLocationId) || null,
    [activeCycleLocationId, cycleBatch]
  );

  useEffect(() => {
    if (!activeCycleLocation) return;
    setCycleCountDrafts((current) => {
      const next = { ...current };
      activeCycleLocation.rows.forEach((row) => {
        const key = `${activeCycleLocation.id}:${row.sku_id}`;
        if (next[key] === undefined) next[key] = String(row.systemQty);
      });
      return next;
    });
  }, [activeCycleLocation]);

  const openMobileCycleCount = () => {
    if (!inventoryReady || !mobileSelectedRecord) return;
    const focusedTerm = String(mobileSelectedRecord.primary || "").trim();
    if (focusedTerm) setSearch(focusedTerm);
    setToolHint("cycle");
  };

  const openMobileAdjust = () => {
    if (!inventoryReady || !mobileSelectedRecord) return;
    const selectedRecordId = String(mobileSelectedRecord.id || "");
    const matchedInventory =
      filteredInventory.find((item: any) => {
        if (view === "sku") return String(item.sku_id || "") === selectedRecordId;
        if (view === "location") return String(item.location_id || "") === selectedRecordId;
        return String(item.client_id || "") === selectedRecordId;
      }) || null;

    if (matchedInventory?.id) {
      setAdjustDraft({
        inventoryId: matchedInventory.id,
        newQuantity: String(matchedInventory.quantity_on_hand ?? ""),
        reason: "",
      });
    }
    setToolHint("adjust");
  };

  const handleMobileRecommendedAction = () => {
    switch (mobileRecommendedAction.key) {
      case "setup":
      case "empty":
        window.location.href = ("href" in mobileRecommendedAction ? mobileRecommendedAction.href : "/setup") ?? "/setup";
        return;
      case "staging":
        setIssueFilter(null);
        setLocationGraphicSelection(null);
        setView("location");
        setFocus("staging");
        setSearch("");
        setMobileDetailsExpanded(false);
        return;
      case "blocked":
        setIssueFilter("blocked");
        setLocationGraphicSelection(null);
        setView("location");
        setFocus("all");
        setSearch("");
        setMobileDetailsExpanded(false);
        return;
      case "allocated":
        setIssueFilter(null);
        setLocationGraphicSelection(null);
        setView("sku");
        setFocus("allocated");
        setSearch("");
        setMobileDetailsExpanded(false);
        return;
      case "available":
        setIssueFilter(null);
        setLocationGraphicSelection(null);
        setView("sku");
        setFocus("available");
        setSearch("");
        setMobileDetailsExpanded(false);
        return;
      case "record":
      default:
        openMobileCycleCount();
    }
  };

  const toolPanel =
    toolHint && inventoryReady ? (
      <div
        ref={toolPanelRef}
        className={`rounded-[1.35rem] border bg-white/82 px-5 py-4 shadow-[0_18px_44px_rgba(19,33,44,0.06)] transition-all duration-500 ${
          toolPanelPulse
            ? "border-[#f0a63a] ring-4 ring-[#f0a63a]/18"
            : "border-[#13212c]/10"
        }`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
              {toolHint === "cycle" ? t("inventory.cycleLabel", "Cycle count") : t("inventory.adjustLabel", "Inventory adjustment")}
            </p>
            <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
              {toolHint === "cycle"
                ? t("inventory.cycleWorkspaceTitle", "Launch a field count from the current filtered scope")
                : t("inventory.adjustWorkspaceTitle", "Adjust one live stock row from the current filtered scope")}
            </h3>
            <p className="mt-2 text-sm leading-6 text-[#61717d]">
              {toolHint === "cycle"
                ? t(
                    "inventory.cycleWorkspaceBody",
                    "Use the table below to narrow the scope first, then create one field count task for the locations now visible on this page."
                  )
                : t(
                    "inventory.adjustWorkspaceBody",
                    "Use this after a physical check. Pick one visible stock row, enter the corrected quantity, and leave a reason for the audit trail."
                  )}
            </p>
          </div>
          <button
            onClick={() => {
              setToolHint(null);
              setToolActionError(null);
              setToolActionSuccess(null);
            }}
            className="shrink-0 rounded-full border border-[#13212c]/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c]"
          >
            {t("common.close", "Close")}
          </button>
        </div>

        {toolActionSuccess ? (
          <div className="mt-4 rounded-[1rem] border border-[#b9dec1] bg-[#eff9f1] px-4 py-3 text-sm text-[#2f6b3a]">
            {toolActionSuccess}
          </div>
        ) : null}

        {toolActionError ? (
          <div className="mt-4 rounded-[1rem] border border-[#e7b3b3] bg-[#fff1f1] px-4 py-3 text-sm text-[#9a4545]">
            {toolActionError}
          </div>
        ) : null}

        {toolHint === "cycle" ? (
          <div className="mt-4 rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("inventory.cycleWorkspaceEyebrow", "Current counting scope")}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                    {t("inventory.scopeRows", "{count} visible rows").replace("{count}", String(filteredInventory.length))}
                  </span>
                  <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                    {t("inventory.scopeLocations", "{count} locations").replace("{count}", String(currentScopeLocations.length))}
                  </span>
                  {cycleScopeWarehouseIds.length === 1 ? (
                    <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                      {warehouseMap.get(String(cycleScopeWarehouseIds[0]))?.name || shortId(String(cycleScopeWarehouseIds[0]))}
                    </span>
                  ) : null}
                </div>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-[#61717d]">
                  {currentScopeLocations.length === 0
                    ? t("inventory.cycleScopeEmpty", "Nothing is visible in the current scope yet. Narrow or clear the filters first.")
                    : cycleScopeWarehouseIds.length > 1
                    ? t(
                        "inventory.cycleMultiWarehouse",
                        "The current scope spans more than one warehouse. Narrow the page to one warehouse before generating count tasks."
                      )
                    : t(
                        "inventory.cycleScopeHint",
                        "This will create count tasks for every location currently visible in the filtered scope."
                      )}
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  setToolActionError(null);
                  setToolActionSuccess(null);
                  if (cycleScopeWarehouseIds.length !== 1) {
                    setToolActionError(
                      t(
                        "inventory.cycleMultiWarehouse",
                        "The current scope spans more than one warehouse. Narrow the page to one warehouse before generating count tasks."
                      )
                    );
                    return;
                  }
                  cycleCountMutation.mutate({
                    warehouse_id: String(cycleScopeWarehouseIds[0]),
                    location_ids: currentScopeLocations.map((location) => location.id),
                  });
                }}
                disabled={currentScopeLocations.length === 0 || cycleScopeWarehouseIds.length !== 1 || cycleCountMutation.isPending}
                className="inline-flex min-h-[44px] min-w-[260px] items-center justify-center rounded-full bg-[#13212c] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#203240] disabled:cursor-not-allowed disabled:bg-[#c8ced3]"
              >
                {cycleCountMutation.isPending
                  ? t("inventory.cycleCreating", "Creating count tasks...")
                  : t("inventory.cycleCreate", "Create count tasks")}
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
            <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("inventory.adjustWorkspaceEyebrow", "Visible stock rows")}
              </p>
              <label className="mt-3 block text-sm font-medium text-[#13212c]">
                {t("inventory.adjustPickRow", "Pick the stock row you want to correct")}
              </label>
              <select
                value={selectedAdjustCandidate?.id || ""}
                onChange={(event) => {
                  const next = adjustCandidates.find((item: any) => item.id === event.target.value);
                  setAdjustDraft((current) => ({
                    ...current,
                    inventoryId: event.target.value,
                    newQuantity: String(next?.quantity_on_hand ?? ""),
                  }));
                  setToolActionError(null);
                  setToolActionSuccess(null);
                }}
                className="mt-2 min-h-[44px] w-full rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
              >
                {adjustCandidates.map((item: any) => (
                  <option key={item.id} value={item.id}>
                    {item.optionLabel}
                  </option>
                ))}
              </select>

              {selectedAdjustCandidate ? (
                <div className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-4">
                  <p className="text-sm font-semibold text-[#13212c]">{selectedAdjustCandidate.sku_label}</p>
                  <p className="mt-1 text-sm text-[#61717d]">
                    {selectedAdjustCandidate.location_label} · {selectedAdjustCandidate.warehouse_label}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                      {t("inventory.currentQuantity", "Current quantity")}: {selectedAdjustCandidate.quantity_on_hand}
                    </span>
                    <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                      {selectedAdjustCandidate.flow_state}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-[1rem] border border-dashed border-[#13212c]/12 bg-white px-4 py-4 text-sm text-[#61717d]">
                  {t("inventory.workflowNoRows", "There is no visible stock row to adjust in the current scope.")}
                </div>
              )}
            </div>

            <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-white p-4">
              <label className="block text-sm font-medium text-[#13212c]">
                {t("inventory.adjustNewQuantity", "New quantity")}
              </label>
              <input
                type="number"
                min="0"
                step="1"
                value={adjustDraft.newQuantity}
                onChange={(event) => {
                  setAdjustDraft((current) => ({ ...current, newQuantity: event.target.value }));
                  setToolActionError(null);
                  setToolActionSuccess(null);
                }}
                className="mt-2 min-h-[44px] w-full rounded-[1rem] border border-[#13212c]/10 bg-[#fcfaf6] px-4 py-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
              />

              <label className="mt-4 block text-sm font-medium text-[#13212c]">
                {t("inventory.adjustReasonLabel", "Reason")}
              </label>
              <textarea
                value={adjustDraft.reason}
                onChange={(event) => {
                  setAdjustDraft((current) => ({ ...current, reason: event.target.value }));
                  setToolActionError(null);
                  setToolActionSuccess(null);
                }}
                rows={4}
                placeholder={t("inventory.adjustReasonPlaceholder", "Explain why the live quantity is being corrected.")}
                className="mt-2 w-full rounded-[1rem] border border-[#13212c]/10 bg-[#fcfaf6] px-4 py-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
              />

              <button
                type="button"
                onClick={() => {
                  const nextQuantity = Number(adjustDraft.newQuantity);
                  if (!selectedAdjustCandidate || Number.isNaN(nextQuantity) || nextQuantity < 0 || !adjustDraft.reason.trim()) {
                    setToolActionSuccess(null);
                    setToolActionError(t("inventory.adjustValidation", "Choose one stock row, enter the corrected quantity, and leave a reason."));
                    return;
                  }
                  setToolActionError(null);
                  setToolActionSuccess(null);
                  adjustInventoryMutation.mutate({
                    inventory_id: selectedAdjustCandidate.id,
                    new_quantity: nextQuantity,
                    reason: adjustDraft.reason.trim(),
                  });
                }}
                disabled={!selectedAdjustCandidate || adjustDraft.newQuantity === "" || !adjustDraft.reason.trim() || adjustInventoryMutation.isPending}
                className="mt-5 inline-flex min-h-[44px] w-full items-center justify-center rounded-full bg-[#13212c] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#203240] disabled:cursor-not-allowed disabled:bg-[#c8ced3]"
              >
                {adjustInventoryMutation.isPending
                  ? t("inventory.adjustApplying", "Applying adjustment...")
                  : t("inventory.adjustApply", "Apply inventory adjustment")}
              </button>
            </div>
          </div>
        )}
      </div>
    ) : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[#7f8d98]">{t("inventory.eyebrow", "Stock control")}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{t("inventory.title", "Inventory")}</h1>
          <p className="mt-3 hidden max-w-3xl text-sm leading-7 text-[#61717d] sm:block">
            {t(
              "inventory.workspaceBody",
              "Use this workspace to understand what stock exists, where it sits, which demand already owns it, and what should move next."
            )}
          </p>
        </div>
      </div>

      {!inventoryReady && (
        <ReadinessGate
          eyebrow={t("inventory.readinessEyebrow", "Inventory readiness gate")}
          title={t("inventory.readinessTitle", "Finish warehouse and master data before controlling live stock")}
          body={t(
            "inventory.readinessBody",
            "Inventory control only becomes trustworthy after the warehouse, storage locations, client records, and SKU master data exist. Otherwise counts, adjustments, and availability have no reliable structure underneath them."
          )}
          nextLabel={t("inventory.readinessNext", "Next recommended step:")}
          steps={missingRequiredSteps}
          t={t}
        />
      )}

      <section className="space-y-3 md:hidden">
        <div
          className="rounded-[1.25rem] bg-[#13212c] px-4 py-4 text-[#f4efe8] shadow-[0_18px_40px_rgba(19,33,44,0.16)]"
          data-testid="inventory-mobile-primary-task"
          data-mobile-primary-contract="single-record-lookup"
          data-inventory-path={mobileInventoryPath}
        >
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#90a7b5]">
            {t("inventory.mobileLookupEyebrow", "Inventory lookup")}
          </p>
          <div className="mt-3 rounded-[0.95rem] border border-white/10 bg-white/10 px-3 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#90a7b5]">
              {t("inventory.mobileCurrentObject", "Current object")}
            </p>
            <h2 className="mt-1 break-words text-xl font-semibold" data-testid="inventory-mobile-current-object">
              {mobileInventoryObject}
            </h2>
            <p className="mt-1 text-sm leading-5 text-[#c4d1da]">
              {mobileRecommendedAction.body}
            </p>
          </div>
          <div
            className="mt-3 rounded-[0.95rem] border border-white/10 bg-white/10 px-3 py-3 text-xs leading-5 text-[#d9e2e8]"
            data-testid="inventory-mobile-current-question"
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#90a7b5]">
              {t("inventory.mobileCurrentQuestion", "Current question")}
            </p>
            <p className="mt-1 font-semibold">{mobileInventoryQuestion}</p>
            <p className="mt-1 text-[#c4d1da]">{mobileInventoryNextStep}</p>
          </div>

          <label className="mt-4 block">
            <span className="sr-only">{t("inventory.searchLabel", "Search")}</span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("inventory.search", "Search by SKU or location...")}
              className="min-h-[44px] w-full rounded-[0.95rem] border border-white/10 bg-white px-4 py-3 text-sm text-[#13212c] focus:border-[#f7bf45] focus:outline-none"
            />
          </label>

          <button
            type="button"
            onClick={handleMobileRecommendedAction}
            data-testid="inventory-mobile-recommended-action"
            data-recommended-action={mobileRecommendedAction.key}
            data-inventory-path={mobileInventoryPath}
            className="mt-3 inline-flex min-h-[44px] w-full items-center justify-center rounded-full bg-[#f4efe8] px-4 py-3 text-sm font-semibold text-[#13212c] disabled:cursor-not-allowed disabled:bg-[#75828c] disabled:text-[#d7dee4]"
          >
            {mobileRecommendedAction.label}
          </button>
        </div>

        {mobileSelectedRecord ? (
          <div className="rounded-[1.15rem] border border-[#13212c]/10 bg-white/88 p-4 shadow-[0_12px_28px_rgba(19,33,44,0.05)]">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                  {view === "location"
                    ? t("common.location", "Location")
                    : view === "client"
                    ? t("common.client", "Client")
                    : t("common.sku", "SKU")}
                </p>
                <h3 className="mt-2 break-words text-lg font-semibold text-[#13212c]">{mobileSelectedRecord.primary}</h3>
                <p className="mt-1 text-sm leading-5 text-[#61717d]">
                  {view === "sku"
                    ? mobileSelectedRecord.location_label || mobileSelectedRecord.secondary
                    : view === "location"
                    ? mobileSelectedRecord.flow_state || mobileSelectedRecord.secondary
                    : t("inventory.mobileClientStockMeta", "{count} locations", {
                        count: mobileSelectedRecord.location_count || 0,
                      })}
                </p>
              </div>
              <Pill as="span" tone="neutral">
                {mobileSelectedRecord.on_hand || 0}
              </Pill>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-[0.85rem] bg-[#f7f4ee] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#7f8d98]">{t("inventory.onHand", "On hand")}</p>
                <p className="mt-1 font-semibold text-[#13212c]">{mobileSelectedRecord.on_hand || 0}</p>
              </div>
              <div className="rounded-[0.85rem] bg-[#edf8f1] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#35724e]">{t("inventory.availableNow", "Available now")}</p>
                <p className="mt-1 font-semibold text-[#13212c]">{mobileSelectedRecord.available || 0}</p>
              </div>
              <div className="rounded-[0.85rem] bg-[#f7f4ee] px-2 py-2">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#7f8d98]">{t("inventory.allocated", "Allocated")}</p>
                <p className="mt-1 font-semibold text-[#13212c]">{mobileSelectedRecord.allocated || 0}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setMobileDetailsExpanded((value) => !value)}
              aria-expanded={mobileDetailsExpanded}
              className="mt-3 flex min-h-[44px] w-full items-center justify-between rounded-full border border-[#13212c]/10 px-4 text-sm font-semibold text-[#13212c]"
            >
              {t("inventory.mobileRecordDetails", "Record details")}
              <ChevronDown size={17} className={`transition-transform ${mobileDetailsExpanded ? "rotate-180" : ""}`} />
            </button>
            {mobileDetailsExpanded ? (
              <div className="mt-3 space-y-2 text-sm leading-6 text-[#61717d]">
                <p>{mobileSelectedRecord.secondary || mobileSelectedRecord.location_detail || mobileSelectedRecord.flow_state || "—"}</p>
                <button
                  type="button"
                  onClick={openMobileAdjust}
                  disabled={!inventoryReady}
                  className="min-h-[44px] w-full rounded-full border border-[#13212c]/10 bg-[#fcfaf6] px-4 text-sm font-semibold text-[#13212c] disabled:cursor-not-allowed disabled:bg-[#f5f1e9]"
                >
                  {t("inventory.adjust", "Adjust")}
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        <details className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84" data-testid="inventory-mobile-secondary-controls">
          <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-left text-sm font-semibold text-[#13212c]">
            <span>
              {t("inventory.mobileViewAndFilters", "View and filters")} · {activeFilterCount}
            </span>
            <ChevronDown size={17} className="shrink-0" />
          </summary>
          <div className="space-y-3 border-t border-[#13212c]/8 px-4 py-4">
            <div className="grid grid-cols-3 gap-2">
              {viewCards.map((card) => (
                <button
                  key={`mobile-view-${card.key}`}
                  type="button"
                  onClick={() => {
                    setView(card.key);
                    setIssueFilter(null);
                    setMobileDetailsExpanded(false);
                    if (card.key !== "location") setLocationGraphicSelection(null);
                  }}
                  className={`min-h-[44px] rounded-[0.95rem] border px-2 py-2 text-sm font-semibold ${
                    view === card.key
                      ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                      : "border-[#13212c]/10 bg-white text-[#13212c]"
                  }`}
                >
                  {card.title}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              {focusChips.map((chip) => (
                <button
                  key={`mobile-focus-${chip.key}`}
                  type="button"
                  onClick={() => setFocus(chip.key)}
                  className={`min-h-[36px] rounded-full px-3 text-[11px] font-semibold uppercase tracking-[0.12em] ${
                    focus === chip.key ? "bg-[#13212c] text-[#f4efe8]" : "border border-[#13212c]/10 bg-white text-[#61717d]"
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </div>
            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7f8d98]">{t("inventory.warehouseFilter", "Warehouse")}</span>
              <select
                value={warehouseFilter}
                onChange={(e) => setWarehouseFilter(e.target.value)}
                className="mt-1 min-h-[44px] w-full rounded-[0.95rem] border border-[#13212c]/10 bg-white px-3 text-sm text-[#13212c]"
              >
                <option value="all">{t("inventory.allWarehouses", "All warehouses")}</option>
                {warehouseFilterOptions.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7f8d98]">{t("inventory.clientFilter", "Client")}</span>
              <select
                value={clientFilter}
                onChange={(e) => setClientFilter(e.target.value)}
                className="mt-1 min-h-[44px] w-full rounded-[0.95rem] border border-[#13212c]/10 bg-white px-3 text-sm text-[#13212c]"
              >
                <option value="all">{t("inventory.allClients", "All clients")}</option>
                {clientFilterOptions.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={resetInventoryControls}
              className="min-h-[44px] w-full rounded-full border border-[#13212c]/10 bg-[#fcfaf6] px-4 text-sm font-semibold text-[#13212c]"
            >
              {t("inventory.clearFilters", "Clear filters")}
            </button>
          </div>
        </details>

        <details className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/78" data-testid="inventory-mobile-record-list">
          <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-left text-sm font-semibold text-[#13212c]">
            <span>{t("inventory.mobileChooseAnotherRecord", "Choose another record")}</span>
            <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              {t("inventory.mobileRowsCount", "{count} rows", { count: sortedDisplayTableData.length })}
            </span>
          </summary>
          <div className="max-h-[42vh] space-y-2 overflow-y-auto border-t border-[#13212c]/8 px-3 py-3">
            {isLoading ? (
              <div className="rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-6 text-center text-sm text-[#7f8e98]">
                {t("common.loading", "Loading...")}
              </div>
            ) : sortedDisplayTableData.length === 0 ? (
              <div className="rounded-[1rem] border border-[#13212c]/10 bg-white px-4 py-5 text-sm text-[#61717d]">
                <p className="font-semibold text-[#13212c]">{t("inventory.empty", "No inventory found")}</p>
                <p className="mt-2 leading-6">
                  {t("inventory.emptyHint", "Inventory appears after receiving and putaway create real stock in real locations.")}
                </p>
              </div>
            ) : (
              mobileVisibleRows.map((row: any, index: number) => {
                const rowKey = inventoryRecordKey(row);
                const selected = rowKey === inventoryRecordKey(mobileSelectedRecord);
                return (
                  <button
                    key={`${rowKey}-${index}`}
                    type="button"
                    onClick={() => {
                      setMobileSelectedRecordId(rowKey);
                      setMobileDetailsExpanded(false);
                    }}
                    className={`min-h-[64px] w-full rounded-[0.95rem] border px-3 py-3 text-left ${
                      selected ? "border-[#13212c] bg-[#eef2f5]" : "border-[#13212c]/8 bg-white"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-[#13212c]">{row.primary}</p>
                        <p className="mt-1 truncate text-xs text-[#61717d]">
                          {view === "sku"
                            ? row.location_label || row.secondary
                            : view === "location"
                            ? row.flow_state || row.secondary
                            : t("inventory.mobileClientStockMeta", "{count} locations", { count: row.location_count || 0 })}
                        </p>
                      </div>
                      <span className="shrink-0 rounded-full bg-[#f7f4ee] px-2.5 py-1 text-xs font-semibold text-[#13212c]">
                        {row.on_hand || 0}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </details>
      </section>

      <section className="hidden grid-cols-2 gap-3 sm:gap-4 md:grid xl:grid-cols-5">
        {summaryCards.map(({ label, value, tone, detail, icon: Icon, onClick }) => (
          <button
            key={label}
            onClick={onClick}
            className={`rounded-[1.35rem] border p-4 text-left shadow-[0_18px_44px_rgba(19,33,44,0.06)] transition hover:-translate-y-0.5 sm:rounded-[1.8rem] sm:p-5 ${tone}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] opacity-70">{label}</p>
                <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] sm:mt-3 sm:text-3xl">{value}</p>
              </div>
              <div className="hidden rounded-2xl border border-current/15 bg-white/10 p-2.5 sm:block">
                <Icon size={18} />
              </div>
            </div>
            <p className="mt-3 hidden text-sm leading-6 opacity-80 sm:block">{detail}</p>
          </button>
        ))}
      </section>

      <section
        className={`space-y-4 rounded-[1.25rem] border border-[#13212c]/8 bg-white/45 p-3 shadow-[0_24px_64px_rgba(19,33,44,0.08)] backdrop-blur md:block md:rounded-[2.2rem] md:p-4 ${
          toolHint || cycleBatch ? "block" : "hidden"
        }`}
      >
        <div className="hidden md:block">
          <div className="space-y-4">
            <div className="overflow-hidden rounded-[1.85rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_58%,#253847_100%)] p-5 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-2xl">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-[#90a7b5]">{t("inventory.map", "Inventory map")}</p>
                  <h2 className="mt-3 text-xl font-semibold tracking-[-0.03em] sm:text-2xl">
                    {t("inventory.mapBody", "Treat this page as the control layer for stock position, allocation pressure, and location confidence.")}
                  </h2>
                </div>
                <div className="rounded-full border border-[#f7bf45]/28 bg-[#f7bf45]/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">
                  {activeFocusChip?.label || t("inventory.focusAll", "All stock")}
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {viewCards.map((card) => (
                  <button
                    key={card.key}
                    onClick={() => {
                      setView(card.key);
                      setIssueFilter(null);
                      if (card.key !== "location") setLocationGraphicSelection(null);
                    }}
                    className={`rounded-[1.15rem] border p-4 text-left transition ${
                      view === card.key ? "border-[#f7bf45]/45 bg-[#f7bf45]/12" : "border-white/10 bg-white/5 hover:bg-white/8"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-[#f4efe8]">{card.title}</p>
                      {view === card.key && <ScanSearch size={16} className="text-[#f7bf45]" />}
                    </div>
                    <p className="mt-2 hidden text-sm leading-6 text-[#c5d2db] sm:block">{card.detail}</p>
                  </button>
                ))}
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {focusChips.map((chip) => (
                  <button
                    key={chip.key}
                    onClick={() => setFocus(chip.key)}
                    className={`rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] transition ${
                      focus === chip.key ? "bg-[#f7bf45] text-[#13212c]" : "border border-white/12 bg-white/5 text-[#d6e0e6] hover:bg-white/8"
                    }`}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            </div>

            {stagingSpotlight.length > 0 && (
              <details className="rounded-[1.35rem] border border-[#13212c]/8 bg-white/82">
                <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-[#13212c]">
                  {t("inventory.stagingSpotlight", "Staging spotlight")} · {stagingPressureUnits} {t("common.qty", "Qty")}
                </summary>
                <div className="grid gap-3 border-t border-[#13212c]/8 px-4 py-4 lg:grid-cols-2">
                  {stagingSpotlight.map((row: any) => (
                    <div key={row.id} className="rounded-[1rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[#13212c]">{row.barcode}</p>
                          <p className="mt-1 text-xs uppercase tracking-[0.16em] text-[#7f8d98]">
                            {row.location_type} · {row.warehouse_label}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-lg font-semibold text-[#13212c]">{row.quantity}</p>
                          <p className="mt-1 text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                            {t("inventory.awaitingPutaway", "Awaiting putaway")}
                          </p>
                        </div>
                      </div>
                      {row.order_numbers.length > 0 && (
                        <p className="mt-3 text-sm leading-6 text-[#61717d]">
                          {t("inventory.stagingRelatedOrders", "Related inbound orders")}: {row.order_numbers.join(", ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>

        </div>

        <div className="pt-1">
          <div className="hidden rounded-[1.25rem] border border-[#13212c]/8 bg-white/78 p-4 md:block">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">{t("inventory.filtersTitle", "Count scope filters")}</p>
                <p className="mt-1 text-sm leading-6 text-[#61717d]">
                  {t("inventory.filtersHint", "Narrow the rows first. Cycle Count will use exactly this visible scope.")}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1">
                  {t("inventory.paginationShowing", "Showing {start}–{end} of {total}")
                    .replace("{start}", displayTableData.length === 0 ? "0" : "1")
                    .replace("{end}", String(displayTableData.length))
                    .replace("{total}", String(displayTableData.length))}
                </span>
                <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1">
                  {t("inventory.activeFilters", "{count} filters active").replace("{count}", String(activeFilterCount))}
                </span>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <label className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">{t("inventory.warehouseFilter", "Warehouse")}</span>
                <select
                  value={warehouseFilter}
                  onChange={(e) => setWarehouseFilter(e.target.value)}
                  className="h-11 w-full rounded-full border border-[#13212c]/10 bg-white px-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                >
                  <option value="all">{t("inventory.allWarehouses", "All warehouses")}</option>
                  {warehouseFilterOptions.map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">{t("inventory.clientFilter", "Client")}</span>
                <select
                  value={clientFilter}
                  onChange={(e) => setClientFilter(e.target.value)}
                  className="h-11 w-full rounded-full border border-[#13212c]/10 bg-white px-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                >
                  <option value="all">{t("inventory.allClients", "All clients")}</option>
                  {clientFilterOptions.map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">{t("inventory.locationTypeFilter", "Location type")}</span>
                <select
                  value={locationTypeFilter}
                  onChange={(e) => setLocationTypeFilter(e.target.value)}
                  className="h-11 w-full rounded-full border border-[#13212c]/10 bg-white px-3 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                >
                  <option value="all">{t("inventory.allLocationTypes", "All location types")}</option>
                  {locationTypeFilterOptions.map(([type, label]) => (
                    <option key={type} value={type}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7f8d98]">{t("inventory.searchLabel", "Search")}</span>
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("inventory.search", "Search by SKU or location...")}
                  className="h-11 w-full rounded-full border border-[#13212c]/10 bg-white px-4 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                />
              </label>
            </div>

            <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap gap-2">
                {activeIssueChip ? (
                  <Pill as="span" tone="warning">
                    {activeIssueChip}
                  </Pill>
                ) : null}
                {locationGraphicSelection ? (
                  <Pill as="span" tone="active">
                    {t("inventory.graphicFilterActive", "Map filter active")}
                  </Pill>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2 lg:justify-end">
                <button
                  type="button"
                  onClick={() => inventoryReady && setToolHint("cycle")}
                  disabled={!inventoryReady}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-full bg-[#13212c] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#203240] disabled:cursor-not-allowed disabled:bg-[#c8ced3]"
                >
                  {t("inventory.cycleCount", "Cycle Count")}
                </button>
                <button
                  type="button"
                  onClick={() => inventoryReady && setToolHint("adjust")}
                  disabled={!inventoryReady}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-[#13212c]/10 bg-white px-4 py-2.5 text-sm font-medium text-[#13212c] transition hover:bg-[#f7f4ee] disabled:cursor-not-allowed disabled:bg-[#f5f1e9] disabled:text-[#9aa7b2]"
                >
                  {t("inventory.adjust", "Adjust")}
                </button>
                <button
                  type="button"
                  onClick={resetInventoryControls}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-[#13212c]/10 bg-[#fcfaf6] px-4 py-2.5 text-sm font-semibold text-[#13212c] transition hover:bg-white"
                >
                  {t("inventory.clearFilters", "Clear filters")}
                </button>
              </div>
            </div>
          </div>

        {toolHint === "cycle" ? (
          <div className="mt-4 hidden rounded-[1.2rem] border border-[#f0cf9d] bg-[#fff7ea] px-4 py-3 text-sm leading-6 text-[#7d6841] md:block">
            {t(
              "inventory.cycleScopeControlHint",
              "Cycle Count will use the inventory rows currently shown. Change the view, filter, or search first if you want to count a different set of stock."
            )}
          </div>
        ) : null}

        {toolPanel ? <div className="mt-4">{toolPanel}</div> : null}

        {cycleBatch ? (
          <section className="mt-4 rounded-[1.2rem] border border-[#d8e1e8] bg-white px-4 py-4 shadow-[0_12px_28px_rgba(19,33,44,0.05)]">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                  {t("inventory.cycleNextLabel", "Next step")}
                </p>
                <h3 className="mt-2 text-lg font-semibold text-[#13212c]">
                  {t("inventory.cycleExecutionTitle", "Work through the cycle count tasks you just created")}
                </h3>
                <p className="mt-1 text-sm leading-6 text-[#61717d]">
                  {t(
                    "inventory.cycleExecutionBody",
                    "Pick one location below, enter the counted quantity for each SKU, then submit the count. The workflow will move to the next location automatically."
                  )}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                  {t("inventory.cycleReference", "Reference")}: {cycleBatch.reference}
                </span>
                <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                  {t("inventory.cycleCompleted", "{count} locations completed").replace("{count}", String(cycleBatch.completedLocationIds.length))}
                </span>
              </div>
            </div>

            {cycleBatch.locations.length === 0 ? (
              <div className="mt-4 rounded-[1rem] border border-dashed border-[#13212c]/10 bg-[#fcfaf6] px-4 py-4 text-sm text-[#61717d]">
                {t("inventory.cycleNoLocations", "No countable locations were captured in this batch. Adjust the scope and try again.")}
              </div>
            ) : cycleBatch.completedLocationIds.length === cycleBatch.locations.length ? (
              <div className="mt-4 rounded-[1rem] border border-[#b9dec1] bg-[#eff9f1] px-4 py-4">
                <p className="text-sm font-semibold text-[#2f6b3a]">{t("inventory.cycleAllDoneTitle", "This batch is fully counted.")}</p>
                <p className="mt-1 text-sm leading-6 text-[#477353]">
                  {t("inventory.cycleAllDoneBody", "You can build another count batch from a different scope, or keep reviewing inventory from this page.")}
                </p>
                <button
                  type="button"
                  onClick={() => setToolHint("cycle")}
                  className="mt-3 inline-flex min-h-[42px] items-center justify-center rounded-full border border-[#2f6b3a]/20 bg-white px-4 py-2 text-sm font-semibold text-[#2f6b3a] transition hover:bg-[#f7fff8]"
                >
                  {t("inventory.countBuildAnother", "Build another count batch")}
                </button>
              </div>
            ) : (
              <div className="mt-4 grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
                <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] p-3">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                    {t("inventory.cycleLocationQueue", "Location queue")}
                  </p>
                  <div className="mt-3 space-y-2">
                    {cycleBatch.locations.map((location) => {
                      const isDone = cycleBatch.completedLocationIds.includes(location.id);
                      const isActive = activeCycleLocationId === location.id;
                      return (
                        <button
                          key={location.id}
                          type="button"
                          onClick={() => setActiveCycleLocationId(location.id)}
                          className={`w-full rounded-[0.95rem] border px-3 py-3 text-left transition ${
                            isActive ? "border-[#13212c] bg-[#eef2f5]" : "border-[#13212c]/8 bg-white hover:bg-[#f7f4ee]"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-[#13212c]">{location.label}</p>
                              <p className="mt-1 text-xs leading-5 text-[#7f8d98]">
                                {location.rows.length} {t("inventory.skuCount", "SKUs")} · {location.systemUnits} {t("inventory.onHand", "On hand")}
                              </p>
                            </div>
                            <span
                              className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                                isDone ? "bg-[#eff9f1] text-[#2f6b3a]" : "bg-[#fff4e2] text-[#8f5f00]"
                              }`}
                            >
                              {isDone ? t("common.done", "Done") : t("inventory.pendingShort", "Pending")}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] p-4">
                  {activeCycleLocation ? (
                    <>
                      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                            {t("inventory.cycleCurrentLocation", "Current location")}
                          </p>
                          <h4 className="mt-2 text-lg font-semibold text-[#13212c]">{activeCycleLocation.label}</h4>
                          <p className="mt-1 text-sm leading-6 text-[#61717d]">{activeCycleLocation.warehouseLabel}</p>
                        </div>
                        <div className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                          {activeCycleLocation.systemUnits} {t("inventory.onHand", "On hand")}
                        </div>
                      </div>

                      <div className="mt-4 space-y-3">
                        {activeCycleLocation.rows.map((row) => {
                          const draftKey = `${activeCycleLocation.id}:${row.sku_id}`;
                          return (
                            <div key={draftKey} className="rounded-[0.95rem] border border-[#13212c]/8 bg-white px-4 py-3">
                              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px] lg:items-end">
                                <div>
                                  <p className="text-sm font-semibold text-[#13212c]">{row.sku_label}</p>
                                </div>
                                <div>
                                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
                                    {t("inventory.systemQuantity", "System quantity")}
                                  </p>
                                  <p className="mt-2 text-lg font-semibold text-[#13212c]">{row.systemQty}</p>
                                </div>
                                <label className="text-sm">
                                  <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7f8d98]">
                                    {t("inventory.countedQuantity", "Counted quantity")}
                                  </span>
                                  <input
                                    type="number"
                                    min="0"
                                    step="1"
                                    value={cycleCountDrafts[draftKey] ?? String(row.systemQty)}
                                    onChange={(event) =>
                                      setCycleCountDrafts((current) => ({
                                        ...current,
                                        [draftKey]: event.target.value,
                                      }))
                                    }
                                    className="w-full rounded-[0.9rem] border border-[#13212c]/10 bg-[#fcfaf6] px-3 py-2.5 text-sm text-[#13212c] focus:border-[#7da9ff] focus:outline-none"
                                  />
                                </label>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            const counts = activeCycleLocation.rows.map((row) => ({
                              sku_id: row.sku_id,
                              counted_quantity: Number(cycleCountDrafts[`${activeCycleLocation.id}:${row.sku_id}`] ?? row.systemQty),
                            }));
                            if (counts.some((item) => Number.isNaN(item.counted_quantity) || item.counted_quantity < 0)) {
                              setToolActionSuccess(null);
                              setToolActionError(t("inventory.countValidation", "Enter a valid counted quantity for every SKU before submitting this location."));
                              return;
                            }
                            setToolActionError(null);
                            setToolActionSuccess(null);
                            recordCycleCountMutation.mutate({
                              location_id: activeCycleLocation.id,
                              counts,
                            });
                          }}
                          disabled={recordCycleCountMutation.isPending}
                          className="inline-flex min-h-[44px] items-center justify-center rounded-full bg-[#13212c] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#203240] disabled:cursor-not-allowed disabled:bg-[#c8ced3]"
                        >
                          {recordCycleCountMutation.isPending
                            ? t("inventory.countSubmitting", "Submitting count...")
                            : t("inventory.countSubmit", "Submit count")}
                        </button>
                      </div>
                    </>
                  ) : null}
                </div>
              </div>
            )}
          </section>
        ) : null}
        {view === "location" && locationGraphicGroups.length > 0 && (
          <section className="mt-5 hidden rounded-[1.6rem] border border-[#13212c]/8 bg-[#fbf8f2] p-4 md:block">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-[0.2em] text-[#7f8d98]">{t("inventory.locationGraphic", "Location graphic")}</p>
                <h3 className="mt-2 flex items-center gap-2 text-lg font-semibold text-[#13212c]">
                  <MapPinned size={18} />
                  {t("inventory.locationGraphicTitle", "Read the warehouse by aisle and rack before reading rows")}
                </h3>
                <p className="mt-1 text-sm leading-6 text-[#61717d]">
                  {t("inventory.locationGraphicBody", "Each tile is one location. Darker bars indicate more stock on hand so you can spot pressure and empty capacity faster.")}
                </p>
              </div>
              <div className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-[#61717d]">
                {t("inventory.locationGraphicLegend", "Bar = on hand pressure")}
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[#7f8d98]">
              <span className="rounded-full bg-[#f6f9ff] px-2.5 py-1 text-[#3469d6]">{t("inventory.dockArea", "Dock area")}</span>
              <span className="rounded-full bg-[#fff9ef] px-2.5 py-1 text-[#b97300]">{t("inventory.awaitingPutaway", "Awaiting putaway")}</span>
              <span className="rounded-full bg-[#fcfaf6] px-2.5 py-1 text-[#61717d]">{t("inventory.locationTypeStorage", "Storage")}</span>
              {locationGraphicSelection ? (
                <button
                  type="button"
                  onClick={() => setLocationGraphicSelection(null)}
                  className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[#13212c]"
                >
                  {t("inventory.clearGraphicSelection", "Clear graphic filter")}
                </button>
              ) : null}
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              {locationGraphicGroups.map((group: any) => (
                <div
                  key={group.key}
                  className={`rounded-[1.3rem] border px-4 py-4 transition ${
                    group.isSelected ? "border-[#13212c] bg-[#f6efe0]" : "border-[#13212c]/8 bg-white"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-[#13212c]">{group.label}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7f8d98]">
                        {group.locations.length} {t("inventory.locationCount", "Locations")} · {group.totalUnits} {t("inventory.onHand", "On hand")}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setLocationGraphicSelection((current) =>
                          current?.type === "group" && current.key === group.key ? null : { type: "group", key: group.key }
                        )
                      }
                      className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                        group.isSelected ? "bg-[#13212c] text-[#f4efe8]" : "border border-[#13212c]/10 bg-white text-[#13212c]"
                      }`}
                    >
                      {group.isSelected ? t("common.selected", "Selected") : t("common.select", "Select")}
                    </button>
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    {group.racks.length > 0 ? (
                      <div className="sm:col-span-2 rounded-[1.1rem] border border-[#13212c]/8 bg-[#f8f3ea] p-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-[#7f8d98]">
                          {t("inventory.rackPlan", "Rack plan")}
                        </p>
                        <div className="mt-3 grid gap-3 lg:grid-cols-2">
                          {group.racks.map((rack: any) => (
                            <div key={rack.key} className="rounded-[1rem] border border-[#13212c]/8 bg-white p-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#61717d]">{rack.label}</p>
                              <div className="mt-3 space-y-2">
                                {rack.levels.map((level: any) => (
                                  <div key={level.key} className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#fcfaf6] px-2.5 py-2.5">
                                    <div className="flex items-center justify-between gap-2">
                                      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7f8d98]">{level.label}</p>
                                      <span className="text-[10px] uppercase tracking-[0.12em] text-[#9aa5ae]">
                                        {level.slots.length} {t("inventory.slot", "Slot")}
                                      </span>
                                    </div>
                                    <div className="mt-2 flex flex-wrap gap-2">
                                      {level.slots.map((location: any) => (
                                        <button
                                          type="button"
                                          key={`${rack.key}-${level.key}-${location.id}-plan`}
                                          onClick={() =>
                                            setLocationGraphicSelection((current) =>
                                              current?.type === "location" && current.key === location.id
                                                ? null
                                                : { type: "location", key: location.id }
                                            )
                                          }
                                          className={`min-w-[78px] rounded-[0.8rem] border px-2 py-2 text-left transition ${
                                            location.isSelected ? "border-[#13212c] bg-[#eef2f5]" : "border-[#13212c]/8 bg-white"
                                          }`}
                                        >
                                          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#13212c]">
                                            {t("inventory.slot", "Slot")} {location.parsed?.slot || "—"}
                                          </p>
                                          <div className="mt-1.5 h-1.5 rounded-full bg-[#e7e0d3]">
                                            <div
                                              className={`h-1.5 rounded-full ${
                                                locationTypeTone(
                                                  location.location_type,
                                                  location.flow_state === t("inventory.awaitingPutaway", "Awaiting putaway")
                                                ).bar
                                              }`}
                                              style={{ width: `${location.intensity * 100}%`, opacity: location.intensity }}
                                            />
                                          </div>
                                          <p className="mt-1.5 text-[11px] font-semibold text-[#13212c]">{location.on_hand}</p>
                                        </button>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {group.locations.map((location: any) => (
                      <button
                        type="button"
                        key={location.id}
                        onClick={() =>
                          setLocationGraphicSelection((current) =>
                            current?.type === "location" && current.key === location.id ? null : { type: "location", key: location.id }
                          )
                        }
                        className={`rounded-[1.1rem] border px-3 py-3 text-left transition ${
                          location.isSelected ? "border-[#13212c] bg-[#eef2f5]" : "border-[#13212c]/8"
                        } ${
                          locationTypeTone(
                            location.location_type,
                            location.flow_state === t("inventory.awaitingPutaway", "Awaiting putaway")
                          ).surface
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-[#13212c]">{location.primary}</p>
                            <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7f8d98]">
                              {location.parsed?.family === "rack"
                                ? `${t("inventory.rack", "Rack")} ${location.parsed?.rack || "—"} · ${t("inventory.level", "Level")} ${location.parsed?.level || "—"} · ${t("inventory.slot", "Slot")} ${location.parsed?.slot || "—"}`
                                : location.secondary}
                            </p>
                          </div>
                          <div
                            className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                              locationTypeTone(
                                location.location_type,
                                location.flow_state === t("inventory.awaitingPutaway", "Awaiting putaway")
                              ).chip
                            }`}
                          >
                            {location.flow_state}
                          </div>
                        </div>

                        <div className="mt-3 h-2 rounded-full bg-[#e7e0d3]">
                          <div
                            className={`h-2 rounded-full ${
                              locationTypeTone(
                                location.location_type,
                                location.flow_state === t("inventory.awaitingPutaway", "Awaiting putaway")
                              ).bar
                            }`}
                            style={{ width: `${location.intensity * 100}%`, opacity: location.intensity }}
                          />
                        </div>

                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-[#61717d]">
                          <div>
                            <p className="uppercase tracking-[0.12em] text-[#8a97a2]">{t("inventory.onHand", "On hand")}</p>
                            <p className="mt-1 font-semibold text-[#13212c]">{location.on_hand}</p>
                          </div>
                          <div>
                            <p className="uppercase tracking-[0.12em] text-[#8a97a2]">{t("inventory.skuCount", "SKUs")}</p>
                            <p className="mt-1 font-semibold text-[#13212c]">{location.sku_count}</p>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="mt-5 hidden md:block">
          <div className="space-y-2 md:hidden">
            <div className="flex items-center justify-between gap-3 px-1">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                {t("inventory.mobileStockQueueEyebrow", "Stock list")}
              </p>
              <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
                {t("inventory.mobileRowsCount", "{count} rows", { count: sortedDisplayTableData.length })}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {tableColumns
                .filter((column) => "sortable" in column && column.sortable)
                .slice(0, 5)
                .map((column) => (
                  <button
                    key={`mobile-inventory-sort-${column.key}`}
                    type="button"
                    onClick={() => handleInventoryHeaderClick(column.key)}
                    className={`inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] ${
                      activeInventorySortField === column.key
                        ? "border-[#13212c] bg-[#13212c] text-[#f4efe8]"
                        : "border-[#13212c]/10 bg-white text-[#61717d]"
                    }`}
                  >
                    <span>{column.header}</span>
                    <span>{activeInventorySortField === column.key ? (inventorySortDirection === "asc" ? "↑" : "↓") : "↕"}</span>
                  </button>
                ))}
            </div>
            {isLoading ? (
              <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white/80 px-4 py-6 text-center text-sm text-[#7f8e98]">
                {t("common.loading", "Loading...")}
              </div>
            ) : sortedDisplayTableData.length === 0 ? (
              <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white/80 px-4 py-6 text-sm text-[#61717d]">
                <p className="font-semibold text-[#13212c]">{t("inventory.empty", "No inventory found")}</p>
                <p className="mt-2 leading-6">
                  {t("inventory.emptyHint", "Inventory appears after receiving and putaway create real stock in real locations.")}
                </p>
                <a
                  href="/receiving"
                  className="mt-4 inline-flex min-h-[40px] items-center justify-center rounded-full bg-[#13212c] px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#f4efe8]"
                >
                  {t("inventory.emptyAction", "Go to receiving")}
                </a>
              </div>
            ) : (
              sortedDisplayTableData.map((row: any, index: number) => (
                <TaskCard
                  key={`${row.id || row.primary}-${index}`}
                  label={
                    view === "location"
                      ? t("common.location", "Location")
                      : view === "client"
                        ? t("common.client", "Client")
                        : t("common.sku", "SKU")
                  }
                  title={row.primary}
                  meta={
                    view === "sku"
                      ? row.location_label || row.secondary
                      : view === "location"
                        ? row.flow_state || row.secondary
                        : t("inventory.mobileClientStockMeta", "{count} locations", {
                            count: row.location_count || 0,
                          })
                  }
                  chips={
                    <>
                      <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#61717d]">
                        {t("inventory.onHand", "On hand")}: {row.on_hand || 0}
                      </span>
                      <span className="rounded-full border border-[#9ed4b7]/45 bg-[#edf8f1] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#1b5f38]">
                        {t("inventory.availableNow", "Available now")}: {row.available || 0}
                      </span>
                      {Number(row.allocated || 0) > 0 ? (
                        <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#61717d]">
                          {t("inventory.allocated", "Allocated")}: {row.allocated}
                        </span>
                      ) : null}
                    </>
                  }
                />
              ))
            )}
          </div>

          <div className="hidden md:block">
            <DataTable
              columns={tableColumns}
              data={sortedDisplayTableData}
              loading={isLoading}
              emptyMessage={t("inventory.empty", "No inventory found")}
              emptyHint={t("inventory.emptyHint", "Inventory appears after receiving and putaway create real stock in real locations.")}
              emptyActionLabel={t("inventory.emptyAction", "Go to receiving")}
              emptyActionHref="/receiving"
              onHeaderClick={handleInventoryHeaderClick}
              sortField={activeInventorySortField}
              sortDirection={inventorySortDirection}
            />
          </div>
        </div>
        </div>
      </section>

      <section className="hidden rounded-[1.6rem] border border-[#13212c]/10 bg-white/70 px-4 py-4 md:block">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
              <Siren size={18} />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("inventory.exceptionTitle", "Exception queue")}</p>
              <h2 className="mt-1 text-base font-semibold text-[#13212c]">{t("inventory.exceptionSubtitle", "Prioritize the stock stories that need intervention first")}</h2>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {exceptionCards.map((card) => (
              <TaskCard
                key={card.key}
                title={card.title}
                meta={card.meta}
                tone={card.tone}
                selected={
                  (card.key === "staging" && focus === "staging") ||
                  (card.key === "allocated" && focus === "allocated") ||
                  (card.key === "blocked" && issueFilter === "blocked")
                }
                action={<Pill as="span" tone={card.tone === "danger" ? "danger" : card.tone === "warning" ? "warning" : "neutral"}>{card.value}</Pill>}
                onClick={card.onClick}
                className="rounded-[1rem]"
              />
            ))}
          </div>
        </div>
      </section>

      {canSeeActivity && (
        <section className="hidden rounded-[2rem] border border-[#13212c]/10 bg-white/82 p-6 shadow-[0_18px_44px_rgba(19,33,44,0.06)] md:block">
          <button
            type="button"
            onClick={() => setActivityExpanded((value) => !value)}
            aria-expanded={activityExpanded}
            aria-controls="inventory-activity-panel"
            className="flex w-full items-center justify-between gap-4 text-left"
          >
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
                <Radar size={18} />
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">{t("inventory.activityTitle", "Recent inventory activity")}</p>
                <h2 className="mt-1 text-lg font-semibold text-[#13212c]">{t("inventory.activitySubtitle", "What changed recently")}</h2>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="hidden rounded-full border border-[#13212c]/8 bg-[#fbf8f2] px-3 py-1.5 text-xs font-semibold text-[#61717d] sm:inline-flex">
                {t("inventory.activityVisibleCount", "{count} visible", { count: filteredActivity.length })}
              </span>
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#13212c]/10 bg-white text-[#13212c]">
                <ChevronDown size={17} className={`transition-transform ${activityExpanded ? "rotate-180" : ""}`} />
              </span>
            </div>
          </button>

          {activityExpanded ? (
            <div id="inventory-activity-panel" className="mt-5 space-y-3">
              {filteredActivity.length === 0 ? (
                <div className="rounded-[1.4rem] border border-[#13212c]/8 bg-[#fbf8f2] px-5 py-6 text-sm leading-7 text-[#61717d]">
                  {activity.length === 0
                    ? t("inventory.activityEmpty", "No recent inventory transactions to show yet.")
                    : t("inventory.activityFilteredEmpty", "No recent inventory activity matches the current lens, focus, or search.")}
                </div>
              ) : (
                filteredActivity.map((entry: any, index: number) => (
                  <div
                    key={`${entry.type}-${entry.performed_at}-${index}`}
                    className="rounded-[1.3rem] border border-[#13212c]/8 bg-[#fbf8f2] px-4 py-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">
                          {formatActivityType(entry.type)} · {shortId(entry.sku_id)}
                        </p>
                        <p className="mt-1.5 text-sm leading-6 text-[#61717d]">
                          {shortId(entry.location)} · {t("common.reference", "Reference")}: {entry.reference || "—"}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.12em] text-[#7f8d98]">
                          {entry.performed_by ? (
                            <span className="rounded-full border border-[#13212c]/8 bg-white px-2 py-1">
                              {t("inventory.activityActor", "Actor")}: {shortId(entry.performed_by)}
                            </span>
                          ) : null}
                          {entry.notes ? (
                            <span className="rounded-full border border-[#13212c]/8 bg-white px-2 py-1">
                              {t("inventory.activityNotes", "Notes")}
                            </span>
                          ) : null}
                        </div>
                        {entry.notes ? <p className="mt-2 text-sm leading-6 text-[#61717d]">{formatActivityNotes(entry)}</p> : null}
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-[#13212c]">{entry.qty_change}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7f8d98]">
                          {entry.performed_at ? new Date(entry.performed_at).toLocaleString() : "—"}
                        </p>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : null}
        </section>
      )}

      {(offset > 0 || hasMore || total > limit) && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500">
            {t("inventory.paginationShowing", "Showing {start}–{end} of {total}")
              .replace("{start}", String(offset + 1))
              .replace("{end}", String(Math.min(offset + limit, total)))
              .replace("{total}", `${total}${totalIsEstimate || hasMore ? "+" : ""}`)}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="px-3 py-1 bg-gray-100 rounded disabled:opacity-30"
            >
              ← {t("common.previous", "Previous")}
            </button>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={!hasMore}
              className="px-3 py-1 bg-gray-100 rounded disabled:opacity-30"
            >
              {t("common.next", "Next")} →
            </button>
          </div>
        </div>
      )}
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
    <section className="rounded-[1.25rem] border border-[#f0cf9d] bg-[#fff7ea] p-4 shadow-[0_20px_52px_rgba(19,33,44,0.06)] sm:rounded-[2rem] sm:p-6">
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="rounded-2xl border border-[#f7bf45]/35 bg-[#f7bf45]/14 p-2.5 text-[#c18500]">
          <AlertCircle size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#8b723f]">{eyebrow}</p>
          <h2 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-[#13212c] sm:text-2xl sm:tracking-[-0.03em]">{title}</h2>
          <p className="mt-3 hidden max-w-3xl text-sm leading-7 text-[#6f6248] sm:block">{body}</p>

          <div className="mt-5 grid gap-3 lg:grid-cols-2">
            {steps.map((step: any) => (
              <a
                key={step.name}
                href={checklistHref(step.name)}
                className="rounded-[1.1rem] border border-[#e6d4b2] bg-white/80 px-4 py-4 transition hover:border-[#d4b07a] hover:bg-white sm:rounded-[1.25rem]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#8a7755]">
                      {t("receiving.requiredStep", "Required step")}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-[#13212c]">
                      {t(`dashboard.checklist.${step.name}.title`, step.title || "")}
                    </p>
                    <p className="mt-1.5 hidden text-sm leading-6 text-[#61717d] sm:block">
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

          <p className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-[#8a7755]">{nextLabel}</p>
        </div>
      </div>
    </section>
  );
}
