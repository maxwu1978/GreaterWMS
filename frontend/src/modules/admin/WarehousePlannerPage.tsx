import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowDown,
  ArrowUp,
  Bot,
  Boxes,
  ChevronDown,
  Map,
  PackageCheck,
  Plus,
  RefreshCw,
  Weight,
} from "lucide-react";
import { Link } from "react-router-dom";
import { queryKeys } from "../../shared/api/queryKeys";
import {
  configureAisle as configureAisleRequest,
  configureRack as configureRackRequest,
  createAisle as createAisleRequest,
  createRack as createRackRequest,
  createWarehouseLocation,
  createWarehouseZone,
  deleteAisle as deleteAisleRequest,
  deleteRack as deleteRackRequest,
  deleteWarehouseLocation,
  deleteWarehouseZone,
  fetchPlannerRules,
  fetchWarehouseLocations,
  fetchWarehouseZones,
  fetchWarehousesPage,
  fetchWcsPointMappings,
  saveWcsPointMappings,
  updatePlannerRules,
  updateWarehouse,
  updateWarehouseLocation,
  updateWarehouseZone,
  validateWcsPointMappings,
} from "../../shared/api/planner";
import { fetchInventoryRaw } from "../../shared/api/inventory";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import {
  blueprintMetadataSummary,
  buildAisleGroups,
  buildAisleHeatmap,
  buildInventoryByLocation,
  buildRackGroups,
  buildRackHeatmap,
  buildZoneHeatmap,
  chunkItems,
  createZoneSkeleton,
  filterRackGroupsByAisle,
  fromDisplayLength,
  fromDisplayWeight,
  groupLocationsByZoneCode,
  lengthUnitLabel,
  locationStatusLabels,
  locationTypeLabels,
  nextGroupedCode,
  orderZones,
  timezoneOptions,
  toDisplayLength,
  toDisplayWeight,
  toList,
  weightUnitLabel,
  withZoneColors,
  zoneTemplates,
  type AisleGroup,
  type InventoryRow,
  type LayoutMode,
  type LocationRow,
  type UnitSystem,
  type WarehouseRow,
  type ZoneBlueprintForm,
  type ZoneRow,
} from "./warehousePlannerUtils";

const placementRules = [
  {
    icon: Weight,
    titleKey: "planner.ruleHeavyTitle",
    detailKey: "planner.ruleHeavyDetail",
  },
  {
    icon: PackageCheck,
    titleKey: "planner.ruleFastTitle",
    detailKey: "planner.ruleFastDetail",
  },
  {
    icon: Boxes,
    titleKey: "planner.ruleSlowTitle",
    detailKey: "planner.ruleSlowDetail",
  },
  {
    icon: Bot,
    titleKey: "planner.ruleSpecialTitle",
    detailKey: "planner.ruleSpecialDetail",
  },
];

type WcsPointMappingItem = {
  location_id: string | null;
  location_barcode: string | null;
  location_type: string;
  aisle: string | null;
  rack: string | null;
  level: string | null;
  position: string | null;
  wms_agv_accessible: boolean | null;
  is_external_point?: boolean;
  point_type?: string | null;
  point_role?: string | null;
  point_name?: string | null;
  point_code: string | null;
  buffer_code: string | null;
  aisle_group: string | null;
  station_role?: string | null;
  agv_reachable: boolean;
  virtual?: boolean;
  wcs_metadata?: Record<string, unknown> | null;
  dimensions?: Record<string, unknown> | null;
  layout_metadata?: Record<string, unknown> | null;
};

type WcsPointMappingsResponse = {
  warehouse_id: string;
  mapped_locations: number;
  unmapped_locations: number;
  external_points?: number;
  items: WcsPointMappingItem[];
};

type WcsPointMappingPayload = {
  location_id?: string | null;
  location_barcode?: string | null;
  point_code: string;
  point_type?: string;
  point_role?: string;
  point_name?: string;
  buffer_code?: string;
  aisle_group?: string;
  station_role?: string;
  agv_reachable: boolean;
  wcs_metadata?: Record<string, unknown>;
};

type WcsPointMappingValidation = {
  ok: boolean;
  summary?: {
    rows: number;
    mapped_locations: number;
    warehouse_locations: number;
    agv_accessible_locations: number;
    unmapped_agv_accessible_locations: number;
  };
  issues?: Array<{ row: number; code: string; message: string }>;
  warnings?: Array<{ row: number; code: string; message: string }>;
};

const wcsRoleForLocationType = (locationType: string) => {
  if (locationType === "dock") return "dock";
  if (locationType === "external") return "external";
  if (locationType === "staging" || locationType === "quality" || locationType === "packing") return "buffer";
  if (locationType === "charging") return "agv_station";
  return "storage";
};

const wcsRoleForItem = (item: WcsPointMappingItem) => {
  const explicitRole = String(item.point_role || item.point_type || item.location_type || "").toLowerCase();
  if (explicitRole === "dock") return "dock";
  if (explicitRole === "buffer") return "buffer";
  if (explicitRole === "agv_station") return "agv_station";
  if (explicitRole === "aisle_group" || explicitRole === "reference" || explicitRole === "external") return "external";
  return wcsRoleForLocationType(item.location_type);
};

const wcsRoleLabel = (role: string) => {
  if (role === "dock") return "Dock door point";
  if (role === "buffer") return "Buffer";
  if (role === "agv_station") return "AGV station";
  if (role === "external") return "External point";
  return "WMS location";
};

const wcsRolePrefix = (role: string) => {
  if (role === "dock") return "DOCK";
  if (role === "buffer") return "BUF";
  if (role === "agv_station") return "AGV";
  if (role === "external") return "EXT";
  return "STO";
};

const isVirtualDockDoor = (item: WcsPointMappingItem) =>
  wcsRoleForItem(item) === "dock" &&
  (Boolean(item.is_external_point) || Boolean(item.virtual) || Boolean(item.wcs_metadata?.virtual));

const wcsPointScopeLabel = (item: WcsPointMappingItem) => {
  if (isVirtualDockDoor(item)) return "Virtual dock door";
  if (item.is_external_point) return "External point";
  if (wcsRoleForItem(item) === "dock") return "Dock location record";
  return "Real WMS location";
};

const pointToken = (value: string | null | undefined, fallback: string) =>
  String(value || fallback)
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || fallback;

const buildSuggestedWcsMappings = (
  items: WcsPointMappingItem[],
  warehouseCode: string | undefined,
): WcsPointMappingPayload[] => {
  const site = pointToken(warehouseCode, "WMS");
  return items.map((item) => {
    const role = wcsRoleForItem(item);
    const aisle = pointToken(item.aisle, "00");
    const barcode = pointToken(item.location_barcode || item.location_id, "POINT");
    const wcsMetadata = { ...(item.wcs_metadata || {}) };
    if (isVirtualDockDoor(item)) wcsMetadata.virtual = true;
    return {
      location_id: item.location_id,
      location_barcode: item.location_barcode,
      point_code: item.point_code || `${site}-${wcsRolePrefix(role)}-${barcode}`,
      point_type: item.point_type || role,
      point_role: item.point_role || role,
      point_name: item.point_name || (isVirtualDockDoor(item) ? item.location_barcode || item.point_code || undefined : undefined),
      buffer_code: item.buffer_code || (role === "buffer" ? `${site}-BUF-${aisle}` : undefined),
      aisle_group: role === "external" || role === "dock" ? item.aisle_group || undefined : item.aisle_group || `${site}-AISLE-${aisle}`,
      station_role: item.station_role || undefined,
      agv_reachable: Boolean(item.agv_reachable ?? item.wms_agv_accessible ?? role === "dock"),
      wcs_metadata: Object.keys(wcsMetadata).length ? wcsMetadata : undefined,
    };
  });
};

export default function WarehousePlannerPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [unitSystem, setUnitSystem] = useState<UnitSystem>("metric");
  const [selectedWarehouseId, setSelectedWarehouseId] = useState("");
  const [zoneForm, setZoneForm] = useState({
    name: "",
    code: "",
    is_agv_zone: false,
    sequence: 10,
    layout_mode: "rack" as LayoutMode,
  });
  const [showZoneDraftCard, setShowZoneDraftCard] = useState(false);
  const [zoneBlueprint, setZoneBlueprint] = useState<ZoneBlueprintForm>({
    aisles: 3,
    racksPerAisle: 4,
    levelsPerRack: 3,
    slotsPerLevel: 6,
  });
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
  const [selectedRackKey, setSelectedRackKey] = useState<string | null>(null);
  const [isCreatingRack, setIsCreatingRack] = useState(false);
  const [isCreatingAisle, setIsCreatingAisle] = useState(false);
  const [pendingLocationFocus, setPendingLocationFocus] = useState<{
    barcode: string;
    rackKey: string;
    aisle: string;
  } | null>(null);
  const [focusedAisleKey, setFocusedAisleKey] = useState<string | null>(null);
  const [locationForm, setLocationForm] = useState({
    barcode: "",
    aisle: "",
    rack: "",
    level: "",
    position: "",
    location_type: "storage",
    current_status: "available",
    is_agv_accessible: false,
  });
  const [locationQuickFilter, setLocationQuickFilter] = useState("");
  const [warehouseDraft, setWarehouseDraft] = useState({
    name: "",
    code: "",
    timezone: "Europe/Budapest",
  });
  const zoneEditorRef = useRef<HTMLDivElement | null>(null);
  const locationEditorRef = useRef<HTMLDivElement | null>(null);
  const rackEditorRef = useRef<HTMLDivElement | null>(null);
  const aisleEditorRef = useRef<HTMLDivElement | null>(null);
  const [rackForm, setRackForm] = useState({
    aisle: "",
    rack: "",
    levels: 1,
    slotsPerLevel: 1,
    location_type: "storage",
    is_agv_accessible: true,
    max_weight_kg: 1200,
  });
  const [aisleForm, setAisleForm] = useState({
    aisle: "",
    firstRack: "01",
    levels: 3,
    slotsPerLevel: 4,
    location_type: "storage",
    is_agv_accessible: true,
    max_weight_kg: 1200,
  });
  const [zoneEditorExpanded, setZoneEditorExpanded] = useState(false);
  const [aisleEditorExpanded, setAisleEditorExpanded] = useState(false);
  const [rackEditorExpanded, setRackEditorExpanded] = useState(false);
  const [locationEditorExpanded, setLocationEditorExpanded] = useState(false);
  const [rules, setRules] = useState({
    heavy_items_low: true,
    heavy_item_threshold_kg: 20,
    fast_movers_front: true,
    slow_movers_deep: true,
    separate_hazmat: true,
    separate_cold_chain: true,
    allow_same_sku_consolidation: true,
    different_sku_slot_policy: "block",
    lot_expiry_mismatch_policy: "warn",
    rack_height_m: 7.5,
    beam_capacity_kg: 1200,
    aisle_width_m: 3.2,
    agv_turning_radius_m: 1.8,
  });
  const [wcsValidation, setWcsValidation] = useState<WcsPointMappingValidation | null>(null);
  const [validatedWcsMappingFingerprint, setValidatedWcsMappingFingerprint] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const { data: warehousePage } = useQuery({
    queryKey: queryKeys.planner.warehouses(),
    queryFn: fetchWarehousesPage,
  });
  const warehouses: WarehouseRow[] = warehousePage?.items || [];
  const activeWarehouseId = selectedWarehouseId || warehouses[0]?.id || "";
  const activeWarehouse = warehouses.find((warehouse) => warehouse.id === activeWarehouseId) || null;

  const { data: zones = [] } = useQuery({
    queryKey: queryKeys.planner.zones(activeWarehouseId),
    enabled: Boolean(activeWarehouseId),
    queryFn: () => fetchWarehouseZones(activeWarehouseId),
  });

  const { data: plannerRules } = useQuery({
    queryKey: queryKeys.planner.rules(activeWarehouseId),
    enabled: Boolean(activeWarehouseId),
    queryFn: () => fetchPlannerRules(activeWarehouseId),
  });

  const { data: locations = [] } = useQuery({
    queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId),
    enabled: Boolean(activeWarehouseId && selectedZoneId),
    queryFn: () => fetchWarehouseLocations(activeWarehouseId, { zone_id: selectedZoneId }),
  });

  const { data: allWarehouseLocations = [] } = useQuery({
    queryKey: queryKeys.planner.allLocations(activeWarehouseId),
    enabled: Boolean(activeWarehouseId),
    queryFn: () => fetchWarehouseLocations(activeWarehouseId).then((data) => toList<LocationRow>(data)),
  });

  const { data: wcsPointMappings, isFetching: isFetchingWcsMappings } = useQuery<WcsPointMappingsResponse>({
    queryKey: queryKeys.planner.wcsPointMappings(activeWarehouseId),
    enabled: Boolean(activeWarehouseId),
    queryFn: () => fetchWcsPointMappings({ warehouse_id: activeWarehouseId, include_unmapped: true }),
  });

  const { data: inventoryItems = [] } = useQuery({
    queryKey: queryKeys.planner.heatInventory(activeWarehouseId),
    enabled: Boolean(activeWarehouseId),
    queryFn: () =>
      fetchInventoryRaw({ offset: 0, limit: 500 }).then((data) =>
        toList<InventoryRow>(data).filter((item) => item.warehouse_id === activeWarehouseId),
      ),
  });

  useEffect(() => {
    if (!plannerRules) return;
    setRules({
      heavy_items_low: plannerRules.heavy_items_low,
      heavy_item_threshold_kg: plannerRules.heavy_item_threshold_kg,
      fast_movers_front: plannerRules.fast_movers_front,
      slow_movers_deep: plannerRules.slow_movers_deep,
      separate_hazmat: plannerRules.separate_hazmat,
      separate_cold_chain: plannerRules.separate_cold_chain,
      allow_same_sku_consolidation: plannerRules.allow_same_sku_consolidation ?? true,
      different_sku_slot_policy: plannerRules.different_sku_slot_policy || "block",
      lot_expiry_mismatch_policy: plannerRules.lot_expiry_mismatch_policy || "warn",
      rack_height_m: plannerRules.rack_height_m,
      beam_capacity_kg: plannerRules.beam_capacity_kg,
      aisle_width_m: plannerRules.aisle_width_m,
      agv_turning_radius_m: plannerRules.agv_turning_radius_m,
    });
  }, [plannerRules]);

  useEffect(() => {
    if (!activeWarehouse) return;
    setWarehouseDraft({
      name: activeWarehouse.name,
      code: activeWarehouse.code,
      timezone: activeWarehouse.timezone,
    });
  }, [activeWarehouse]);

  const addZone = useMutation({
    mutationFn: async () => {
      const zoneResponse = await createWarehouseZone(activeWarehouseId, {
        ...zoneForm,
        code: zoneForm.code.toUpperCase(),
      });

      const createdZone = zoneResponse.data;
      const skeleton = createZoneSkeleton(
        createdZone.id,
        zoneForm.code.toUpperCase(),
        zoneBlueprint,
        zoneForm.is_agv_zone,
        zoneForm.layout_mode,
      );

      for (const chunk of chunkItems(skeleton, 24)) {
        await Promise.all(chunk.map((location) => createWarehouseLocation(activeWarehouseId, location)));
      }

      return { createdZone, skeletonCount: skeleton.length };
    },
    onSuccess: async ({ createdZone, skeletonCount }) => {
      setError("");
      setSuccess(
        `${t("planner.successZone", "Zone added to the planner.")} ${t("planner.successZoneSkeleton", "{count} starter locations created.", {
          count: String(skeletonCount),
        })}`,
      );
      setZoneForm({ name: "", code: "", is_agv_zone: false, sequence: 10, layout_mode: "rack" });
      setZoneBlueprint({ aisles: 3, racksPerAisle: 4, levelsPerRack: 3, slotsPerLevel: 6 });
      setShowZoneDraftCard(false);
      setSelectedLocationId(null);
      setSelectedRackKey(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, createdZone.id) });
      setSelectedZoneId(createdZone.id);
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorZone", "Could not add the zone.")));
    },
  });

  const updateZone = useMutation({
    mutationFn: async () =>
      updateWarehouseZone(activeWarehouseId, selectedZoneId, {
        ...zoneForm,
        code: zoneForm.code.toUpperCase(),
      }),
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successZoneUpdated", "Zone details saved."));
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorZoneUpdated", "Could not save the zone.")));
    },
  });

  const moveZone = useMutation({
    mutationFn: async (direction: "earlier" | "later") => {
      if (!selectedZone) return;
      const orderedZones = [...zoneBlocks].sort((a, b) =>
        a.sequence === b.sequence ? a.code.localeCompare(b.code) : a.sequence - b.sequence,
      );
      const currentIndex = orderedZones.findIndex((zone) => zone.id === selectedZone.id);
      const neighborIndex = direction === "earlier" ? currentIndex - 1 : currentIndex + 1;
      const neighbor = orderedZones[neighborIndex];
      if (!neighbor) return;

      await updateWarehouseZone(activeWarehouseId, selectedZone.id, {
        name: selectedZone.name,
        code: selectedZone.code,
        is_agv_zone: selectedZone.is_agv_zone,
        sequence: neighbor.sequence,
      });
      await updateWarehouseZone(activeWarehouseId, neighbor.id, {
        name: neighbor.name,
        code: neighbor.code,
        is_agv_zone: neighbor.is_agv_zone,
        sequence: selectedZone.sequence,
      });
    },
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successZoneReordered", "Zone order updated."));
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorZoneReordered", "Could not update zone order.")));
    },
  });

  const deleteZone = useMutation({
    mutationFn: async () => deleteWarehouseZone(activeWarehouseId, selectedZoneId),
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successZoneDeleted", "Zone removed from the plan."));
      setSelectedZoneId(null);
      setSelectedLocationId(null);
      setZoneForm({ name: "", code: "", is_agv_zone: false, sequence: 10, layout_mode: "rack" });
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorZoneDeleted", "Could not delete the zone.")));
    },
  });

  const saveRules = useMutation({
    mutationFn: async () => updatePlannerRules(activeWarehouseId, rules),
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successRules", "Placement rules saved."));
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.rules(activeWarehouseId) });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorRules", "Could not save planner rules.")));
    },
  });

  const validateWcsMappings = useMutation({
    mutationFn: async () =>
      validateWcsPointMappings({
        warehouse_id: activeWarehouseId,
        mappings: suggestedWcsMappings,
      }),
    onSuccess: (response) => {
      setError("");
      setSuccess(t("planner.wcsValidationSuccess", "WCS point mappings checked."));
      setWcsValidation(response.data);
      setValidatedWcsMappingFingerprint(suggestedWcsMappingFingerprint);
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.wcsValidationError", "Could not validate WCS point mappings.")));
    },
  });

  const saveWcsMappings = useMutation({
    mutationFn: async () => {
      if (!wcsValidationIsCurrent) {
        throw new Error(t("planner.wcsCheckBeforeSave", "Check mappings before saving."));
      }
      return saveWcsPointMappings({
        warehouse_id: activeWarehouseId,
        mappings: suggestedWcsMappings,
        merge: false,
      });
    },
    onSuccess: async (response) => {
      setError("");
      setSuccess(t("planner.wcsMappingSuccess", "WCS point mappings saved."));
      setWcsValidation(response.data?.validation || null);
      setValidatedWcsMappingFingerprint(suggestedWcsMappingFingerprint);
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.wcsPointMappings(activeWarehouseId) });
    },
    onError: (err: any) => {
      setSuccess("");
      const detail = err?.response?.data?.detail;
      setWcsValidation(detail?.summary ? detail : null);
      setError(getApiErrorMessage(err, t("planner.wcsMappingError", "Could not save WCS point mappings.")));
    },
  });

  const saveWarehouse = useMutation({
    mutationFn: async () =>
      updateWarehouse(activeWarehouseId, {
        name: warehouseDraft.name,
        code: warehouseDraft.code.toUpperCase(),
        timezone: warehouseDraft.timezone,
      }),
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successWarehouse", "Warehouse details saved."));
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.warehouses() });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorWarehouse", "Could not save warehouse details.")));
    },
  });

  const zoneBlocks = useMemo(() => withZoneColors(zones), [zones]);

  const agvZoneCount = zones.filter((zone: ZoneRow) => zone.is_agv_zone).length;
  const totalLocations = zones.reduce((sum: number, zone: ZoneRow) => sum + zone.location_count, 0);
  const totalZones = zones.length;
  const enabledRuleCount = [
    rules.heavy_items_low,
    rules.fast_movers_front,
    rules.slow_movers_deep,
    rules.separate_hazmat,
    rules.separate_cold_chain,
    rules.allow_same_sku_consolidation,
  ].filter(Boolean).length;
  const agvChecks = [
    {
      label: t("planner.checkAisle", "Aisle width"),
      value: `${toDisplayLength(rules.aisle_width_m, unitSystem).toFixed(1)} ${lengthUnitLabel(unitSystem)}`,
      target:
        unitSystem === "imperial"
          ? t("planner.checkAisleTargetImperial", "Target 9.2ft+")
          : t("planner.checkAisleTarget", "Target 2.8m+"),
      ok: rules.aisle_width_m >= 2.8,
      detail: rules.aisle_width_m >= 2.8
        ? t("planner.checkAisleOk", "Forklift and AGV lanes have workable clearance.")
        : t("planner.checkAisleWarn", "This aisle profile is likely too narrow for safe AGV routing."),
    },
    {
      label: t("planner.checkTurn", "Turning radius"),
      value: `${toDisplayLength(rules.agv_turning_radius_m, unitSystem).toFixed(1)} ${lengthUnitLabel(unitSystem)}`,
      target:
        unitSystem === "imperial"
          ? t("planner.checkTurnTargetImperial", "Target 4.6ft+")
          : t("planner.checkTurnTarget", "Target 1.4m+"),
      ok: rules.agv_turning_radius_m >= 1.4,
      detail: rules.agv_turning_radius_m >= 1.4
        ? t("planner.checkTurnOk", "Robots should have enough clearance for standard turns.")
        : t("planner.checkTurnWarn", "Tight turns will create false readiness if this is not corrected."),
    },
    {
      label: t("planner.checkBeam", "Beam capacity"),
      value: `${toDisplayWeight(rules.beam_capacity_kg, unitSystem).toFixed(0)} ${weightUnitLabel(unitSystem)}`,
      target:
        unitSystem === "imperial"
          ? t("planner.checkBeamTargetImperial", "Match pallet profile (lb)")
          : t("planner.checkBeamTarget", "Match pallet profile"),
      ok: rules.beam_capacity_kg >= Math.max(rules.heavy_item_threshold_kg * 60, 800),
      detail: rules.beam_capacity_kg >= Math.max(rules.heavy_item_threshold_kg * 60, 800)
        ? t("planner.checkBeamOk", "Rack load profile is aligned with heavier pallet storage.")
        : t("planner.checkBeamWarn", "Beam capacity looks light relative to the heavy-item threshold."),
    },
    {
      label: t("planner.checkRack", "Rack height"),
      value: `${toDisplayLength(rules.rack_height_m, unitSystem).toFixed(1)} ${lengthUnitLabel(unitSystem)}`,
      target:
        unitSystem === "imperial"
          ? t("planner.checkRackTargetImperial", "Confirm lift envelope (ft)")
          : t("planner.checkRackTarget", "Confirm lift envelope"),
      ok: rules.rack_height_m >= 4.5,
      detail: rules.rack_height_m >= 4.5
        ? t("planner.checkRackOk", "Vertical storage envelope looks realistic for reserve operations.")
        : t("planner.checkRackWarn", "Low rack height may limit reserve strategy and robot reach assumptions."),
    },
  ];
  const agvReadyScore = agvChecks.filter((check) => check.ok).length;
  const wcsMappingItems = wcsPointMappings?.items || [];
  const suggestedWcsMappings = useMemo(
    () => buildSuggestedWcsMappings(wcsMappingItems, activeWarehouse?.code),
    [activeWarehouse?.code, wcsMappingItems],
  );
  const suggestedWcsMappingFingerprint = useMemo(
    () => JSON.stringify(suggestedWcsMappings),
    [suggestedWcsMappings],
  );
  const wcsValidationIsCurrent =
    Boolean(wcsValidation?.ok) && validatedWcsMappingFingerprint === suggestedWcsMappingFingerprint;
  const wcsRoleCounts = useMemo(() => {
    return wcsMappingItems.reduce<Record<string, number>>((counts, item) => {
      const role = wcsRoleForItem(item);
      counts[role] = (counts[role] || 0) + 1;
      return counts;
    }, {});
  }, [wcsMappingItems]);
  const wcsMissingCount = wcsMappingItems.filter((item) => !item.point_code).length;
  const wcsExternalPointCount = wcsMappingItems.filter((item) => item.is_external_point || isVirtualDockDoor(item)).length;
  const wcsWarehouseLocationPointCount = wcsMappingItems.length - wcsExternalPointCount;
  const wcsVirtualDockDoorCount = wcsMappingItems.filter(isVirtualDockDoor).length;
  const wcsIssueCount = wcsValidation?.issues?.length || 0;
  const wcsWarningCount = wcsValidation?.warnings?.length || 0;

  useEffect(() => {
    setWcsValidation(null);
    setValidatedWcsMappingFingerprint("");
  }, [activeWarehouseId, suggestedWcsMappingFingerprint]);
  const warehouseDirty =
    Boolean(activeWarehouse) &&
    (warehouseDraft.name !== activeWarehouse?.name ||
      warehouseDraft.code !== activeWarehouse?.code ||
      warehouseDraft.timezone !== activeWarehouse?.timezone);
  const selectedZone = zoneBlocks.find((zone) => zone.id === selectedZoneId) || null;
  const selectedLocation = locations.find((location: LocationRow) => location.id === selectedLocationId) || null;
  const selectedZoneLayoutMode: LayoutMode = selectedZone?.layout_mode || zoneForm.layout_mode || "rack";
  const layoutTerms = {
    primary: selectedZoneLayoutMode === "area" ? t("planner.termSection", "Section") : t("planner.termAisle", "Aisle"),
    primaryPlural:
      selectedZoneLayoutMode === "area" ? t("planner.termSections", "Sections") : t("planner.termAisles", "Aisles"),
    secondary: selectedZoneLayoutMode === "area" ? t("planner.termRow", "Row") : t("planner.termRack", "Rack"),
    secondaryPlural:
      selectedZoneLayoutMode === "area" ? t("planner.termRows", "Rows") : t("planner.termRacks", "Racks"),
    level: t("planner.termLevel", "Level"),
    slot: t("planner.termSlot", "Slot"),
  };
  const groupModeLabel =
    selectedZoneLayoutMode === "area"
      ? t("planner.layoutModeArea", "Area-first")
      : t("planner.layoutModeRack", "Rack-first");
  const newGroupButtonLabel =
    selectedZoneLayoutMode === "area"
      ? t("planner.newRowButton", "New row")
      : t("planner.newRackButton", "New rack");
  const heatEyebrow = t("planner.inventoryHeatEyebrow", "Inventory distribution");
  const heatTitle =
    selectedZoneLayoutMode === "area"
      ? t("planner.inventoryDensityTitleArea", "Plan with inventory distribution visible across sections and rows.")
      : t("planner.inventoryHeatTitle", "Keep stock pressure visible while planning.");
  const heatBody =
    selectedZoneLayoutMode === "area"
      ? t("planner.inventoryDensityBodyArea", "See which sections, rows, and slots are fuller before you change the zone layout.")
      : t("planner.inventoryHeatBody", "See which zones, aisles, and slots are fuller before you change the layout.");
  const secondaryViewEyebrow =
    selectedZoneLayoutMode === "area"
      ? t("planner.areaView", "Area grid")
      : t("planner.slotLanguage", "Rack view");
  const secondaryViewTitle =
    selectedZoneLayoutMode === "area"
      ? t("planner.areaViewTitle", "Keep the same area language in planning and daily execution.")
      : t("planner.slotLanguageTitle", "Use the same rack language in planning and putaway.");
  const secondaryViewHint =
    selectedZoneLayoutMode === "area"
      ? t("planner.areaViewHint", "Pick a row here, then keep editing the same structure operators will use on the floor.")
      : t("planner.slotLanguageHint", "Select a rack here, then keep editing the same structure operators will later use on the floor.");
  const secondaryViewBody =
    selectedZoneLayoutMode === "area"
      ? t("planner.areaViewBody", "Suggested, manual, and selected states stay consistent between planning and execution in area-based zones.")
      : t("planner.slotLanguageBody", "Suggested, manual, and selected states stay consistent between planning and execution.");
  const formatLocationSummary = (location: Pick<LocationRow, "aisle" | "rack" | "level" | "position">) =>
    `${layoutTerms.primary} ${location.aisle} · ${layoutTerms.secondary} ${location.rack} · ${layoutTerms.level} ${location.level} · ${layoutTerms.slot} ${location.position}`;
  const orderedZones = useMemo(() => orderZones(zoneBlocks), [zoneBlocks]);
  const rackGroups = useMemo(() => buildRackGroups(locations), [locations]);
  const aisleGroups = useMemo<AisleGroup[]>(() => buildAisleGroups(locations), [locations]);
  const inventoryByLocation = useMemo(() => buildInventoryByLocation(inventoryItems), [inventoryItems]);
  const zoneLocationGroups = useMemo(() => groupLocationsByZoneCode(allWarehouseLocations), [allWarehouseLocations]);
  const blueprintSummary = useMemo(
    () => blueprintMetadataSummary(zones, allWarehouseLocations),
    [allWarehouseLocations, zones],
  );
  const selectedRack = rackGroups.find((rack) => rack.key === selectedRackKey) || null;
  const selectedAisle = aisleGroups.find((aisleGroup) => aisleGroup.aisle === focusedAisleKey) || null;
  const zoneHeatmap = useMemo(
    () => buildZoneHeatmap(orderedZones, zoneLocationGroups, inventoryByLocation),
    [inventoryByLocation, orderedZones, zoneLocationGroups],
  );
  const aisleHeatmap = useMemo(
    () => (selectedZone ? buildAisleHeatmap(locations, inventoryByLocation) : []),
    [inventoryByLocation, locations, selectedZone],
  );
  const rackHeatmap = useMemo(
    () => buildRackHeatmap(locations, selectedRack, inventoryByLocation),
    [inventoryByLocation, locations, selectedRack],
  );
  const displayedRackGroups = useMemo(
    () => filterRackGroupsByAisle(rackGroups, focusedAisleKey),
    [focusedAisleKey, rackGroups],
  );
  const zoneHeatActive = Boolean(selectedZone);
  const aisleHeatActive = Boolean(focusedAisleKey);
  const rackHeatActive = Boolean(selectedRack);
  const slotHeatActive = Boolean(selectedLocation);
  const selectedZoneOrderIndex = selectedZone
    ? orderedZones.findIndex((zone) => zone.id === selectedZone.id)
    : -1;
  const previousZone = selectedZoneOrderIndex > 0 ? orderedZones[selectedZoneOrderIndex - 1] : null;
  const nextZone =
    selectedZoneOrderIndex >= 0 && selectedZoneOrderIndex < orderedZones.length - 1
      ? orderedZones[selectedZoneOrderIndex + 1]
      : null;
  const describeLocationType = (value: string) =>
    t(`planner.locationTypeValue.${value}`, locationTypeLabels[value] || value);
  const describeLocationStatus = (value: string) =>
    t(`planner.locationStatusValue.${value}`, locationStatusLabels[value] || value);
  const filteredLocations = useMemo(() => {
    const query = locationQuickFilter.trim().toLowerCase();
    if (!query) return locations;
    return locations.filter((location) => {
      const haystack = [
        location.barcode,
        location.aisle,
        location.rack,
        location.level,
        location.position,
        describeLocationType(location.location_type),
        describeLocationStatus(location.current_status),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [locationQuickFilter, locations, t]);
  const zoneEditorDirty = Boolean(
    selectedZone &&
      (zoneForm.name !== selectedZone.name ||
        zoneForm.code !== selectedZone.code ||
        zoneForm.is_agv_zone !== selectedZone.is_agv_zone ||
        zoneForm.sequence !== selectedZone.sequence ||
        zoneForm.layout_mode !== selectedZone.layout_mode),
  );
  const locationEditorDirty = Boolean(
    selectedLocation &&
      (locationForm.barcode !== selectedLocation.barcode ||
        locationForm.aisle !== selectedLocation.aisle ||
        locationForm.rack !== selectedLocation.rack ||
        locationForm.level !== selectedLocation.level ||
        locationForm.position !== selectedLocation.position ||
        locationForm.location_type !== selectedLocation.location_type ||
        locationForm.current_status !== selectedLocation.current_status ||
        locationForm.is_agv_accessible !== selectedLocation.is_agv_accessible),
  );
  const rackEditorDirty = Boolean(
    selectedRack &&
      (rackForm.aisle !== selectedRack.aisle ||
        rackForm.rack !== selectedRack.rack ||
        rackForm.levels !== selectedRack.levelCount ||
        rackForm.slotsPerLevel !== selectedRack.slotCount ||
        rackForm.location_type !== selectedRack.locationType ||
        rackForm.max_weight_kg !== (selectedRack.maxWeightKg ?? 1200) ||
        rackForm.is_agv_accessible !== (selectedRack.agvCount === selectedRack.locationCount)),
  );
  const aisleEditorDirty = Boolean(
    selectedAisle &&
      (aisleForm.aisle !== selectedAisle.aisle ||
        aisleForm.location_type !== selectedAisle.locationType ||
        aisleForm.max_weight_kg !== (selectedAisle.maxWeightKg ?? 1200) ||
        aisleForm.is_agv_accessible !== (selectedAisle.agvCount === selectedAisle.locationCount)),
  );
  const rackCreateReady = Boolean(rackForm.aisle.trim() && rackForm.rack.trim() && rackForm.levels > 0 && rackForm.slotsPerLevel > 0);
  const aisleCreateReady = Boolean(aisleForm.aisle.trim() && aisleForm.firstRack.trim() && aisleForm.levels > 0 && aisleForm.slotsPerLevel > 0);
  const prepareNewZone = () => {
    setSelectedZoneId(null);
    setSelectedLocationId(null);
    setSelectedRackKey(null);
    setIsCreatingRack(false);
    setIsCreatingAisle(false);
    setShowZoneDraftCard(true);
      setZoneForm({
        name: "",
        code: "",
        is_agv_zone: false,
        sequence: (orderedZones.at(-1)?.sequence ?? 0) + 1,
        layout_mode: "rack",
      });
    setZoneBlueprint({
      aisles: 3,
      racksPerAisle: 4,
      levelsPerRack: 3,
      slotsPerLevel: 6,
    });
    setLocationForm({
      barcode: "",
      aisle: "",
      rack: "",
      level: "",
      position: "",
      location_type: "storage",
      current_status: "available",
      is_agv_accessible: false,
    });
    setSuccess("");
    setError("");
    requestAnimationFrame(() => zoneEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  const prepareNewRack = () => {
    const zoneForRack = selectedZone || orderedZones[0] || null;
    if (!zoneForRack) {
      setSuccess("");
      setError(t("planner.selectZoneBeforeRack", "Select a zone before adding a rack."));
      return;
    }
    const zoneLocations = locations;
    const defaultAisle = focusedAisleKey || zoneLocations[0]?.aisle || "01";
    const aisleLocations = zoneLocations.filter((location: LocationRow) => location.aisle === defaultAisle);
    const nextRack = nextGroupedCode(aisleLocations.map((location: LocationRow) => location.rack));
    setSelectedZoneId(zoneForRack.id);
    setSelectedLocationId(null);
    setSelectedRackKey(null);
    setIsCreatingAisle(false);
    setIsCreatingRack(true);
    setRackEditorExpanded(true);
    setRackForm({
      aisle: defaultAisle,
      rack: nextRack,
      levels: 3,
      slotsPerLevel: 4,
      location_type: "storage",
      is_agv_accessible: selectedZoneLayoutMode === "rack",
      max_weight_kg: 1200,
    });
    setSuccess("");
    setError("");
    setTimeout(() => rackEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  };
  const prepareNewAisle = () => {
    const zoneForAisle = selectedZone || orderedZones[0] || null;
    if (!zoneForAisle) {
      setSuccess("");
      setError(t("planner.selectZoneBeforeAisle", "Select a zone before adding an aisle."));
      return;
    }
    const nextAisle = nextGroupedCode(locations.map((location: LocationRow) => location.aisle));
    setSelectedZoneId(zoneForAisle.id);
    setSelectedLocationId(null);
    setSelectedRackKey(null);
    setFocusedAisleKey(nextAisle);
    setIsCreatingRack(false);
    setIsCreatingAisle(true);
    setAisleEditorExpanded(true);
    setAisleForm({
      aisle: nextAisle,
      firstRack: "01",
      levels: 3,
      slotsPerLevel: 4,
      location_type: "storage",
      is_agv_accessible: selectedZoneLayoutMode === "rack",
      max_weight_kg: 1200,
    });
    setSuccess("");
    setError("");
    setTimeout(() => aisleEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  };
  const selectRack = (rackKey: string) => {
    setIsCreatingAisle(false);
    setIsCreatingRack(false);
    setSelectedRackKey(rackKey);
    const rack = rackGroups.find((item) => item.key === rackKey);
    setFocusedAisleKey(rack?.aisle || null);
    const firstLocation = locations.find((location) => `${location.aisle}::${location.rack}` === rackKey);
    setSelectedLocationId(firstLocation?.id || null);
    setSuccess("");
    setError("");
    setTimeout(() => {
      rackEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      if (firstLocation) {
        locationEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 80);
  };

  const selectZoneFromHeat = (zoneCode: string) => {
    const nextZone = zoneBlocks.find((zone) => zone.code.toUpperCase() === zoneCode.toUpperCase());
    if (!nextZone) return;
    setSelectedZoneId(nextZone.id);
    setSelectedRackKey(null);
    setIsCreatingRack(false);
    setIsCreatingAisle(false);
    setSelectedLocationId(null);
    setFocusedAisleKey(null);
    setShowZoneDraftCard(false);
    setSuccess("");
    setError("");
  };

  const selectAisleFromHeat = (aisle: string) => {
    const nextFocusedAisle = focusedAisleKey === aisle ? null : aisle;
    setFocusedAisleKey(nextFocusedAisle);
    setIsCreatingAisle(false);
    if (!nextFocusedAisle) {
      setSelectedRackKey(null);
      setSelectedLocationId(null);
      return;
    }
    const firstRack = rackGroups.find((rack) => rack.aisle === aisle);
    if (firstRack) {
      setIsCreatingRack(false);
      setSelectedRackKey(firstRack.key);
      const firstLocation = locations.find((location) => location.aisle === firstRack.aisle && location.rack === firstRack.rack);
      setSelectedLocationId(firstLocation?.id || null);
      setTimeout(() => {
        rackEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        if (firstLocation) {
          locationEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 80);
    }
  };

  const selectLocationFromHeat = (barcode: string) => {
    const nextLocation = locations.find((location) => location.barcode === barcode);
    if (!nextLocation) return;
    setIsCreatingAisle(false);
    setIsCreatingRack(false);
    setSelectedLocationId(nextLocation.id);
    setSelectedRackKey(`${nextLocation.aisle}::${nextLocation.rack}`);
    setFocusedAisleKey(nextLocation.aisle);
    setTimeout(() => locationEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  };

  useEffect(() => {
    if (!selectedZone) return;
    setZoneEditorExpanded(true);
    setZoneForm({
      name: selectedZone.name,
      code: selectedZone.code,
      is_agv_zone: selectedZone.is_agv_zone,
      sequence: selectedZone.sequence,
      layout_mode: selectedZone.layout_mode || "rack",
    });
    requestAnimationFrame(() => zoneEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [selectedZoneId, selectedZone?.name, selectedZone?.code, selectedZone?.is_agv_zone, selectedZone?.sequence, selectedZone?.layout_mode]);

  useEffect(() => {
    if (!selectedLocation) return;
    setLocationEditorExpanded(true);
    setLocationForm({
      barcode: selectedLocation.barcode,
      aisle: selectedLocation.aisle,
      rack: selectedLocation.rack,
      level: selectedLocation.level,
      position: selectedLocation.position,
      location_type: selectedLocation.location_type,
      current_status: selectedLocation.current_status,
      is_agv_accessible: selectedLocation.is_agv_accessible,
    });
    requestAnimationFrame(() => locationEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [selectedLocationId, selectedLocation?.barcode, selectedLocation?.aisle, selectedLocation?.rack, selectedLocation?.level, selectedLocation?.position, selectedLocation?.location_type, selectedLocation?.current_status, selectedLocation?.is_agv_accessible]);

  useEffect(() => {
    if (!selectedRack) return;
    setIsCreatingRack(false);
    setRackEditorExpanded(true);
    setRackForm({
      aisle: selectedRack.aisle,
      rack: selectedRack.rack,
      levels: selectedRack.levelCount,
      slotsPerLevel: selectedRack.slotCount,
      location_type: selectedRack.locationType,
      is_agv_accessible: selectedRack.agvCount === selectedRack.locationCount,
      max_weight_kg: selectedRack.maxWeightKg ?? 1200,
    });
    requestAnimationFrame(() => rackEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [selectedRackKey, selectedRack?.aisle, selectedRack?.rack, selectedRack?.agvCount, selectedRack?.locationCount, selectedRack?.levelCount, selectedRack?.slotCount, selectedRack?.locationType, selectedRack?.maxWeightKg]);

  useEffect(() => {
    if (!selectedZoneId) {
      setFocusedAisleKey(null);
      setIsCreatingRack(false);
      setIsCreatingAisle(false);
      setPendingLocationFocus(null);
      return;
    }
    setFocusedAisleKey(null);
    setLocationQuickFilter("");
  }, [selectedZoneId]);

  useEffect(() => {
    if (!pendingLocationFocus) return;
    const nextLocation = locations.find((location) => location.barcode === pendingLocationFocus.barcode);
    if (!nextLocation) return;
    setFocusedAisleKey(pendingLocationFocus.aisle);
    setSelectedRackKey(pendingLocationFocus.rackKey);
    setSelectedLocationId(nextLocation.id);
    setPendingLocationFocus(null);
    setTimeout(() => locationEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }, [locations, pendingLocationFocus]);

  useEffect(() => {
    if (isCreatingAisle) return;
    if (!selectedAisle) return;
    setAisleEditorExpanded(true);
    setAisleForm({
      aisle: selectedAisle.aisle,
      firstRack: rackGroups.find((rack) => rack.aisle === selectedAisle.aisle)?.rack || "01",
      levels: 3,
      slotsPerLevel: 4,
      location_type: selectedAisle.locationType,
      is_agv_accessible: selectedAisle.agvCount === selectedAisle.locationCount,
      max_weight_kg: selectedAisle.maxWeightKg ?? 1200,
    });
    requestAnimationFrame(() => aisleEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [isCreatingAisle, rackGroups, selectedAisle?.aisle, selectedAisle?.agvCount, selectedAisle?.locationCount, selectedAisle?.locationType, selectedAisle?.maxWeightKg]);

  useEffect(() => {
    if (!selectedZoneId) return;
    if (!rackGroups.length) {
      setSelectedRackKey(null);
      setSelectedLocationId(null);
      return;
    }

    if (isCreatingRack || isCreatingAisle) return;

    const hasSelectedRack = selectedRackKey ? rackGroups.some((rack) => rack.key === selectedRackKey) : false;
    const hasSelectedLocation = selectedLocationId ? locations.some((location) => location.id === selectedLocationId) : false;
    if (hasSelectedRack && hasSelectedLocation) return;

    const firstRack = rackGroups[0];
    setSelectedRackKey(firstRack.key);
    setFocusedAisleKey((current) => current || firstRack.aisle);
    if (!hasSelectedLocation) {
      const firstLocation = locations.find((location) => location.aisle === firstRack.aisle && location.rack === firstRack.rack);
      setSelectedLocationId(firstLocation?.id || null);
    }
  }, [isCreatingAisle, isCreatingRack, locations, rackGroups, selectedLocationId, selectedRackKey, selectedZoneId]);

  const createLocation = useMutation({
    mutationFn: async () =>
      createWarehouseLocation(activeWarehouseId, {
        zone_id: selectedZoneId,
        ...locationForm,
      }),
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successLocation", "Location added to the zone."));
      setLocationForm({
        barcode: "",
        aisle: "",
        rack: "",
        level: "",
        position: "",
        location_type: "storage",
        current_status: "available",
        is_agv_accessible: false,
      });
      setSelectedLocationId(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) }),
      ]);
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorLocation", "Could not add the location.")));
    },
  });

  const updateLocation = useMutation({
    mutationFn: async () =>
      updateWarehouseLocation(activeWarehouseId, selectedLocationId, locationForm),
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successLocationUpdated", "Location details saved."));
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorLocationUpdated", "Could not save the location.")));
    },
  });

  const deleteLocation = useMutation({
    mutationFn: async () => deleteWarehouseLocation(activeWarehouseId, selectedLocationId),
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successLocationDeleted", "Location removed from the zone."));
      setSelectedLocationId(null);
      setLocationForm({
        barcode: "",
        aisle: "",
        rack: "",
        level: "",
        position: "",
        location_type: "storage",
        current_status: "available",
        is_agv_accessible: false,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) }),
      ]);
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorLocationDeleted", "Could not delete the location.")));
    },
  });

  const updateRack = useMutation({
    mutationFn: async () => {
      if (!selectedRack) return;
      await configureRackRequest(activeWarehouseId, {
        zone_id: selectedZoneId,
        current_aisle: selectedRack.aisle,
        current_rack: selectedRack.rack,
        aisle: rackForm.aisle,
        rack: rackForm.rack,
        levels: rackForm.levels,
        slots_per_level: rackForm.slotsPerLevel,
        location_type: rackForm.location_type,
        is_agv_accessible: rackForm.is_agv_accessible,
        max_weight_kg: rackForm.max_weight_kg,
      });
    },
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successRackUpdated", "Rack details saved."));
      const nextRackKey = `${rackForm.aisle}::${rackForm.rack}`;
      setSelectedRackKey(nextRackKey);
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(getApiErrorMessage(err, t("planner.errorRackUpdated", "Could not save the rack.")));
    },
  });

  const createRack = useMutation({
    mutationFn: async () => {
      await createRackRequest(activeWarehouseId, {
        zone_id: selectedZoneId,
        aisle: rackForm.aisle,
        rack: rackForm.rack,
        levels: rackForm.levels,
        slots_per_level: rackForm.slotsPerLevel,
        location_type: rackForm.location_type,
        is_agv_accessible: rackForm.is_agv_accessible,
        max_weight_kg: rackForm.max_weight_kg,
      });
    },
    onSuccess: async () => {
      setError("");
      const rackKey = `${rackForm.aisle}::${rackForm.rack}`;
      const barcode = selectedZone ? `${selectedZone.code}-${rackForm.aisle}-${rackForm.rack}-01-01` : "";
      setSuccess(
        selectedZoneLayoutMode === "area"
          ? t("planner.successRowCreated", "A new row skeleton was added to this zone.")
          : t("planner.successRackCreated", "A new rack skeleton was added to this zone."),
      );
      setIsCreatingRack(false);
      setSelectedRackKey(rackKey);
      setFocusedAisleKey(rackForm.aisle);
      if (barcode) {
        setPendingLocationFocus({
          barcode,
          rackKey,
          aisle: rackForm.aisle,
        });
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) }),
      ]);
    },
    onError: (err: any) => {
      setSuccess("");
      setError(
        getApiErrorMessage(
          err,
          selectedZoneLayoutMode === "area"
            ? t("planner.errorRowCreated", "Could not add the row skeleton.")
            : t("planner.errorRackCreated", "Could not add the rack skeleton."),
        ),
      );
    },
  });

  const deleteRack = useMutation({
    mutationFn: async () => {
      if (!selectedRack) return;
      await deleteRackRequest(activeWarehouseId, {
        zone_id: selectedZoneId,
        aisle: selectedRack.aisle,
        rack: selectedRack.rack,
      });
    },
    onSuccess: async () => {
      setError("");
      setSuccess(t("planner.successRackDeleted", "Rack removed from the plan."));
      setSelectedRackKey(null);
      setSelectedLocationId(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) }),
      ]);
    },
    onError: (err: any) => {
      setSuccess("");
      const detail = getApiErrorMessage(err, t("planner.errorRackDeleted", "Could not delete the rack."));
      if (detail.includes("still has inventory")) {
        setError(
          selectedZoneLayoutMode === "area"
            ? t("planner.errorRowHasInventory", "This row still has inventory. Move or clear the affected locations before deleting the row.")
            : t("planner.errorRackHasInventory", "This rack still has inventory. Move or clear the affected locations before deleting the rack."),
        );
        return;
      }
      setError(detail);
    },
  });

  const updateAisle = useMutation({
    mutationFn: async () => {
      if (!selectedAisle) return;
      await configureAisleRequest(activeWarehouseId, {
        zone_id: selectedZoneId,
        current_aisle: selectedAisle.aisle,
        aisle: aisleForm.aisle,
        location_type: aisleForm.location_type,
        is_agv_accessible: aisleForm.is_agv_accessible,
        max_weight_kg: aisleForm.max_weight_kg,
      });
    },
    onSuccess: async () => {
      setError("");
      setSuccess(
        selectedZoneLayoutMode === "area"
          ? t("planner.successSectionUpdated", "Section details saved.")
          : t("planner.successAisleUpdated", "Aisle details saved."),
      );
      setFocusedAisleKey(aisleForm.aisle);
      await queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) });
    },
    onError: (err: any) => {
      setSuccess("");
      setError(
        getApiErrorMessage(
          err,
          selectedZoneLayoutMode === "area"
            ? t("planner.errorSectionUpdated", "Could not save the section.")
            : t("planner.errorAisleUpdated", "Could not save the aisle."),
        ),
      );
    },
  });

  const createAisle = useMutation({
    mutationFn: async () => {
      await createAisleRequest(activeWarehouseId, {
        zone_id: selectedZoneId,
        aisle: aisleForm.aisle,
        first_rack: aisleForm.firstRack,
        levels: aisleForm.levels,
        slots_per_level: aisleForm.slotsPerLevel,
        location_type: aisleForm.location_type,
        is_agv_accessible: aisleForm.is_agv_accessible,
        max_weight_kg: aisleForm.max_weight_kg,
      });
    },
    onSuccess: async () => {
      setError("");
      const rackKey = `${aisleForm.aisle}::${aisleForm.firstRack}`;
      const barcode = selectedZone ? `${selectedZone.code}-${aisleForm.aisle}-${aisleForm.firstRack}-01-01` : "";
      setSuccess(
        selectedZoneLayoutMode === "area"
          ? t("planner.successSectionCreated", "A new section was added to this zone.")
          : t("planner.successAisleCreated", "A new aisle was added to this zone."),
      );
      setIsCreatingAisle(false);
      setFocusedAisleKey(aisleForm.aisle);
      setSelectedRackKey(rackKey);
      if (barcode) {
        setPendingLocationFocus({
          barcode,
          rackKey,
          aisle: aisleForm.aisle,
        });
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) }),
      ]);
    },
    onError: (err: any) => {
      setSuccess("");
      setError(
        getApiErrorMessage(
          err,
          selectedZoneLayoutMode === "area"
            ? t("planner.errorSectionCreated", "Could not add the section.")
            : t("planner.errorAisleCreated", "Could not add the aisle."),
        ),
      );
    },
  });

  const deleteAisle = useMutation({
    mutationFn: async () => {
      if (!selectedAisle) return;
      await deleteAisleRequest(activeWarehouseId, {
        zone_id: selectedZoneId,
        aisle: selectedAisle.aisle,
      });
    },
    onSuccess: async () => {
      setError("");
      setSuccess(
        selectedZoneLayoutMode === "area"
          ? t("planner.successSectionDeleted", "Section removed from the plan.")
          : t("planner.successAisleDeleted", "Aisle removed from the plan."),
      );
      setFocusedAisleKey(null);
      setSelectedRackKey(null);
      setSelectedLocationId(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.locations(activeWarehouseId, selectedZoneId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.planner.zones(activeWarehouseId) }),
      ]);
    },
    onError: (err: any) => {
      setSuccess("");
      const detail = getApiErrorMessage(
        err,
        selectedZoneLayoutMode === "area"
          ? t("planner.errorSectionDeleted", "Could not delete the section.")
          : t("planner.errorAisleDeleted", "Could not delete the aisle."),
      );
      if (detail.includes("still has inventory")) {
        setError(
          selectedZoneLayoutMode === "area"
            ? t("planner.errorSectionHasInventory", "This section still has inventory. Move or clear the affected locations before deleting the section.")
            : t("planner.errorAisleHasInventory", "This aisle still has inventory. Move or clear the affected locations before deleting the aisle."),
        );
        return;
      }
      setError(detail);
    },
  });

  return (
    <div className="space-y-6">
      <section className="rounded-[1.8rem] border border-[#13212c]/10 bg-white/85 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.05)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.24em] text-[#5f6f7b]">{t("planner.eyebrow", "Warehouse planner")}</p>
            <h1 className="mt-2 text-[2rem] font-semibold tracking-[-0.04em] text-[#13212c]">
              {t("planner.title", "Plan the warehouse in a way the floor can use")}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#5f6f7c]">
              {t(
                "planner.body",
                "Use zones and placement rules to turn warehouse knowledge into a floor map the team can actually follow.",
              )}
            </p>
          </div>

          <div className="flex flex-wrap gap-2 lg:max-w-[460px] lg:justify-end">
            <span className="inline-flex items-center rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-medium text-[#13212c]">
              {t("planner.metricZones", "Planned zones")}: {totalZones}
            </span>
            <span className="inline-flex items-center rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-medium text-[#13212c]">
              {t("planner.metricLocations", "Mapped locations")}: {totalLocations}
            </span>
            <span className="inline-flex items-center rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-medium text-[#13212c]">
              {t("planner.metricRules", "Active placement rules")}: {enabledRuleCount}
            </span>
          </div>
        </div>
      </section>

      {success || error ? (
        <div
          className={`flex flex-wrap items-center justify-between gap-3 rounded-[1.2rem] border px-4 py-3 text-sm shadow-[0_12px_32px_rgba(19,33,44,0.05)] ${
            error
              ? "border-red-200 bg-red-50 text-red-700"
              : "border-emerald-200 bg-emerald-50 text-emerald-800"
          }`}
        >
          <p className="font-medium leading-6">{error || success}</p>
          <button
            type="button"
            onClick={() => {
              setSuccess("");
              setError("");
            }}
            className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] transition ${
              error
                ? "border-red-200 bg-white text-red-700 hover:bg-red-100"
                : "border-emerald-200 bg-white text-emerald-800 hover:bg-emerald-100"
            }`}
          >
            {t("common.close", "Close")}
          </button>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_380px]">
        <section className="overflow-hidden rounded-[2rem] border border-[#13212c]/10 bg-[linear-gradient(135deg,#13212c_0%,#1a2d39_60%,#253847_100%)] p-6 text-[#f4efe8] shadow-[0_30px_80px_rgba(19,33,44,0.16)]">
          <div className="mb-5 inline-flex items-center rounded-full border border-white/12 bg-white/6 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#cdd9e1]">
            {t("planner.workflowStepOneSection", "Step 01")} · {t("planner.workflowStepOneTitle", "Choose the warehouse shell")}
          </div>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#bfd2dc]">{t("planner.visualLayout", "Visual layout")}</p>
              <div className="rounded-full border border-[#f7bf45]/30 bg-[#f7bf45]/12 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">
                {t("planner.operatorMap", "operator map")}
              </div>
            </div>
            <h2 className="text-2xl font-semibold tracking-[-0.03em]">
              {t("planner.visualTitle", "Mark the warehouse shell first, then assign zones so people do not rely on guesswork.")}
            </h2>
            <p className="max-w-3xl text-sm leading-6 text-[#cdd9e1]">
              {!selectedZone
                ? showZoneDraftCard
                  ? t("planner.zoneDraftGuidance", "Use the draft card in the visual map above to define the new zone and its starter rack layout.")
                  : t("planner.zoneSelectGuidance", "Choose a zone from the visual map above to edit it, or click New zone to create the next one directly on the map.")
                : t("planner.warehouseProfileBody", "Use step 1 to confirm the warehouse name, site code, and operating timezone before you split zones or save placement rules.")}
            </p>
          </div>

          <div className="mt-5 flex min-w-0 flex-wrap items-center gap-3">
            <span className="text-[11px] uppercase tracking-[0.18em] text-[#bfd2dc]">
              {t("planner.warehouseLabel", "Warehouse")}
            </span>
            <span className="relative inline-flex w-full min-w-0 sm:w-auto">
              <select
                value={activeWarehouseId}
                onChange={(e) => setSelectedWarehouseId(e.target.value)}
                className="w-full min-w-0 max-w-full appearance-none truncate rounded-full border border-white/14 bg-[#20303b] px-4 py-2 pr-10 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10 sm:min-w-[270px]"
              >
                {warehouses.map((warehouse) => (
                  <option key={warehouse.id} value={warehouse.id} className="text-[#13212c]">
                    {warehouse.name} ({warehouse.code})
                  </option>
                ))}
              </select>
              <ChevronDown
                size={16}
                className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[#cdd9e1]"
              />
            </span>
            {activeWarehouse ? (
              <>
                <span className="max-w-full break-words rounded-full border border-white/15 px-3 py-2 text-xs uppercase tracking-[0.16em] text-[#eef5f9]">
                  {activeWarehouse.code}
                </span>
                <span className="max-w-full break-words rounded-full border border-white/15 px-3 py-2 text-xs uppercase tracking-[0.16em] text-[#dbe7ee]">
                  {activeWarehouse.timezone}
                </span>
              </>
            ) : null}
          </div>

          <div className="mt-6 rounded-[1.5rem] border border-white/10 bg-white/6 p-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#bfd2dc]">
                  {t("planner.warehouseProfile", "Warehouse profile")}
                </p>
                <p className="mt-2 text-sm leading-6 text-[#cdd9e1]">
                  {t(
                    "planner.warehouseProfileBody",
                    "Use step 1 to confirm the warehouse name, site code, and operating timezone before you split zones or save placement rules.",
                  )}
                </p>
              </div>
              <Link
                to="/warehouses"
                className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-4 py-2 text-xs font-medium uppercase tracking-[0.14em] text-[#f7fbfd] transition hover:bg-white/12"
              >
                {t("planner.openWarehouseMaster", "Open warehouse master")}
                <ArrowRight size={14} />
              </Link>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="inline-flex max-w-full items-center break-words rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-[#f0f6fa]">
                {warehouseDraft.name || t("planner.warehouseNamePlaceholder", "Budapest Demo DC")}
              </span>
              <span className="inline-flex max-w-full items-center break-words rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs uppercase tracking-[0.14em] text-[#dbe7ee]">
                {warehouseDraft.code || "BUDDEMO"}
              </span>
              <span className="inline-flex max-w-full items-center break-words rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-[#dbe7ee]">
                {warehouseDraft.timezone}
              </span>
              <span
                className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs ${
                  warehouseDirty
                    ? "border-[#f7bf45]/24 bg-[#f7bf45]/12 text-[#f7d472]"
                    : "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
                }`}
              >
                {warehouseDirty
                  ? t("planner.warehouseDirtyHint", "The current warehouse has unsaved basic details.")
                  : t("planner.warehouseSavedHint", "The current warehouse profile is already in sync.")}
              </span>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <PlannerActionButton
                type="button"
                tone="accent"
                size="sm"
                disabled={
                  !activeWarehouseId ||
                  !warehouseDraft.name ||
                  !warehouseDraft.code ||
                  !warehouseDraft.timezone ||
                  !warehouseDirty ||
                  saveWarehouse.isPending
                }
                onClick={() => saveWarehouse.mutate()}
              >
                {saveWarehouse.isPending
                  ? t("planner.savingWarehouse", "Saving warehouse...")
                  : t("planner.saveWarehouse", "Save warehouse details")}
                <ArrowRight size={14} />
              </PlannerActionButton>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-3">
                <FieldDark label={t("common.name", "Name")}>
                  <input
                    type="text"
                    value={warehouseDraft.name}
                    onChange={(e) => setWarehouseDraft({ ...warehouseDraft, name: e.target.value })}
                    placeholder={t("planner.warehouseNamePlaceholder", "Budapest Demo DC")}
                    className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                  />
                </FieldDark>
                <FieldDark label={t("common.code", "Code")}>
                  <input
                    type="text"
                    value={warehouseDraft.code}
                    onChange={(e) => setWarehouseDraft({ ...warehouseDraft, code: e.target.value.toUpperCase() })}
                    placeholder="BUDDEMO"
                    className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm uppercase text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                  />
                </FieldDark>
                <FieldDark label={t("warehouses.timezone", "Timezone")}>
                  <span className="relative inline-flex w-full">
                    <select
                      value={warehouseDraft.timezone}
                      onChange={(e) => setWarehouseDraft({ ...warehouseDraft, timezone: e.target.value })}
                      className="w-full appearance-none rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 pr-10 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                    >
                      {timezoneOptions.map((option) => (
                        <option key={option} value={option} className="text-[#13212c]">
                          {option}
                        </option>
                      ))}
                    </select>
                    <ChevronDown
                      size={16}
                      className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[#cdd9e1]"
                    />
                  </span>
                </FieldDark>
              </div>
          </div>

            <div className="mt-6 rounded-[1.8rem] border border-white/10 bg-[#0d1922] p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-[#c1d4de]">{t("planner.flowPicture", "Flow picture")}</p>
                  <p className="mt-1.5 text-base font-semibold text-white">{t("planner.flowPictureTitle", "Main entry, storage zones, and dispatch side")}</p>
                </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1 text-xs uppercase tracking-[0.14em] text-[#eef5f9]">
                <Map size={13} />
                {t("planner.zoneView", "zone view")}
              </div>
              <button
                type="button"
                onClick={prepareNewZone}
                className="inline-flex items-center gap-2 rounded-full border border-[#f7bf45]/24 bg-[#f7bf45]/12 px-3.5 py-2 text-xs font-medium uppercase tracking-[0.14em] text-[#f7d472] transition hover:bg-[#f7bf45]/18"
              >
                <Plus size={14} />
                {t("planner.newZoneButton", "New zone")}
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {[
                t("planner.legendDock", "Dock / entry"),
                t("planner.legendReserve", "Reserve storage"),
                t("planner.legendPacking", "Packing"),
                t("planner.legendQc", "QC hold"),
                t("planner.legendDispatch", "Dispatch"),
              ].map((label, index) => (
                <span
                  key={label}
                  className="inline-flex items-center rounded-full px-3 py-1.5 text-[11px] font-medium"
                  style={{
                    backgroundColor: ["#f7bf4520", "#8db6ff20", "#87c6a120", "#f28a7d20", "#b7a6ff20"][index],
                    color: "#f4efe8",
                    border: "1px solid rgba(255,255,255,0.08)",
                  }}
                >
                  {label}
                </span>
              ))}
            </div>

            <div className="mt-4 grid gap-3.5 lg:grid-cols-[156px_minmax(0,1fr)]">
              <div className="rounded-[1.25rem] border border-dashed border-[#f7bf45]/45 bg-[#f7bf45]/10 p-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#f7bf45]">{t("planner.entryDock", "Entry / dock")}</p>
                <p className="mt-1.5 text-sm leading-6 text-[#f0e8d5]">
                  {t(
                    "planner.entryDockDetail",
                    "Place inbound staging and outbound dispatch here so the customer can relate the digital map to the real floor.",
                  )}
                </p>
              </div>

              <div className="grid min-h-[232px] gap-3 rounded-[1.25rem] border border-white/8 bg-[#13212c] p-3 md:grid-cols-2">
                {zoneBlocks.length === 0 && !showZoneDraftCard ? (
                  <div className="col-span-full flex items-center justify-center rounded-[1.2rem] border border-dashed border-white/10 text-sm text-[#9cb0bc]">
                    {t("planner.emptyZones", "Add the first warehouse zone to start the visual map.")}
                  </div>
                ) : (
                  <>
                    {zoneBlocks.map((zone) => (
                      <button
                        key={zone.id}
                        type="button"
                        onClick={() => {
                          setSelectedZoneId(zone.id);
                          setShowZoneDraftCard(false);
                          setSuccess("");
                          setError("");
                        }}
                        className={`rounded-[1.05rem] border p-3 text-left transition ${
                          selectedZoneId === zone.id
                            ? "border-[#f7bf45]/70 bg-[#17222c] shadow-[0_16px_36px_rgba(247,191,69,0.16)] ring-2 ring-[#f7bf45]/30"
                            : "border-white/10 hover:border-white/18"
                        }`}
                        style={{ background: `linear-gradient(135deg, ${zone.color}22, rgba(255,255,255,0.04))` }}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[15px] font-semibold leading-5 text-white">{zone.name}</p>
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            <span className="rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]" style={{ backgroundColor: zone.color }}>
                              {zone.code}
                            </span>
                          </div>
                        </div>
                        <div className="mt-2.5 flex flex-wrap gap-2">
                          <span className="rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-[11px] font-medium text-[#d5e1e8]">
                            {t("planner.mappedLocationsCompact", "{count} locations", {
                              count: String(zone.location_count),
                            })}
                          </span>
                          <span className="rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-[11px] font-medium text-[#d5e1e8]">
                            {zone.layout_mode === "area"
                              ? t("planner.layoutModeAreaCompact", "Area layout")
                              : t("planner.layoutModeRackCompact", "Rack layout")}
                          </span>
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${zone.is_agv_zone ? "border-[#8db6ff]/24 bg-[#8db6ff]/12 text-[#cfe0ff]" : "border-[#f7bf45]/24 bg-[#f7bf45]/12 text-[#f7d472]"}`}>
                            {zone.is_agv_zone
                              ? t("planner.agvReadyZoneCompact", "AGV")
                              : t("planner.manualZoneCompact", "Manual")}
                          </span>
                        </div>
                      </button>
                    ))}
                    {showZoneDraftCard ? (
                      <div className="rounded-[1.2rem] border border-dashed border-[#8db6ff]/45 bg-[#12202a] p-4 text-left">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[11px] uppercase tracking-[0.16em] text-[#9cb0bc]">
                              {t("planner.newZoneCardEyebrow", "New zone draft")}
                            </p>
                            <p className="mt-1 text-lg font-semibold text-white">
                              {zoneForm.name || t("planner.newZoneCardTitle", "Define the next zone directly on the map")}
                            </p>
                          </div>
                          <span className="rounded-full border border-[#8db6ff]/24 bg-[#8db6ff]/14 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.14em] text-[#cfe0ff]">
                            {t("planner.newZoneCardChip", "Draft")}
                          </span>
                        </div>
                        <div className="mt-4 grid gap-3">
                          <input
                            type="text"
                            value={zoneForm.name}
                            onChange={(e) => setZoneForm({ ...zoneForm, name: e.target.value })}
                            placeholder={t("planner.zoneNamePlaceholder", "Cold chain reserve")}
                            className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#8db6ff]/45 focus:ring-4 focus:ring-[#8db6ff]/10"
                          />
                          <div className="grid gap-3 md:grid-cols-2">
                            <input
                              type="text"
                              value={zoneForm.code}
                              onChange={(e) => setZoneForm({ ...zoneForm, code: e.target.value.toUpperCase() })}
                              placeholder={t("planner.zoneCodePlaceholder", "COLD")}
                              className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm uppercase text-white outline-none transition focus:border-[#8db6ff]/45 focus:ring-4 focus:ring-[#8db6ff]/10"
                            />
                            <input
                              type="number"
                              min={0}
                              value={zoneForm.sequence}
                              onChange={(e) => setZoneForm({ ...zoneForm, sequence: Number(e.target.value) })}
                              className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#8db6ff]/45 focus:ring-4 focus:ring-[#8db6ff]/10"
                            />
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {(["rack", "area"] as LayoutMode[]).map((mode) => (
                              <button
                                key={mode}
                                type="button"
                                onClick={() => setZoneForm({ ...zoneForm, layout_mode: mode })}
                                className={`rounded-full border px-3 py-2 text-xs font-medium uppercase tracking-[0.14em] transition ${
                                  zoneForm.layout_mode === mode
                                    ? "border-[#8db6ff]/45 bg-[#8db6ff]/16 text-[#cfe0ff]"
                                    : "border-white/10 bg-[#20303b] text-[#d5e1e8] hover:bg-[#223743]"
                                }`}
                              >
                                {mode === "area"
                                  ? t("planner.layoutModeArea", "Area-first")
                                  : t("planner.layoutModeRack", "Rack-first")}
                              </button>
                            ))}
                          </div>
                          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            <FieldDark label={zoneForm.layout_mode === "area" ? t("planner.zoneBlueprintSections", "Sections") : t("planner.zoneBlueprintAisles", "Aisles")}>
                              <input
                                type="number"
                                min={1}
                                value={zoneBlueprint.aisles}
                                onChange={(e) => setZoneBlueprint({ ...zoneBlueprint, aisles: Number(e.target.value) })}
                                className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#8db6ff]/45 focus:ring-4 focus:ring-[#8db6ff]/10"
                              />
                            </FieldDark>
                            <FieldDark label={zoneForm.layout_mode === "area" ? t("planner.zoneBlueprintRows", "Rows per section") : t("planner.zoneBlueprintRacks", "Racks per aisle")}>
                              <input
                                type="number"
                                min={1}
                                value={zoneBlueprint.racksPerAisle}
                                onChange={(e) => setZoneBlueprint({ ...zoneBlueprint, racksPerAisle: Number(e.target.value) })}
                                className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#8db6ff]/45 focus:ring-4 focus:ring-[#8db6ff]/10"
                              />
                            </FieldDark>
                            <FieldDark label={zoneForm.layout_mode === "area" ? t("planner.zoneBlueprintLevelsArea", "Levels per row") : t("planner.zoneBlueprintLevels", "Levels per rack")}>
                              <input
                                type="number"
                                min={1}
                                value={zoneBlueprint.levelsPerRack}
                                onChange={(e) => setZoneBlueprint({ ...zoneBlueprint, levelsPerRack: Number(e.target.value) })}
                                className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#8db6ff]/45 focus:ring-4 focus:ring-[#8db6ff]/10"
                              />
                            </FieldDark>
                            <FieldDark label={t("planner.zoneBlueprintSlots", "Slots per level")}>
                              <input
                                type="number"
                                min={1}
                                value={zoneBlueprint.slotsPerLevel}
                                onChange={(e) => setZoneBlueprint({ ...zoneBlueprint, slotsPerLevel: Number(e.target.value) })}
                                className="w-full rounded-2xl border border-white/12 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#8db6ff]/45 focus:ring-4 focus:ring-[#8db6ff]/10"
                              />
                            </FieldDark>
                          </div>
                          <p className="text-xs leading-6 text-[#c4d6df]">
                            {zoneForm.layout_mode === "area"
                              ? t("planner.layoutModeAreaHint", "Use this when the zone is mostly floor or bulk storage and operators think in sections and rows, not physical racks.")
                              : t("planner.layoutModeRackHint", "Use this when operators really navigate by aisle and rack on the floor.")}
                          </p>
                          <label className="flex items-start gap-3 rounded-[1rem] border border-white/10 bg-[#0f1d27] px-4 py-3 text-sm leading-6 text-[#d5e1e8]">
                            <input
                              type="checkbox"
                              checked={zoneForm.is_agv_zone}
                              onChange={(e) => setZoneForm({ ...zoneForm, is_agv_zone: e.target.checked })}
                              className="mt-1 h-4 w-4 accent-[#8db6ff]"
                            />
                            <span>
                              {zoneForm.layout_mode === "area"
                                ? t("planner.zoneBlueprintAgvArea", "Make the starter locations in this zone AGV-accessible from day one.")
                                : t("planner.zoneBlueprintAgv", "Make the starter racks in this zone AGV-accessible from day one.")}
                            </span>
                          </label>
                          <p className="text-xs leading-6 text-[#c4d6df]">
                            {t("planner.zoneBlueprintSummary", "This draft will create {count} starter locations in the new zone.", {
                              count: String(zoneBlueprint.aisles * zoneBlueprint.racksPerAisle * zoneBlueprint.levelsPerRack * zoneBlueprint.slotsPerLevel),
                            })}
                          </p>
                          <div className="flex flex-wrap gap-3">
                            <button
                              type="button"
                              disabled={!activeWarehouseId || !zoneForm.name || !zoneForm.code || addZone.isPending}
                              onClick={() => addZone.mutate()}
                              className="inline-flex items-center gap-2 rounded-full bg-[#f7bf45] px-4 py-2.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#f9c75f] disabled:opacity-50"
                            >
                              <ArrowRight size={14} />
                              {addZone.isPending ? t("planner.addingZone", "Adding zone...") : t("planner.addZoneAction", "Add zone to plan")}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setShowZoneDraftCard(false);
                                setZoneForm({ name: "", code: "", is_agv_zone: false, sequence: (orderedZones.at(-1)?.sequence ?? 0) + 1, layout_mode: "rack" });
                                setZoneBlueprint({ aisles: 3, racksPerAisle: 4, levelsPerRack: 3, slotsPerLevel: 6 });
                              }}
                              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2.5 text-xs font-medium uppercase tracking-[0.14em] text-[#d5e1e8] transition hover:bg-white/10"
                            >
                              {t("common.cancel", "Cancel")}
                            </button>
                          </div>
                          {addZone.isPending ? (
                            <p className="text-xs leading-6 text-[#9cb0bc]">
                              {t(
                                "planner.addingZoneHint",
                                "Creating the zone and its starting locations. They will appear in the zone view above when done.",
                              )}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </div>

              <div className="mt-4 rounded-[1.25rem] border border-white/8 bg-[#13212c] p-3">
                <div className="flex flex-col gap-1.5 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#c4d6df]">{heatEyebrow}</p>
                    <p className="mt-1.5 text-base font-semibold text-white">
                      {heatTitle}
                    </p>
                  </div>
                </div>

              <div className="mt-3 rounded-[1rem] border border-white/8 bg-[#0f1d27] px-3 py-2.5">
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#c4d6df]">
                      {t("planner.focusRibbon", "Current focus")}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <FocusChip label={t("planner.focusZone", "Zone")} value={selectedZone?.name || "—"} tone="amber" active={zoneHeatActive} />
                    <FocusChip label={layoutTerms.primary} value={focusedAisleKey ? `${layoutTerms.primary} ${focusedAisleKey}` : "—"} tone="blue" active={aisleHeatActive} />
                    <FocusChip label={layoutTerms.secondary} value={selectedRack ? `${layoutTerms.secondary} ${selectedRack.rack}` : "—"} tone="green" active={rackHeatActive} />
                    <FocusChip label={t("planner.focusLocation", "Slot")} value={selectedLocation?.barcode || "—"} tone="slate" active={slotHeatActive} />
                  </div>
                </div>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <div className={`rounded-[1rem] border bg-[#0f1d27] px-3 py-3 shadow-[inset_0_1px_0_rgba(247,191,69,0.18)] transition ${zoneHeatActive ? "border-[#f7bf45]/28 ring-1 ring-[#f7bf45]/18" : "border-white/8"}`}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-[#c4d6df]">
                      {t("planner.inventoryHeatZones", "Zone distribution")}
                    </p>
                    <span className="rounded-full border border-[#f7bf45]/20 bg-[#f7bf45]/12 px-2.5 py-1 text-[11px] font-semibold text-[#f7d472]">
                      {zoneHeatmap.reduce((sum, segment) => sum + segment.units, 0)} {t("planner.inventoryHeatUnitShort", "units")}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[11px] leading-5 text-[#c4d6df]">
                      {t("planner.inventoryHeatZonesHint", "Click a zone here to drive the rest of the planner.")}
                  </p>
                  <PlannerHeatStrip
                    segments={zoneHeatmap.map((segment) => ({ label: segment.label, units: segment.units }))}
                  />
                  <div className="mt-2.5 space-y-2">
                    {zoneHeatmap.map((segment) => (
                      <button
                        key={`planner-zone-heat-${segment.label}`}
                        type="button"
                        onClick={() => selectZoneFromHeat(segment.label)}
                            className={`flex w-full items-center justify-between gap-3 rounded-[0.9rem] border px-3 py-2 text-left text-xs transition ${
                              selectedZone?.code === segment.label
                            ? "border-[#f7bf45]/45 bg-[#2a2417] text-white shadow-[0_12px_28px_rgba(247,191,69,0.12)]"
                            : "border-white/8 bg-[#13212c] text-[#cdd9e1] hover:bg-[#172632]"
                            }`}
                      >
                        <span className="font-medium">{segment.name}</span>
                        <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] font-semibold text-[#f4efe8]">
                          {t("planner.inventoryHeatUnits", "{units} units · {count} slots used", {
                            units: String(segment.units),
                            count: String(segment.occupiedCount),
                          })}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className={`rounded-[1rem] border bg-[#0f1d27] px-3 py-3 shadow-[inset_0_1px_0_rgba(141,182,255,0.18)] transition ${aisleHeatActive ? "border-[#8db6ff]/28 ring-1 ring-[#8db6ff]/18" : "border-white/8"}`}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-[#c4d6df]">
                      {selectedZoneLayoutMode === "area" ? t("planner.inventoryHeatAreas", "Focused zone sections") : t("planner.inventoryHeatAisles", "Focused zone aisles")}
                    </p>
                    {focusedAisleKey ? (
                      <span className="rounded-full border border-[#8db6ff]/24 bg-[#8db6ff]/12 px-2.5 py-1 text-[11px] font-semibold text-[#cfe0ff]">
                        {`${layoutTerms.primary} ${focusedAisleKey}`}
                      </span>
                    ) : null}
                  </div>
                      <p className="mt-1.5 text-[11px] leading-5 text-[#c4d6df]">
                    {selectedZoneLayoutMode === "area" ? t("planner.inventoryHeatAreasHint", "Click a section to narrow the row view below.") : t("planner.inventoryHeatAislesHint", "Click an aisle to narrow the rack view below.")}
                  </p>
                  {aisleHeatmap.length ? (
                    <>
                      <PlannerHeatStrip
                        segments={aisleHeatmap.map((segment) => ({ label: segment.label, units: segment.units }))}
                      />
                      <div className="mt-2.5 space-y-2">
                        {aisleHeatmap.map((segment) => (
                          <button
                            key={`planner-aisle-heat-${segment.label}`}
                            type="button"
                            onClick={() => selectAisleFromHeat(segment.label)}
                            className={`flex w-full items-center justify-between gap-3 rounded-[0.9rem] border px-3 py-2 text-left text-xs transition ${
                              focusedAisleKey === segment.label
                                ? "border-[#8db6ff]/45 bg-[#162536] text-white shadow-[0_12px_28px_rgba(141,182,255,0.14)]"
                                : "border-white/8 bg-[#13212c] text-[#cdd9e1] hover:bg-[#172632]"
                            }`}
                          >
                            <span className="font-medium">
                              {`${layoutTerms.primary} ${segment.label}`}
                            </span>
                            <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] font-semibold text-[#f4efe8]">
                              {t("planner.inventoryHeatUnits", "{units} units · {count} slots used", {
                                units: String(segment.units),
                                count: String(segment.occupiedCount),
                              })}
                            </span>
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="mt-3 text-sm leading-6 text-[#9cb0bc]">
                      {selectedZoneLayoutMode === "area" ? t("planner.inventoryHeatChooseZoneArea", "Select a zone above to see which sections already hold more stock.") : t("planner.inventoryHeatChooseZone", "Select a zone above to see which aisles are already denser.")}
                    </p>
                  )}
                </div>

                <div className={`rounded-[1rem] border bg-[#0f1d27] px-3 py-3 shadow-[inset_0_1px_0_rgba(135,198,161,0.18)] transition ${slotHeatActive || rackHeatActive ? "border-[#87c6a1]/28 ring-1 ring-[#87c6a1]/18" : "border-white/8"}`}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-[#c4d6df]">
                      {selectedZoneLayoutMode === "area" ? t("planner.inventoryHeatRows", "Focused row slots") : t("planner.inventoryHeatRack", "Focused rack slots")}
                    </p>
                    {selectedRack ? (
                      <span className="rounded-full border border-[#87c6a1]/24 bg-[#87c6a1]/12 px-2.5 py-1 text-[11px] font-semibold text-[#c7f3d6]">
                        {`${layoutTerms.secondary} ${selectedRack.rack}`}
                      </span>
                    ) : null}
                  </div>
                    <p className="mt-1.5 text-[11px] leading-5 text-[#c4d6df]">
                    {t("planner.inventoryHeatRackHint", "Click a slot to jump straight into location editing.")}
                  </p>
                  {rackHeatmap.length ? (
                    <>
                      <PlannerHeatStrip
                        segments={rackHeatmap.map((segment) => ({ label: segment.label, units: segment.units }))}
                      />
                      <div className="mt-2.5 space-y-2">
                        {rackHeatmap.map((segment) => (
                          <button
                            key={`planner-rack-heat-${segment.barcode}`}
                            type="button"
                            onClick={() => selectLocationFromHeat(segment.barcode)}
                            className={`flex w-full items-center justify-between gap-3 rounded-[0.9rem] border px-3 py-2 text-left text-xs transition ${
                              selectedLocation?.barcode === segment.barcode
                                ? "border-[#87c6a1]/45 bg-[#153025] text-white shadow-[0_12px_28px_rgba(135,198,161,0.14)]"
                                : "border-white/8 bg-[#13212c] text-[#cdd9e1] hover:bg-[#172632]"
                            }`}
                          >
                            <span className="font-medium">{segment.barcode}</span>
                            <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] font-semibold text-[#f4efe8]">
                              {t("planner.inventoryHeatRackUnits", "{units} units", { units: String(segment.units) })}
                            </span>
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="mt-3 text-sm leading-6 text-[#c4d6df]">
                      {selectedZoneLayoutMode === "area" ? t("planner.inventoryHeatChooseRow", "Select a row below to see which exact slots are carrying stock.") : t("planner.inventoryHeatChooseRack", "Select a rack below to see which exact slots are carrying stock.")}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {selectedZone ? (
              <div
                ref={aisleEditorRef}
                className={`mt-4 rounded-[1.2rem] border bg-[#f7f4ee] p-3.5 transition ${
                  selectedAisle || isCreatingAisle ? "border-[#93a4b4]/24 ring-1 ring-[#93a4b4]/14" : "border-[#13212c]/10"
                }`}
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                      {selectedZoneLayoutMode === "area"
                        ? selectedAisle && !isCreatingAisle
                          ? t("planner.editSection", "Edit section")
                          : t("planner.addSection", "Add section")
                        : selectedAisle && !isCreatingAisle
                          ? t("planner.editAisle", "Edit aisle")
                          : t("planner.addAisle", "Add aisle")}
                    </p>
                    <p className="mt-1 text-base font-semibold text-[#13212c]">
                      {selectedZoneLayoutMode === "area"
                        ? selectedAisle && !isCreatingAisle
                          ? t("planner.editSectionTitle", "Update the selected section")
                          : t("planner.addSectionTitle", "Create the next section in this zone")
                        : selectedAisle && !isCreatingAisle
                          ? t("planner.editAisleTitle", "Update the selected aisle")
                          : t("planner.addAisleTitle", "Create the next aisle in this zone")}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <PlannerActionButton type="button" tone="secondary" size="sm" onClick={prepareNewAisle}>
                      <Plus size={14} />
                      {selectedZoneLayoutMode === "area"
                        ? t("planner.newSectionButton", "New section")
                        : t("planner.newAisleButton", "New aisle")}
                    </PlannerActionButton>
                    {!isCreatingAisle && selectedAisle ? (
                      <>
                        <PlannerActionButton
                          type="button"
                          tone="primary"
                          size="sm"
                          disabled={!aisleEditorDirty || updateAisle.isPending}
                          onClick={() => updateAisle.mutate()}
                        >
                          {updateAisle.isPending
                            ? selectedZoneLayoutMode === "area"
                              ? t("planner.savingSection", "Saving section...")
                              : t("planner.savingAisle", "Saving aisle...")
                            : selectedZoneLayoutMode === "area"
                              ? t("planner.saveSection", "Save section")
                              : t("planner.saveAisle", "Save aisle")}
                        </PlannerActionButton>
                        <PlannerActionButton
                          type="button"
                          tone="danger"
                          size="sm"
                          disabled={deleteAisle.isPending}
                          onClick={() => {
                            if (window.confirm(
                              selectedZoneLayoutMode === "area"
                                ? t("planner.deleteSectionConfirm", "Delete this section from the zone?")
                                : t("planner.deleteAisleConfirm", "Delete this aisle from the zone?"),
                            )) {
                              deleteAisle.mutate();
                            }
                          }}
                        >
                          {deleteAisle.isPending
                            ? selectedZoneLayoutMode === "area"
                              ? t("planner.deletingSection", "Deleting section...")
                              : t("planner.deletingAisle", "Deleting aisle...")
                            : selectedZoneLayoutMode === "area"
                              ? t("planner.deleteSection", "Delete section")
                              : t("planner.deleteAisle", "Delete aisle")}
                        </PlannerActionButton>
                      </>
                    ) : isCreatingAisle ? (
                      <PlannerActionButton
                        type="button"
                        tone="primary"
                        size="sm"
                        disabled={!aisleCreateReady || createAisle.isPending}
                        onClick={() => createAisle.mutate()}
                      >
                        {createAisle.isPending
                          ? selectedZoneLayoutMode === "area"
                            ? t("planner.creatingSection", "Creating section...")
                            : t("planner.creatingAisle", "Creating aisle...")
                          : selectedZoneLayoutMode === "area"
                            ? t("planner.createSection", "Create section")
                            : t("planner.createAisle", "Create aisle")}
                      </PlannerActionButton>
                    ) : null}
                  </div>
                </div>

                {selectedAisle && !isCreatingAisle ? (
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-[11px] font-medium text-[#13212c]">
                      {`${layoutTerms.primary} ${selectedAisle.aisle}`}
                    </span>
                    <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-[11px] font-medium text-[#61717d]">
                      {t("planner.mappedLocationsCompact", "{count} locations", { count: String(selectedAisle.locationCount) })}
                    </span>
                  </div>
                ) : null}

                {(isCreatingAisle || selectedAisle) ? (
                  <>
                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      <Field label={layoutTerms.primary}>
                        <input
                          type="text"
                          value={aisleForm.aisle}
                          onChange={(e) => setAisleForm({ ...aisleForm, aisle: e.target.value.toUpperCase() })}
                          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                      {isCreatingAisle ? (
                        <Field label={selectedZoneLayoutMode === "area" ? t("planner.firstRowCode", "First row code") : t("planner.firstRackCode", "First rack code")}>
                          <input
                            type="text"
                            value={aisleForm.firstRack}
                            onChange={(e) => setAisleForm({ ...aisleForm, firstRack: e.target.value.toUpperCase() })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                      ) : null}
                    </div>

                    {isCreatingAisle ? (
                      <div className="mt-4 grid gap-4 md:grid-cols-3">
                        <Field label={selectedZoneLayoutMode === "area" ? t("planner.zoneBlueprintLevelsArea", "Levels per row") : t("planner.zoneBlueprintLevels", "Levels per rack")}>
                          <input
                            type="number"
                            min={1}
                            value={aisleForm.levels}
                            onChange={(e) => setAisleForm({ ...aisleForm, levels: Number(e.target.value) })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                        <Field label={t("planner.zoneBlueprintSlots", "Slots per level")}>
                          <input
                            type="number"
                            min={1}
                            value={aisleForm.slotsPerLevel}
                            onChange={(e) => setAisleForm({ ...aisleForm, slotsPerLevel: Number(e.target.value) })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                        <Field label={t("planner.maxLoad", "Max load")}><input
                          type="number"
                          min={0}
                          value={aisleForm.max_weight_kg}
                          onChange={(e) => setAisleForm({ ...aisleForm, max_weight_kg: Number(e.target.value) })}
                          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                        /></Field>
                      </div>
                    ) : (
                      <div className="mt-4 grid gap-4 md:grid-cols-2">
                        <Field label={t("planner.maxLoad", "Max load")}><input
                          type="number"
                          min={0}
                          value={aisleForm.max_weight_kg}
                          onChange={(e) => setAisleForm({ ...aisleForm, max_weight_kg: Number(e.target.value) })}
                          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                        /></Field>
                      </div>
                    )}

                    <div className="mt-5 rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                      <div className="mb-3">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                          {selectedZoneLayoutMode === "area"
                            ? t("planner.sectionProperties", "Section properties")
                            : t("planner.aisleProperties", "Aisle properties")}
                        </p>
                        <p className="mt-1 text-sm text-[#61717d]">
                          {selectedZoneLayoutMode === "area"
                            ? t("planner.sectionPropertiesHint", "After the section code is right, adjust storage type, load, and AGV access here.")
                            : t("planner.aislePropertiesHint", "After the aisle code is right, adjust storage type, load, and AGV access here.")}
                        </p>
                      </div>
                      <div className="grid gap-4 md:grid-cols-3">
                        <Field label={t("planner.locationType", "Location type")}>
                          <select
                            value={aisleForm.location_type}
                            onChange={(e) => setAisleForm({ ...aisleForm, location_type: e.target.value })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          >
                            {["storage", "staging", "dock", "quality", "packing", "charging"].map((option) => (
                              <option key={option} value={option}>
                                {describeLocationType(option)}
                              </option>
                            ))}
                          </select>
                        </Field>
                      <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-white px-4 py-4 text-sm leading-6 text-[#61717d]">
                        <input
                          type="checkbox"
                          checked={aisleForm.is_agv_accessible}
                          onChange={(e) => setAisleForm({ ...aisleForm, is_agv_accessible: e.target.checked })}
                          className="mt-1 h-4 w-4 accent-[#13212c]"
                        />
                        <span>
                          {selectedZoneLayoutMode === "area"
                            ? t("planner.sectionAgv", "Mark every row location in this section as AGV-accessible.")
                            : t("planner.aisleAgv", "Mark every rack location in this aisle as AGV-accessible.")}
                          </span>
                      </label>
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="mt-4 text-sm leading-6 text-[#61717d]">
                    {selectedZoneLayoutMode === "area"
                      ? t("planner.sectionEditorHint", "Pick a section from the heat view or start a new one here.")
                      : t("planner.aisleEditorHint", "Pick an aisle from the heat view or start a new one here.")}
                  </p>
                )}
              </div>
            ) : null}

            <div className={`mt-4 rounded-[1.25rem] border bg-[#13212c] p-3 shadow-[inset_0_1px_0_rgba(141,182,255,0.18)] transition ${rackHeatActive ? "border-[#8db6ff]/24 ring-1 ring-[#8db6ff]/16" : "border-white/8"}`}>
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#bfd2dc]">{secondaryViewEyebrow}</p>
                  <p className="mt-1.5 text-base font-semibold text-white">
                    {secondaryViewTitle}
                  </p>
                </div>
                <div className="flex flex-col items-start gap-2 md:items-end">
                  <span className="rounded-full border border-white/10 bg-[#0f1d27] px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-[#cdd9e1]">
                    {secondaryViewHint}
                  </span>
                  <button
                    type="button"
                    onClick={prepareNewRack}
                    className="inline-flex items-center gap-2 rounded-full border border-[#8db6ff]/24 bg-[#8db6ff]/12 px-3.5 py-2 text-xs font-medium uppercase tracking-[0.14em] text-[#cfe0ff] transition hover:bg-[#8db6ff]/18"
                  >
                    <Plus size={14} />
                    {newGroupButtonLabel}
                  </button>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <PlannerLegendChip label={t("planner.slotLegendSuggested", "Suggested slot")} className="border-[#f7bf45]/30 bg-[#f7bf45]/16 text-[#f7d472]" />
                <PlannerLegendChip label={t("planner.slotLegendManual", "Manual slot")} className="border-white/10 bg-white/8 text-[#cdd9e1]" />
                <PlannerLegendChip label={t("planner.slotLegendSelected", "Selected slot")} className="border-[#8db6ff]/24 bg-[#8db6ff]/14 text-[#cfe0ff]" />
              </div>

              <div className="relative mt-3 rounded-[1.15rem] border border-white/8 bg-[#0f1d27] px-3 py-3">
                <div className="absolute left-8 right-8 top-1/2 h-px -translate-y-1/2 bg-[linear-gradient(90deg,rgba(255,255,255,0.06),rgba(255,255,255,0.22),rgba(255,255,255,0.06))]" />
                <div className="relative grid gap-3 md:grid-cols-3">
                  {selectedZone ? (
                    displayedRackGroups.length > 0 ? (
                      displayedRackGroups.map((rack) => (
                        <button
                          key={rack.key}
                          type="button"
                          onClick={() => selectRack(rack.key)}
                          className={`rounded-[0.95rem] border p-3 text-left transition ${
                            selectedRackKey === rack.key
                              ? "border-[#8db6ff]/45 bg-[#172632] shadow-[0_14px_32px_rgba(141,182,255,0.16)] ring-2 ring-[#8db6ff]/24"
                              : "border-white/8 bg-[#13212c] hover:bg-[#172632]"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <p className="text-[11px] uppercase tracking-[0.16em] text-[#c4d6df]">
                              {`${layoutTerms.secondary} ${rack.rack}`}
                            </p>
                            <span className="rounded-full border border-white/15 bg-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-[#eef5f9]">
                              {`${layoutTerms.primary} ${rack.aisle}`}
                            </span>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <span className="rounded-full border border-white/10 bg-[#0d1922] px-2.5 py-1 text-[11px] font-medium text-white">
                              {t("planner.rackLocationCountCompact", "{count} locations", { count: String(rack.locationCount) })}
                            </span>
                            <span className="rounded-full border border-[#f7bf45]/24 bg-[#f7bf45]/12 px-2.5 py-1 text-[11px] font-medium text-[#f7d472]">
                              {t("planner.rackOccupancySummaryCompact", "In use {count}", {
                                count: String(rack.occupiedCount),
                              })}
                            </span>
                            {selectedRackKey === rack.key ? (
                              <>
                                <span className="rounded-full border border-white/10 bg-[#0d1922] px-2.5 py-1 text-[11px] font-medium text-[#d5e1e8]">
                                  {t("planner.rackSummaryCompact", "{levels} levels · {slots} slots", {
                                    levels: String(rack.levelCount),
                                    slots: String(rack.slotCount),
                                  })}
                                </span>
                                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${rack.agvCount === rack.locationCount ? "border-[#8db6ff]/24 bg-[#8db6ff]/12 text-[#cfe0ff]" : "border-white/10 bg-[#0d1922] text-[#d5e1e8]"}`}>
                                  {rack.agvCount === rack.locationCount
                                    ? t("planner.rackAgvCompact", "AGV")
                                    : t("planner.rackManualCompact", "Manual")}
                                </span>
                                <span className="rounded-full border border-[#8db6ff]/24 bg-[#8db6ff]/12 px-2.5 py-1 text-[11px] font-medium text-[#cfe0ff]">
                                  {t("planner.rackSelectedCompact", "Editing")}
                                </span>
                              </>
                            ) : null}
                          </div>
                        </button>
                      ))
                    ) : (
                      <div className="col-span-full flex items-center justify-center rounded-[1rem] border border-dashed border-white/10 px-4 py-8 text-sm text-[#9cb0bc]">
                        {selectedZoneLayoutMode === "area"
                          ? t("planner.rowEmpty", "This zone does not have row-shaped locations yet. Use New row to start the first one.")
                          : t("planner.rackEmpty", "This zone does not have rack-shaped locations yet. Use New rack to start the first one.")}
                      </div>
                    )
                  ) : (
                    <div className="col-span-full flex items-center justify-center rounded-[1rem] border border-dashed border-white/10 px-4 py-8 text-sm text-[#9cb0bc]">
                      {selectedZoneLayoutMode === "area"
                        ? t("planner.selectZoneForRows", "Select a zone first, then the area view will show the real rows inside that zone.")
                        : t("planner.selectZoneForRacks", "Select a zone first, then the rack view will show the real racks inside that zone.")}
                    </div>
                  )}
                </div>
              </div>

              {selectedRack || isCreatingRack ? (
                <div ref={rackEditorRef} className="mt-4 rounded-[1.2rem] border border-white/8 bg-[#0f1d27] p-3.5">
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#bfd2dc]">
                        {isCreatingRack
                          ? selectedZoneLayoutMode === "area"
                            ? t("planner.addRow", "Add a row")
                            : t("planner.addRack", "Add a rack")
                          : selectedZoneLayoutMode === "area"
                            ? t("planner.rowEditorEyebrow", "Row editor")
                            : t("planner.rackEditorEyebrow", "Rack editor")}
                      </p>
                      <p className="mt-1.5 text-base font-semibold text-white">
                        {isCreatingRack
                          ? selectedZoneLayoutMode === "area"
                            ? t("planner.addRowTitle", "Create a full row skeleton")
                            : t("planner.addRackTitle", "Create a full rack skeleton")
                          : selectedZoneLayoutMode === "area"
                            ? t("planner.rowEditorTitle", "Edit the selected row")
                            : t("planner.rackEditorTitle", "Edit the selected rack")}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {isCreatingRack ? (
                        <>
                          <PlannerActionButton
                            type="button"
                            tone="accent"
                            size="sm"
                            disabled={!rackCreateReady || createRack.isPending}
                            onClick={() => createRack.mutate()}
                          >
                            <ArrowRight size={14} />
                            {createRack.isPending
                              ? selectedZoneLayoutMode === "area"
                                ? t("planner.creatingRow", "Creating row...")
                                : t("planner.creatingRack", "Creating rack...")
                              : selectedZoneLayoutMode === "area"
                                ? t("planner.createRow", "Create row")
                                : t("planner.createRack", "Create rack")}
                          </PlannerActionButton>
                          <PlannerActionButton
                            type="button"
                            tone="dark-outline"
                            size="sm"
                            onClick={() => {
                              setSelectedRackKey(null);
                              setIsCreatingRack(false);
                            }}
                          >
                            {t("common.cancel", "Cancel")}
                          </PlannerActionButton>
                        </>
                      ) : selectedRack ? (
                        <>
                          <PlannerActionButton
                            type="button"
                            tone="accent"
                            size="sm"
                            disabled={!rackForm.aisle || !rackForm.rack || !rackEditorDirty || updateRack.isPending}
                            onClick={() => updateRack.mutate()}
                          >
                            <ArrowRight size={14} />
                            {updateRack.isPending
                              ? selectedZoneLayoutMode === "area"
                                ? t("planner.savingRow", "Saving row...")
                                : t("planner.savingRack", "Saving rack...")
                              : selectedZoneLayoutMode === "area"
                                ? t("planner.saveRow", "Save row")
                                : t("planner.saveRack", "Save rack")}
                          </PlannerActionButton>
                          <PlannerActionButton
                            type="button"
                            tone="danger"
                            size="sm"
                            disabled={deleteRack.isPending}
                            onClick={() => deleteRack.mutate()}
                          >
                            {deleteRack.isPending
                              ? selectedZoneLayoutMode === "area"
                                ? t("planner.deletingRow", "Deleting row...")
                                : t("planner.deletingRack", "Deleting rack...")
                              : selectedZoneLayoutMode === "area"
                                ? t("planner.deleteRow", "Delete row")
                                : t("planner.deleteRack", "Delete rack")}
                          </PlannerActionButton>
                        </>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-white/10 bg-[#13212c] px-3 py-1.5 text-[11px] font-medium text-white">
                      {`${layoutTerms.secondary} ${rackForm.rack || "--"}`}
                    </span>
                    <span className="rounded-full border border-white/10 bg-[#13212c] px-3 py-1.5 text-[11px] font-medium text-[#d5e1e8]">
                      {`${layoutTerms.primary} ${rackForm.aisle || "--"}`}
                    </span>
                    <span className="rounded-full border border-white/10 bg-[#13212c] px-3 py-1.5 text-[11px] font-medium text-[#d5e1e8]">
                      {t("planner.rackSummaryCompact", "{levels} levels · {slots} slots · {count} locations", {
                        levels: String(isCreatingRack ? rackForm.levels : selectedRack?.levelCount || rackForm.levels),
                        slots: String(isCreatingRack ? rackForm.slotsPerLevel : selectedRack?.slotCount || rackForm.slotsPerLevel),
                        count: String(
                          isCreatingRack ? rackForm.levels * rackForm.slotsPerLevel : selectedRack?.locationCount || 0,
                        ),
                      })}
                    </span>
                    <span className="rounded-full border border-white/10 bg-[#13212c] px-3 py-1.5 text-[11px] font-medium text-[#d5e1e8]">
                      {`${t("planner.beamCapacity", "Beam capacity")} ${Math.round(rackForm.max_weight_kg)} ${weightUnitLabel(unitSystem)}`}
                    </span>
                  </div>
                    <>
                      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                        <FieldDark label={layoutTerms.primary}>
                          <input
                            type="text"
                            value={rackForm.aisle}
                            onChange={(e) => setRackForm({ ...rackForm, aisle: e.target.value })}
                            className="w-full rounded-2xl border border-white/10 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                          />
                        </FieldDark>
                        <FieldDark label={layoutTerms.secondary}>
                          <input
                            type="text"
                            value={rackForm.rack}
                            onChange={(e) => setRackForm({ ...rackForm, rack: e.target.value })}
                            className="w-full rounded-2xl border border-white/10 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                          />
                        </FieldDark>
                        <FieldDark label={t("planner.levelCount", "Levels")}>
                          <input
                            type="number"
                            min={1}
                            value={rackForm.levels}
                            onChange={(e) => setRackForm({ ...rackForm, levels: Number(e.target.value) || 1 })}
                            className="w-full rounded-2xl border border-white/10 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                          />
                        </FieldDark>
                        <FieldDark label={t("planner.slotCount", "Slots")}>
                          <input
                            type="number"
                            min={1}
                            value={rackForm.slotsPerLevel}
                            onChange={(e) => setRackForm({ ...rackForm, slotsPerLevel: Number(e.target.value) || 1 })}
                            className="w-full rounded-2xl border border-white/10 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                          />
                        </FieldDark>
                      </div>
                      <div className="mt-5 rounded-[1rem] border border-white/10 bg-[#13212c] p-4">
                        <div className="mb-3">
                          <p className="text-[11px] uppercase tracking-[0.18em] text-[#d7e4ea]">
                            {selectedZoneLayoutMode === "area"
                              ? t("planner.rowProperties", "Row properties")
                              : t("planner.rackProperties", "Rack properties")}
                          </p>
                          <p className="mt-1 text-sm text-[#d5e1e8]">
                            {selectedZoneLayoutMode === "area"
                              ? t("planner.rowPropertiesHint", "After the row code and skeleton are right, adjust storage type, beam load, and AGV access here.")
                              : t("planner.rackPropertiesHint", "After the rack code and skeleton are right, adjust storage type, beam load, and AGV access here.")}
                          </p>
                        </div>
                        <div className="grid gap-4 md:grid-cols-3">
                          <FieldDark label={t("common.type", "Type")}>
                            <span className="relative inline-flex w-full">
                              <select
                                value={rackForm.location_type}
                                onChange={(e) => setRackForm({ ...rackForm, location_type: e.target.value })}
                                className="w-full appearance-none rounded-2xl border border-white/10 bg-[#20303b] px-4 py-3 pr-10 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                              >
                                {Object.keys(locationTypeLabels).map((value) => (
                                  <option key={value} value={value} className="text-[#13212c]">
                                    {describeLocationType(value)}
                                  </option>
                                ))}
                              </select>
                              <ChevronDown
                                size={16}
                                className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[#cdd9e1]"
                              />
                            </span>
                          </FieldDark>
                          <FieldDark label={t("planner.beamCapacity", "Beam capacity")}>
                            <input
                              type="number"
                              min={0}
                              value={rackForm.max_weight_kg}
                              onChange={(e) => setRackForm({ ...rackForm, max_weight_kg: Number(e.target.value) || 0 })}
                              className="w-full rounded-2xl border border-white/10 bg-[#20303b] px-4 py-3 text-sm text-white outline-none transition focus:border-[#f7bf45]/45 focus:ring-4 focus:ring-[#f7bf45]/10"
                            />
                          </FieldDark>
                          <label className="flex items-start gap-3 rounded-[1.2rem] border border-white/10 bg-[#0f1d27] px-4 py-4 text-sm leading-6 text-[#d5e1e8]">
                            <input
                              type="checkbox"
                              checked={rackForm.is_agv_accessible}
                              onChange={(e) => setRackForm({ ...rackForm, is_agv_accessible: e.target.checked })}
                              className="mt-1 h-4 w-4 accent-[#8db6ff]"
                            />
                            <span>
                              {selectedZoneLayoutMode === "area"
                                ? t("planner.rowAgv", "Apply AGV accessibility to every location in this row.")
                                : t("planner.rackAgv", "Apply AGV accessibility to every location on this rack.")}
                            </span>
                          </label>
                        </div>
                      </div>
                    </>
                </div>
              ) : null}
            </div>
          </div>
        </section>

        <section className="rounded-[1.75rem] border border-[#13212c]/10 bg-white/85 p-5 shadow-[0_24px_60px_rgba(19,33,44,0.08)] backdrop-blur lg:p-6">
          <div className="mb-5 inline-flex items-center rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#61717d]">
            {t("planner.workflowStepTwoSection", "Step 02")} · {t("planner.workflowStepTwoTitle", "Split the floor into zones")}
          </div>
          <div ref={zoneEditorRef} className="flex items-center gap-3">
            <div className="rounded-2xl border border-[#8db6ff]/28 bg-[#8db6ff]/12 p-2.5 text-[#7da9ff]">
              <Plus size={18} />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">
                {selectedZone ? t("planner.editZone", "Edit zone") : t("planner.addZone", "Add a zone")}
              </p>
              <h2 className="mt-1 text-lg font-semibold text-[#13212c]">
                {selectedZone
                  ? t("planner.editZoneTitle", "Update the selected warehouse section")
                  : t("planner.addZoneTitle", "Create visual warehouse sections")}
              </h2>
            </div>
          </div>

          <div className="mt-4 space-y-4">
            {selectedZone ? (
              <div className="rounded-[1.15rem] border border-[#8db6ff]/24 bg-[#eff4ff] px-4 py-3 text-sm leading-6 text-[#415464]">
                <p className="text-[10px] uppercase tracking-[0.18em] text-[#6c84a2]">
                  {t("planner.selectedZoneEyebrow", "Editing now")}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="text-base font-semibold text-[#13212c]">{selectedZone.name}</span>
                  <span className="rounded-full border border-[#8db6ff]/24 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#40618e]">
                    {selectedZone.code}
                  </span>
                  <span className="rounded-full border border-[#13212c]/8 bg-white px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-[#61717d]">
                    {t("planner.selectedZoneSummary", "{count} mapped locations · sequence {sequence}", {
                      count: selectedZone.location_count,
                      sequence: selectedZone.sequence,
                    })}
                  </span>
                </div>
              </div>
            ) : null}
              <div className="rounded-[1.05rem] border border-[#13212c]/10 bg-[#fbf8f2] px-3.5 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[#5f6f7b]">{t("planner.quickTemplates", "Quick templates")}</p>
              </div>
              <div className="mt-3 grid gap-3">
                {zoneTemplates.map((template) => (
                  <button
                    key={template.code}
                    type="button"
                    onClick={() =>
                      setZoneForm({
                        name: t(template.nameKey, template.code),
                        code: template.code,
                        is_agv_zone: template.is_agv_zone,
                        sequence: template.sequence,
                        layout_mode: zoneForm.layout_mode,
                      })
                    }
                    className="rounded-[1.15rem] border border-[#13212c]/10 bg-white px-4 py-3 text-left transition hover:bg-[#fffdfa]"
                  >
                    <p className="text-sm font-semibold text-[#13212c]">{t(template.nameKey, template.code)}</p>
                    <p className="mt-1 text-sm leading-6 text-[#4f606c]">{t(template.detailKey, template.detailKey)}</p>
                  </button>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-3">
                {selectedZone ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedZoneId(null);
                      setSelectedLocationId(null);
                      setZoneForm({ name: "", code: "", is_agv_zone: false, sequence: 10, layout_mode: "rack" });
                      setLocationForm({
                        barcode: "",
                        aisle: "",
                        rack: "",
                        level: "",
                        position: "",
                        location_type: "storage",
                        current_status: "available",
                        is_agv_accessible: false,
                      });
                      setSuccess("");
                      setError("");
                    }}
                    className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-xs font-medium uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                  >
                    {t("planner.createAnotherZone", "Create another zone")}
                  </button>
                ) : null}
                <p className="text-sm leading-6 text-[#61717d]">
                  {selectedZone
                    ? t("planner.zoneSelectedHint", "You are editing the selected zone from the map.")
                    : t("planner.zoneCreateHint", "Pick a template or start a new zone here.")}
                </p>
              </div>
            </div>
            {selectedZone ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-medium text-[#13212c]">
                    {zoneForm.name || selectedZone.name}
                  </span>
                  <span className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-medium text-[#61717d]">
                    {groupModeLabel}
                  </span>
                </div>
                <>
                    <Field label={t("planner.zoneName", "Zone name")}>
                      <input
                        type="text"
                        value={zoneForm.name}
                        onChange={(e) => setZoneForm({ ...zoneForm, name: e.target.value })}
                        placeholder={t("planner.zoneNamePlaceholder", "Cold chain reserve")}
                        className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                      />
                    </Field>
                    <div className="grid gap-4 md:grid-cols-2">
                      <Field label={t("planner.zoneCode", "Zone code")}>
                        <input
                          type="text"
                          value={zoneForm.code}
                          onChange={(e) => setZoneForm({ ...zoneForm, code: e.target.value.toUpperCase() })}
                          placeholder={t("planner.zoneCodePlaceholder", "COLD")}
                          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                        />
                      </Field>
                      <Field label={t("planner.displaySequence", "Display sequence")}>
                        <div className="space-y-3">
                          <input
                            type="number"
                            value={zoneForm.sequence}
                            onChange={(e) => setZoneForm({ ...zoneForm, sequence: Number(e.target.value) })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                          {selectedZone ? (
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                disabled={!previousZone || moveZone.isPending}
                                onClick={() => moveZone.mutate("earlier")}
                                className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-xs font-medium uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                              >
                                <ArrowUp size={14} />
                                {t("planner.moveEarlier", "Move earlier")}
                              </button>
                              <button
                                type="button"
                                disabled={!nextZone || moveZone.isPending}
                                onClick={() => moveZone.mutate("later")}
                                className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-xs font-medium uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa]"
                              >
                                <ArrowDown size={14} />
                                {t("planner.moveLater", "Move later")}
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </Field>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(["rack", "area"] as LayoutMode[]).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => setZoneForm({ ...zoneForm, layout_mode: mode })}
                          className={`rounded-full border px-3 py-2 text-xs font-medium uppercase tracking-[0.14em] transition ${
                            zoneForm.layout_mode === mode
                              ? "border-[#13212c]/20 bg-[#13212c] text-[#f4efe8]"
                              : "border-[#13212c]/10 bg-white text-[#13212c] hover:bg-[#fffdfa]"
                          }`}
                        >
                          {mode === "area"
                            ? t("planner.layoutModeArea", "Area-first")
                            : t("planner.layoutModeRack", "Rack-first")}
                        </button>
                      ))}
                    </div>
                    <p className="text-sm leading-6 text-[#61717d]">
                      {zoneForm.layout_mode === "area"
                        ? t("planner.layoutModeAreaHint", "Use this when the zone is mostly floor or bulk storage and operators think in sections and rows, not physical racks.")
                        : t("planner.layoutModeRackHint", "Use this when operators really navigate by aisle and rack on the floor.")}
                    </p>
                    <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
                      <input
                        type="checkbox"
                        checked={zoneForm.is_agv_zone}
                        onChange={(e) => setZoneForm({ ...zoneForm, is_agv_zone: e.target.checked })}
                        className="mt-1 h-4 w-4 accent-[#13212c]"
                      />
                      <span>{t("planner.markAgvZone", "Mark this as an AGV-ready zone if robots should be allowed to route into it later.")}</span>
                    </label>
                  </>
                <PlannerActionButton
                  type="button"
                  tone="primary"
                  fullWidth
                  disabled={
                    !activeWarehouseId ||
                    !zoneForm.name ||
                    !zoneForm.code ||
                    (selectedZone ? !zoneEditorDirty || updateZone.isPending : addZone.isPending)
                  }
                  onClick={() => (selectedZone ? updateZone.mutate() : addZone.mutate())}
                >
                  {selectedZone
                    ? updateZone.isPending
                      ? t("planner.savingZone", "Saving zone...")
                      : t("planner.saveZoneAction", "Save zone changes")
                    : addZone.isPending
                      ? t("planner.addingZone", "Adding zone...")
                      : t("planner.addZoneAction", "Add zone to plan")}
                  <ArrowRight size={15} />
                </PlannerActionButton>
                {selectedZone ? (
                  <PlannerActionButton
                    type="button"
                    tone="danger"
                    fullWidth
                    disabled={deleteZone.isPending || selectedZone.location_count > 0}
                    onClick={() => {
                      if (window.confirm(t("planner.deleteZoneConfirm", "Delete this zone from the planner?"))) {
                        deleteZone.mutate();
                      }
                    }}
                  >
                    {deleteZone.isPending ? t("planner.deletingZone", "Deleting zone...") : t("planner.deleteZone", "Delete zone")}
                  </PlannerActionButton>
                ) : null}
                {selectedZone?.location_count ? (
                  <p className="text-sm leading-6 text-[#61717d]">
                    {t("planner.zoneDeleteBlocked", "This zone already has mapped locations, so delete is blocked until those locations are moved or removed.")}
                  </p>
                ) : null}
              </>
            ) : null}

            {selectedZone ? (
              <div className={`rounded-[1.2rem] border bg-[#f7f4ee] p-3.5 transition ${slotHeatActive ? "border-[#93a4b4]/24 ring-1 ring-[#93a4b4]/16" : "border-[#13212c]/10"}`}>
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                      {t("planner.locationEditorEyebrow", "Zone locations")}
                    </p>
                    <p className="mt-1 text-base font-semibold text-[#13212c]">
                      {selectedZoneLayoutMode === "area"
                        ? t("planner.locationEditorTitleArea", "Maintain the section and row locations that belong to this zone")
                        : t("planner.locationEditorTitle", "Maintain the locations that belong to this zone")}
                    </p>
                  </div>
                  <span className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-[#61717d]">
                    {selectedZoneLayoutMode === "area"
                      ? t("planner.locationEditorCompactArea", "Section / row locations")
                      : t("planner.locationEditorCompact", "Aisle / rack locations")}
                  </span>
                </div>

                {isCreatingRack || isCreatingAisle ? (
                  <div className="mt-4 rounded-[1rem] border border-dashed border-[#13212c]/12 bg-white px-4 py-4 text-sm leading-6 text-[#61717d]">
                    {isCreatingAisle
                      ? selectedZoneLayoutMode === "area"
                        ? t("planner.finishSectionBeforeLocations", "Create this section first; the location maintenance below will switch to the new section.")
                        : t("planner.finishAisleBeforeLocations", "Create this aisle first; the location maintenance below will switch to the new aisle.")
                      : selectedZoneLayoutMode === "area"
                        ? t("planner.finishRowBeforeLocations", "Build this row's skeleton first; the location maintenance below will switch to the new row.")
                        : t("planner.finishRackBeforeLocations", "Build this rack's skeleton first; the location maintenance below will switch to the new rack.")}
                  </div>
                ) : (
                  <>
                    <div className="mt-3">
                      <Field label={t("planner.locationQuickFilter", "Quick filter")}>
                        <input
                          type="text"
                          value={locationQuickFilter}
                          onChange={(e) => setLocationQuickFilter(e.target.value)}
                          placeholder={selectedZoneLayoutMode === "area"
                            ? t("planner.locationQuickFilterAreaPlaceholder", "Search barcode, section, row, level, slot, or status")
                            : t("planner.locationQuickFilterPlaceholder", "Search barcode, aisle, rack, level, slot, or status")}
                          className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                        />
                      </Field>
                    </div>

                    <div className="mt-3 grid gap-2.5">
                      {locations.length === 0 ? (
                        <div className="rounded-[1rem] border border-dashed border-[#13212c]/10 bg-white px-4 py-4 text-sm leading-6 text-[#61717d]">
                          {t("planner.locationEmpty", "This zone does not have any mapped locations yet. Add the first one below.")}
                        </div>
                      ) : filteredLocations.length === 0 ? (
                        <div className="rounded-[1rem] border border-dashed border-[#13212c]/10 bg-white px-4 py-4 text-sm leading-6 text-[#61717d]">
                          {t("planner.locationFilterEmpty", "No locations match the current filter.")}
                        </div>
                      ) : (
                        filteredLocations.map((location: LocationRow) => (
                          <button
                            key={location.id}
                            type="button"
                            onClick={() => {
                              setSelectedLocationId(location.id);
                              setSuccess("");
                              setError("");
                            }}
                            className={`rounded-[0.95rem] border px-3 py-2.5 text-left transition ${
                              selectedLocationId === location.id
                                ? "border-[#93a4b4]/45 bg-[#eef2f5] shadow-[0_14px_30px_rgba(147,164,180,0.18)] ring-2 ring-[#93a4b4]/18"
                                : "border-[#13212c]/10 bg-white hover:bg-[#fffdfa]"
                            }`}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <p className="text-sm font-semibold text-[#13212c]">{location.barcode}</p>
                                  {selectedLocationId === location.id ? (
                                    <span className="rounded-full border border-[#93a4b4]/24 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#50616f]">
                                      {t("planner.locationSelected", "Editing")}
                                    </span>
                                  ) : null}
                                </div>
                                <div className="mt-1.5 flex flex-wrap gap-2">
                                  <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-medium text-[#61717d]">
                                    {formatLocationSummary(location)}
                                  </span>
                                  <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-[#61717d]">
                                    {describeLocationStatus(location.current_status)}
                                  </span>
                                  {selectedLocationId === location.id ? (
                                    <>
                                      <span className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-[#61717d]">
                                        {describeLocationType(location.location_type)}
                                      </span>
                                      {location.is_agv_accessible ? (
                                        <span className="rounded-full border border-[#8db6ff]/24 bg-[#8db6ff]/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-[#506c93]">
                                          {t("planner.locationAgvCompact", "AGV")}
                                        </span>
                                      ) : null}
                                    </>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          </button>
                        ))
                      )}
                    </div>

                    <div ref={locationEditorRef} className={`mt-3 rounded-[1rem] border bg-white p-3.5 transition ${selectedLocation ? "border-[#93a4b4]/24 ring-1 ring-[#93a4b4]/14" : "border-[#13212c]/10"}`}>
                  <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                        {selectedLocation ? t("planner.editLocation", "Edit location") : t("planner.addLocation", "Add location")}
                      </p>
                      <p className="mt-1 text-base font-semibold text-[#13212c]">
                        {selectedLocation
                          ? t("planner.editLocationTitle", "Update the selected location")
                          : t("planner.addLocationTitle", "Create a new location inside this zone")}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {selectedLocation ? (
                        <>
                          <PlannerActionButton
                            type="button"
                            tone="secondary"
                            size="sm"
                            onClick={() => {
                              setSelectedLocationId(null);
                              setLocationForm({
                                barcode: "",
                                aisle: "",
                                rack: "",
                                level: "",
                                position: "",
                                location_type: "storage",
                                current_status: "available",
                                is_agv_accessible: false,
                              });
                            }}
                          >
                            {t("planner.createAnotherLocation", "Create another location")}
                          </PlannerActionButton>
                          <PlannerActionButton
                            type="button"
                            tone="primary"
                            size="sm"
                            disabled={!locationEditorDirty || updateLocation.isPending}
                            onClick={() => updateLocation.mutate()}
                          >
                            {updateLocation.isPending
                              ? t("planner.savingLocation", "Saving location...")
                              : t("planner.saveLocation", "Save location")}
                          </PlannerActionButton>
                          <PlannerActionButton
                            type="button"
                            tone="danger"
                            size="sm"
                            disabled={deleteLocation.isPending}
                            onClick={() => {
                              if (window.confirm(t("planner.deleteLocationConfirm", "Delete this location from the zone?"))) {
                                deleteLocation.mutate();
                              }
                            }}
                          >
                            {deleteLocation.isPending
                              ? t("planner.deletingLocation", "Deleting location...")
                              : t("planner.deleteLocation", "Delete location")}
                          </PlannerActionButton>
                        </>
                      ) : (
                        <>
                          <PlannerActionButton
                            type="button"
                            tone="primary"
                            size="sm"
                            disabled={
                              !selectedZoneId ||
                              !locationForm.barcode ||
                              !locationForm.aisle ||
                              !locationForm.rack ||
                              !locationForm.level ||
                              !locationForm.position ||
                              createLocation.isPending
                            }
                            onClick={() => createLocation.mutate()}
                          >
                            {createLocation.isPending
                              ? t("planner.addingLocation", "Adding location...")
                              : t("planner.addLocationAction", "Add location")}
                            <ArrowRight size={15} />
                          </PlannerActionButton>
                          <PlannerActionButton
                            type="button"
                            tone="secondary"
                            size="sm"
                            onClick={() => {
                              setSelectedLocationId(null);
                              setLocationForm({
                                barcode: "",
                                aisle: "",
                                rack: "",
                                level: "",
                                position: "",
                                location_type: "storage",
                                current_status: "available",
                                is_agv_accessible: false,
                              });
                              setSuccess("");
                              setError("");
                            }}
                          >
                            <Plus size={14} />
                            {t("planner.newLocationButton", "New location")}
                          </PlannerActionButton>
                        </>
                      )}
                    </div>
                  </div>
                  <>
                    <div className="mt-4">
                        <Field label={t("planner.locationBarcode", "Location barcode")}>
                          <input
                            type="text"
                            value={locationForm.barcode}
                            onChange={(e) => setLocationForm({ ...locationForm, barcode: e.target.value })}
                            placeholder="A-01-01-01-01"
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                    </div>

                    <div className="mt-4 grid gap-4 md:grid-cols-4">
                        <Field label={layoutTerms.primary}>
                          <input
                            type="text"
                            value={locationForm.aisle}
                            onChange={(e) => setLocationForm({ ...locationForm, aisle: e.target.value })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                        <Field label={layoutTerms.secondary}>
                          <input
                            type="text"
                            value={locationForm.rack}
                            onChange={(e) => setLocationForm({ ...locationForm, rack: e.target.value })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                        <Field label={t("planner.locationLevel", "Level")}>
                          <input
                            type="text"
                            value={locationForm.level}
                            onChange={(e) => setLocationForm({ ...locationForm, level: e.target.value })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                        <Field label={t("planner.locationPosition", "Slot")}>
                          <input
                            type="text"
                            value={locationForm.position}
                            onChange={(e) => setLocationForm({ ...locationForm, position: e.target.value })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          />
                        </Field>
                    </div>

                    <div className="mt-5 rounded-[1rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                            {t("planner.locationProperties", "Location properties")}
                          </p>
                          <p className="mt-1 text-sm text-[#61717d]">
                            {t("planner.locationPropertiesHint", "Adjust status, storage type, and AGV access after the position is right.")}
                          </p>
                        </div>
                      </div>
                      <div className="grid gap-4 md:grid-cols-3">
                        <Field label={t("common.status", "Status")}>
                          <select
                            value={locationForm.current_status}
                            onChange={(e) => setLocationForm({ ...locationForm, current_status: e.target.value })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          >
                            {["available", "occupied", "reserved", "blocked"].map((option) => (
                              <option key={option} value={option}>
                                {describeLocationStatus(option)}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <Field label={t("planner.locationType", "Location type")}>
                          <select
                            value={locationForm.location_type}
                            onChange={(e) => setLocationForm({ ...locationForm, location_type: e.target.value })}
                            className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                          >
                            {["storage", "staging", "dock", "quality", "packing", "charging"].map((option) => (
                              <option key={option} value={option}>
                                {describeLocationType(option)}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
                          <input
                            type="checkbox"
                            checked={locationForm.is_agv_accessible}
                            onChange={(e) => setLocationForm({ ...locationForm, is_agv_accessible: e.target.checked })}
                            className="mt-1 h-4 w-4 accent-[#13212c]"
                          />
                          <span>{t("planner.locationAgv", "Mark this location as AGV-accessible.")}</span>
                        </label>
                      </div>
                    </div>
                  </>
                    </div>
                  </>
                )}
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <section className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.08fr)_360px]">
      <div className="min-w-0 overflow-hidden rounded-[1.9rem] border border-[#13212c]/10 bg-white/85 p-4 shadow-[0_20px_52px_rgba(19,33,44,0.06)] sm:p-6">
        <div className="mb-5 inline-flex items-center rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#61717d]">
          {t("planner.workflowStepThreeSection", "Step 03")} · {t("planner.workflowStepThreeTitle", "Save placement rules")}
        </div>
        <div className="flex min-w-0 items-center gap-3">
          <div className="rounded-2xl border border-[#f7bf45]/28 bg-[#f7bf45]/12 p-2.5 text-[#d19009]">
            <PackageCheck size={18} />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("planner.rulesGuide", "Placement rules guide")}</p>
            <h2 className="mt-1 break-words text-lg font-semibold text-[#13212c]">{t("planner.rulesGuideTitle", "Help customers standardize where products should live")}</h2>
          </div>
        </div>

        <div className="mt-4 grid min-w-0 gap-3.5 lg:grid-cols-2 xl:grid-cols-4">
          {placementRules.map(({ icon: Icon, titleKey, detailKey }) => (
            <div key={titleKey} className="rounded-[1.35rem] border border-[#13212c]/10 bg-[#f7f4ee] p-4">
              <div className="inline-flex rounded-2xl border border-[#13212c]/10 bg-white p-2.5 text-[#13212c]">
                <Icon size={18} />
              </div>
              <p className="mt-4 text-base font-semibold text-[#13212c]">{t(titleKey, titleKey)}</p>
              <p className="mt-2 text-sm leading-6 text-[#61717d]">{t(detailKey, detailKey)}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 grid min-w-0 gap-3.5 lg:grid-cols-2">
          <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <input type="checkbox" checked={rules.heavy_items_low} onChange={(e) => setRules({ ...rules, heavy_items_low: e.target.checked })} className="mt-1 h-4 w-4 accent-[#13212c]" />
            <span>{t("planner.prefHeavyLow", "Prefer lower levels for heavy items")}</span>
          </label>
          <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <input type="checkbox" checked={rules.fast_movers_front} onChange={(e) => setRules({ ...rules, fast_movers_front: e.target.checked })} className="mt-1 h-4 w-4 accent-[#13212c]" />
            <span>{t("planner.prefFastFront", "Keep fast movers near the front of the flow")}</span>
          </label>
          <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <input type="checkbox" checked={rules.slow_movers_deep} onChange={(e) => setRules({ ...rules, slow_movers_deep: e.target.checked })} className="mt-1 h-4 w-4 accent-[#13212c]" />
            <span>{t("planner.prefSlowDeep", "Push slow movers deeper into storage")}</span>
          </label>
          <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <input type="checkbox" checked={rules.separate_hazmat} onChange={(e) => setRules({ ...rules, separate_hazmat: e.target.checked })} className="mt-1 h-4 w-4 accent-[#13212c]" />
            <span>{t("planner.prefHazmat", "Require separate hazmat zones")}</span>
          </label>
          <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <input type="checkbox" checked={rules.separate_cold_chain} onChange={(e) => setRules({ ...rules, separate_cold_chain: e.target.checked })} className="mt-1 h-4 w-4 accent-[#13212c]" />
            <span>{t("planner.prefColdChain", "Require separate cold-chain zones")}</span>
          </label>
          <label className="flex items-start gap-3 rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <input
              type="checkbox"
              checked={rules.allow_same_sku_consolidation}
              onChange={(e) => setRules({ ...rules, allow_same_sku_consolidation: e.target.checked })}
              className="mt-1 h-4 w-4 accent-[#13212c]"
            />
            <span>{t("planner.prefSameSkuMerge", "Allow same-SKU stock to consolidate in one slot")}</span>
          </label>
          <label className="block rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <span className="mb-1.5 block text-sm font-medium text-[#334351]">{t("planner.differentSkuPolicy", "Different SKU in the same slot")}</span>
            <select
              value={rules.different_sku_slot_policy}
              onChange={(e) => setRules({ ...rules, different_sku_slot_policy: e.target.value })}
              className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
            >
              <option value="block">{t("planner.slotPolicyBlock", "Block")}</option>
              <option value="warn">{t("planner.slotPolicyWarn", "Warn only")}</option>
              <option value="allow">{t("planner.slotPolicyAllow", "Allow")}</option>
            </select>
          </label>
          <label className="block rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <span className="mb-1.5 block text-sm font-medium text-[#334351]">{t("planner.lotExpiryPolicy", "Same SKU with different lot / expiry")}</span>
            <select
              value={rules.lot_expiry_mismatch_policy}
              onChange={(e) => setRules({ ...rules, lot_expiry_mismatch_policy: e.target.value })}
              className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
            >
              <option value="warn">{t("planner.slotPolicyWarn", "Warn only")}</option>
              <option value="block">{t("planner.slotPolicyBlock", "Block")}</option>
              <option value="allow">{t("planner.slotPolicyAllow", "Allow")}</option>
            </select>
          </label>
          <label className="block rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-4 text-sm leading-6 text-[#61717d]">
            <span className="mb-1.5 block text-sm font-medium text-[#334351]">{`${t("planner.heavyThreshold", "Heavy item threshold")} (${weightUnitLabel(unitSystem)})`}</span>
            <input
              type="number"
              min={1}
              value={toDisplayWeight(rules.heavy_item_threshold_kg, unitSystem)}
              onChange={(e) => setRules({ ...rules, heavy_item_threshold_kg: fromDisplayWeight(Number(e.target.value), unitSystem) })}
              className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
            />
          </label>
        </div>

        <div className="mt-5 rounded-[1.5rem] border border-[#13212c]/10 bg-[#f7f4ee] p-5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{t("planner.agvEnvelope", "AGV physical envelope")}</p>
          <div className="mt-3.5 rounded-[1.2rem] border border-[#13212c]/10 bg-white px-3.5 py-3.5">
            <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1 basis-56">
                <p className="text-sm font-semibold text-[#13212c]">{t("planner.readinessPanelTitle", "Readiness panel")}</p>
                <p className="mt-1 text-sm leading-6 text-[#61717d]">
                  {t(
                    "planner.readinessPanelBody",
                    "Keep this panel in view while customers define the floor. It turns physical assumptions into an explicit go / not-yet signal before AGV work starts.",
                  )}
                </p>
              </div>
              <div className="inline-flex max-w-full flex-wrap rounded-full border border-[#13212c]/10 bg-white p-1">
                {(["metric", "imperial"] as UnitSystem[]).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setUnitSystem(option)}
                    className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                      unitSystem === option
                        ? "bg-[#13212c] text-[#f4efe8]"
                        : "text-[#61717d] hover:text-[#13212c]"
                    }`}
                  >
                    {option === "metric"
                      ? t("common.metricSystem", "Metric (EU)")
                      : t("common.imperialSystem", "Imperial (US)")}
                  </button>
                ))}
              </div>
              <div className={`max-w-full break-words rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${agvReadyScore === agvChecks.length ? "bg-[#87c6a120] text-[#356b4c]" : "bg-[#f7bf4520] text-[#8a6208]"}`}>
                {t("planner.readinessScore", "{score}/{total} checks in range", {
                  score: agvReadyScore,
                  total: agvChecks.length,
                })}
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {agvChecks.map((check) => (
                <ConstraintCard
                  key={check.label}
                  label={check.label}
                  value={check.value}
                  target={check.target}
                  detail={check.detail}
                  ok={check.ok}
                />
              ))}
            </div>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-[#334351]">{`${t("planner.rackHeight", "Rack height")} (${lengthUnitLabel(unitSystem)})`}</span>
              <input
                type="number"
                step="0.1"
                min={1}
                value={toDisplayLength(rules.rack_height_m, unitSystem)}
                onChange={(e) => setRules({ ...rules, rack_height_m: fromDisplayLength(Number(e.target.value), unitSystem) })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-[#334351]">{`${t("planner.beamCapacity", "Beam capacity")} (${weightUnitLabel(unitSystem)})`}</span>
              <input
                type="number"
                step="50"
                min={50}
                value={toDisplayWeight(rules.beam_capacity_kg, unitSystem)}
                onChange={(e) => setRules({ ...rules, beam_capacity_kg: fromDisplayWeight(Number(e.target.value), unitSystem) })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-[#334351]">{`${t("planner.aisleWidth", "Aisle width")} (${lengthUnitLabel(unitSystem)})`}</span>
              <input
                type="number"
                step="0.1"
                min={1}
                value={toDisplayLength(rules.aisle_width_m, unitSystem)}
                onChange={(e) => setRules({ ...rules, aisle_width_m: fromDisplayLength(Number(e.target.value), unitSystem) })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-[#334351]">{`${t("planner.turningRadius", "AGV turning radius")} (${lengthUnitLabel(unitSystem)})`}</span>
              <input
                type="number"
                step="0.1"
                min={0.5}
                value={toDisplayLength(rules.agv_turning_radius_m, unitSystem)}
                onChange={(e) => setRules({ ...rules, agv_turning_radius_m: fromDisplayLength(Number(e.target.value), unitSystem) })}
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              />
            </label>
          </div>
          <p className="mt-4 text-sm leading-6 text-[#61717d]">
            {t(
              "planner.agvEnvelopeBody",
              "These dimensions matter for AGV feasibility. Narrow aisles, low turning clearance, and weak rack beams should block a premature \"ready\" signal.",
            )}
          </p>
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          <PlannerActionButton
            type="button"
            tone="primary"
            disabled={!activeWarehouseId || saveRules.isPending}
            onClick={() => saveRules.mutate()}
          >
            {saveRules.isPending ? t("planner.savingRules", "Saving rules...") : t("planner.saveRules", "Save placement rules")}
            <ArrowRight size={15} />
          </PlannerActionButton>
        </div>

        <div className="mt-4 rounded-[1.2rem] border border-[#13212c]/8 bg-[#eff4ff] px-4 py-3.5 text-sm leading-7 text-[#4d5d6a]">
          {t(
            "planner.rulesFootnote",
            "These rules are now warehouse-specific and are used by putaway suggestion logic. This is still not a full CAD tool, but it gives the customer a visual planning surface and makes the system recommend locations more consistently.",
          )}
        </div>

        <div className="mt-5 rounded-[1.5rem] border border-[#13212c]/10 bg-[#f7f4ee] p-5">
          <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">
                {t("planner.wcsMappingEyebrow", "WCS point mapping")}
              </p>
              <h3 className="mt-1 text-lg font-semibold text-[#13212c]">
                {t("planner.wcsMappingTitle", "Turn warehouse locations into AGV executable points")}
              </h3>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[#61717d]">
                {t(
                  "planner.wcsMappingBody",
                  "After a drawing creates zones and locations, check that storage locations, buffers, aisle groups, AGV stations, and virtual dock door points each have a clear WCS point code.",
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.planner.wcsPointMappings(activeWarehouseId) })}
              className="inline-flex items-center justify-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-4 py-2.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#13212c] transition hover:bg-[#fffdfa] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!activeWarehouseId || isFetchingWcsMappings}
            >
              <RefreshCw size={14} className={isFetchingWcsMappings ? "animate-spin" : ""} />
              {t("common.refresh", "Refresh")}
            </button>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="rounded-[1.15rem] border border-[#13212c]/8 bg-white px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7e8d98]">
                {t("planner.blueprintMetadata", "Blueprint metadata")}
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#9a6f11]">
                    {t("planner.blueprintZoneSize", "Area size")}
                  </p>
                  <p className="mt-1 break-words text-sm font-semibold text-[#13212c]">
                    {blueprintSummary.zoneDimensions || t("planner.blueprintUnknown", "Not provided")}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#9a6f11]">
                    {t("planner.blueprintLocationSize", "Location size")}
                  </p>
                  <p className="mt-1 break-words text-sm font-semibold text-[#13212c]">
                    {blueprintSummary.locationDimensions || t("planner.blueprintUnknown", "Not provided")}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#9a6f11]">
                    {t("planner.blueprintSource", "Drawing source")}
                  </p>
                  <p className="mt-1 break-words text-sm font-semibold text-[#13212c]">
                    {blueprintSummary.drawingSource || t("planner.blueprintManualSource", "Manual planner")}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-xs leading-5 text-[#61717d]">
                {t(
                  "planner.blueprintMetadataDetail",
                  "{zones} zones and {locations} locations carry drawing metadata. Coordinate system: {coordinateSystem}.",
                  {
                    zones: String(blueprintSummary.blueprintZoneCount),
                    locations: String(blueprintSummary.blueprintLocationCount),
                    coordinateSystem: blueprintSummary.coordinateSystem || t("planner.blueprintCoordinateUnknown", "not provided"),
                  },
                )}
              </p>
            </div>

            <div className="rounded-[1.15rem] border border-[#13212c]/8 bg-[#fffdfa] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.16em] text-[#7e8d98]">
                {t("planner.wcsPointBoundary", "WCS point boundary")}
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                    {t("planner.wcsRealLocations", "Real locations")}
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-[#13212c]">{wcsWarehouseLocationPointCount}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                    {t("planner.wcsExternalPoints", "External points")}
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-[#13212c]">
                    {wcsPointMappings?.external_points ?? wcsExternalPointCount}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-[#61717d]">
                    {t("planner.wcsVirtualDockDoors", "Virtual dock doors")}
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-[#13212c]">{wcsVirtualDockDoorCount}</p>
                </div>
              </div>
              <p className="mt-3 text-xs leading-5 text-[#61717d]">
                {t(
                  "planner.wcsDockBoundaryDetail",
                  "Dock doors are not storage locations. They are virtual entry/exit point codes used by WCS routing for unload and ship movement.",
                )}
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <PlannerMetric
              label={t("planner.wcsMapped", "Mapped")}
              value={wcsPointMappings?.mapped_locations ?? 0}
              detail={t("planner.wcsMappedDetail", "Locations with a WCS point code.")}
            />
            <PlannerMetric
              label={t("planner.wcsMissing", "Missing")}
              value={wcsMissingCount}
              detail={t("planner.wcsMissingDetail", "Will receive generated point codes before saving.")}
            />
            <PlannerMetric
              label={t("planner.wcsIssues", "Issues")}
              value={wcsIssueCount}
              detail={t("planner.wcsIssuesDetail", "Blocking validation findings.")}
            />
            <PlannerMetric
              label={t("planner.wcsWarnings", "Warnings")}
              value={wcsWarningCount}
              detail={t("planner.wcsWarningsDetail", "Review before AGV dispatch.")}
            />
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-5">
            {["storage", "dock", "buffer", "agv_station", "external"].map((role) => (
              <div key={role} className="rounded-[1.15rem] border border-[#13212c]/8 bg-white px-4 py-3">
                <p className="text-[11px] uppercase tracking-[0.14em] text-[#7e8d98]">{wcsRoleLabel(role)}</p>
                <p className="mt-2 text-2xl font-semibold text-[#13212c]">{wcsRoleCounts[role] || 0}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 overflow-x-auto rounded-[1.2rem] border border-[#13212c]/10 bg-white">
            <div className="grid min-w-[920px] grid-cols-[minmax(170px,1.15fr)_150px_130px_minmax(170px,1fr)_minmax(120px,0.8fr)] gap-3 border-b border-[#13212c]/8 bg-[#eef3f5] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#61717d]">
              <span>{t("planner.wcsLocation", "WMS object")}</span>
              <span>{t("planner.wcsScope", "Scope")}</span>
              <span>{t("planner.wcsRole", "Role")}</span>
              <span>{t("planner.wcsPointCode", "Point code")}</span>
              <span>{t("planner.wcsAisleGroup", "Aisle group")}</span>
            </div>
            <div className="max-h-[360px] overflow-auto">
              {wcsMappingItems.length ? (
                wcsMappingItems.map((item, index) => {
                  const suggestion = suggestedWcsMappings[index];
                  const role = wcsRoleForItem(item);
                  const scopeLabel = wcsPointScopeLabel(item);
                  return (
                    <div
                      key={item.location_id || item.location_barcode || item.point_code || `wcs-point-${index}`}
                      className="grid min-w-[920px] grid-cols-[minmax(170px,1.15fr)_150px_130px_minmax(170px,1fr)_minmax(120px,0.8fr)] gap-3 border-b border-[#13212c]/6 px-4 py-3 text-sm text-[#334351] last:border-b-0"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-[#13212c]">
                          {item.location_barcode || item.point_name || item.point_code || t("planner.wcsExternalPoint", "External point")}
                        </p>
                        <p className="mt-1 text-xs text-[#7e8d98]">
                          {item.is_external_point
                            ? t("planner.wcsExternalPointDetail", "No WMS location row")
                            : `${t("planner.termAisle", "Aisle")} ${item.aisle || "—"} · ${t("planner.termRack", "Rack")} ${item.rack || "—"}`}
                        </p>
                      </div>
                      <span
                        className={`self-start rounded-full border px-2.5 py-1 text-xs font-medium ${
                          isVirtualDockDoor(item)
                            ? "border-[#f7bf45]/30 bg-[#f7bf45]/14 text-[#8a6208]"
                            : item.is_external_point
                              ? "border-[#8db6ff]/30 bg-[#8db6ff]/14 text-[#315f9d]"
                              : "border-[#13212c]/10 bg-[#f7f4ee] text-[#13212c]"
                        }`}
                      >
                        {scopeLabel}
                      </span>
                      <span className="self-start rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-2.5 py-1 text-xs font-medium text-[#13212c]">
                        {wcsRoleLabel(role)}
                      </span>
                      <span className={`min-w-0 truncate font-mono text-xs ${item.point_code ? "text-[#13212c]" : "text-[#8a6208]"}`}>
                        {suggestion?.point_code || "—"}
                      </span>
                      <span className="min-w-0 truncate font-mono text-xs text-[#61717d]">
                        {suggestion?.aisle_group || "—"}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="px-4 py-6 text-sm leading-6 text-[#61717d]">
                  {isFetchingWcsMappings
                    ? t("planner.wcsLoading", "Loading WCS point mappings...")
                    : t("planner.wcsEmpty", "No warehouse locations are available for WCS mapping yet.")}
                </div>
              )}
            </div>
            {wcsMappingItems.length ? (
              <div className="border-t border-[#13212c]/8 bg-[#fffdfa] px-4 py-2 text-xs font-medium text-[#61717d]">
                {t("planner.wcsShowingAll", "Showing all {count} WCS points. Save applies exactly these reviewed rows.", {
                  count: String(wcsMappingItems.length),
                })}
              </div>
            ) : null}
          </div>

          {wcsValidation?.issues?.length || wcsValidation?.warnings?.length ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {(wcsValidation.issues || []).slice(0, 4).map((issue) => (
                <div key={`wcs-issue-${issue.row}-${issue.code}`} className="rounded-[1rem] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  <p className="font-semibold">{issue.code}</p>
                  <p className="mt-1 leading-6">{issue.message}</p>
                </div>
              ))}
              {(wcsValidation.warnings || []).slice(0, 4).map((warning) => (
                <div key={`wcs-warning-${warning.row}-${warning.code}`} className="rounded-[1rem] border border-[#f7bf45]/40 bg-[#fff8e6] px-4 py-3 text-sm text-[#8a6208]">
                  <p className="font-semibold">{warning.code}</p>
                  <p className="mt-1 leading-6">{warning.message}</p>
                </div>
              ))}
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-3">
            <PlannerActionButton
              type="button"
              tone="secondary"
              disabled={!activeWarehouseId || !suggestedWcsMappings.length || validateWcsMappings.isPending}
              onClick={() => validateWcsMappings.mutate()}
            >
              {validateWcsMappings.isPending
                ? t("planner.wcsValidating", "Checking mappings...")
                : t("planner.wcsValidate", "Check mappings")}
            </PlannerActionButton>
            <PlannerActionButton
              type="button"
              tone="primary"
              disabled={!activeWarehouseId || !suggestedWcsMappings.length || saveWcsMappings.isPending || !wcsValidationIsCurrent}
              onClick={() => saveWcsMappings.mutate()}
            >
              {saveWcsMappings.isPending
                ? t("planner.wcsSaving", "Saving mappings...")
                : t("planner.wcsSave", "Save mappings")}
              <ArrowRight size={15} />
            </PlannerActionButton>
          </div>
          {!wcsValidationIsCurrent && suggestedWcsMappings.length ? (
            <p className="mt-2 text-xs leading-5 text-[#8a6208]">
              {t("planner.wcsSaveNeedsCurrentValidation", "Check mappings before saving. If the warehouse or point list changes, run the check again.")}
            </p>
          ) : null}
        </div>
      </div>
        <aside className="min-w-0 rounded-[1.9rem] border border-[#13212c]/10 bg-[#f7f4ee] p-4 shadow-[0_20px_52px_rgba(19,33,44,0.06)] sm:p-6">
          <div className="mb-4 inline-flex items-center rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#61717d]">
            {t("planner.workflowStepFourSection", "Step 04")} · {t("planner.workflowStepFourTitle", "Check readiness and hand off")}
          </div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7e8d98]">{t("planner.nextMoves", "Next moves")}</p>
          <div className="mt-4 space-y-3">
            <GuideChip
              title={t("planner.nextMoveOne", "Review AGV readiness")}
              detail={t("planner.nextMoveOneDetail", "{count} zones are AGV-ready right now.", { count: agvZoneCount })}
            />
            <GuideChip
              title={t("planner.nextMoveTwo", "Complete setup details")}
              detail={t("planner.nextMoveTwoDetail", "Finish warehouse, location, client, and billing setup before the first live inbound order.")}
            />
            <GuideChip
              title={t("planner.nextMoveThree", "Move into receiving")}
              detail={t("planner.nextMoveThreeDetail", "Once the floor map feels believable, start the first inbound flow and validate putaway suggestions.")}
            />
          </div>
          <div className="mt-5 flex flex-col gap-3">
            <Link
              to="/agv"
              className="inline-flex items-center justify-between rounded-full border border-[#13212c]/10 bg-white px-4 py-3 text-sm font-medium text-[#13212c] transition hover:bg-[#fffdfa]"
            >
              {t("planner.openAgv", "Open AGV readiness")}
              <ArrowRight size={15} />
            </Link>
            <Link
              to="/receiving"
              className="inline-flex items-center justify-between rounded-full bg-[#13212c] px-4 py-3 text-sm font-medium text-[#f4efe8] transition hover:bg-[#1d3040]"
            >
              {t("planner.openReceiving", "Go to receiving")}
              <ArrowRight size={15} />
            </Link>
          </div>
        </aside>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-[#334351]">{label}</span>
      {children}
    </label>
  );
}

function FieldDark({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-[#e6eef4]">{label}</span>
      {children}
    </label>
  );
}

function PlannerMetric({ label, value, detail }: { label: string; value: React.ReactNode; detail: string }) {
  return (
    <div className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/80 p-4 shadow-[0_18px_44px_rgba(19,33,44,0.05)]">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#13212c]">{value}</p>
      <p className="mt-2 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}

function WorkflowStepCard({ index, title, detail }: { index: string; title: string; detail: string }) {
  return (
    <div className="rounded-[1.3rem] border border-[#13212c]/10 bg-[#f7f4ee] p-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7e8d98]">{index}</p>
      <p className="mt-2 text-base font-semibold text-[#13212c]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}

function GuideChip({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-[1.25rem] border border-[#13212c]/8 bg-white px-4 py-3">
      <p className="text-sm font-semibold text-[#13212c]">{title}</p>
      <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}

function PlannerActionButton({
  children,
  tone = "secondary",
  size = "md",
  fullWidth = false,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: "primary" | "secondary" | "danger" | "accent" | "dark-outline";
  size?: "sm" | "md";
  fullWidth?: boolean;
}) {
  const toneClass = {
    primary: "bg-[#13212c] text-[#f4efe8] hover:bg-[#1d3040]",
    secondary: "border border-[#13212c]/10 bg-white text-[#13212c] hover:bg-[#fffdfa]",
    danger: "border border-red-200 bg-red-50 text-red-700 hover:bg-red-100",
    accent: "bg-[#f7bf45] text-[#13212c] hover:bg-[#f9c75f]",
    "dark-outline": "border border-white/10 bg-white/5 text-[#d5e1e8] hover:bg-white/10",
  } as const;
  const sizeClass = {
    sm: "px-4 py-2.5 text-xs",
    md: "px-5 py-3 text-sm",
  } as const;

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-full font-semibold uppercase tracking-[0.14em] transition disabled:cursor-not-allowed disabled:opacity-50 ${toneClass[tone]} ${sizeClass[size]} ${fullWidth ? "w-full" : ""} ${className}`.trim()}
    >
      {children}
    </button>
  );
}

function ConstraintCard({
  label,
  value,
  target,
  detail,
  ok,
}: {
  label: string;
  value: string;
  target: string;
  detail: string;
  ok: boolean;
}) {
  return (
    <div className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-[#13212c]">{label}</p>
          <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#7e8d98]">{target}</p>
        </div>
        <div className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${ok ? "bg-[#87c6a120] text-[#356b4c]" : "bg-[#f28a7d20] text-[#9b4d43]"}`}>
          {value}
        </div>
      </div>
      <p className="mt-3 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}

function PlannerLegendChip({ label, className }: { label: string; className: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] ${className}`}>
      {label}
    </span>
  );
}

function FocusChip({
  label,
  value,
  tone,
  active,
}: {
  label: string;
  value: string;
  tone: "amber" | "blue" | "green" | "slate";
  active?: boolean;
}) {
  const tones = {
    amber: "border-[#f7bf45]/24 bg-[#f7bf45]/12 text-[#f7d472]",
    blue: "border-[#8db6ff]/24 bg-[#8db6ff]/12 text-[#cfe0ff]",
    green: "border-[#87c6a1]/24 bg-[#87c6a1]/12 text-[#c7f3d6]",
    slate: "border-white/10 bg-white/8 text-[#d5e1e8]",
  } as const;
  return (
    <div className={`rounded-[0.9rem] border px-3 py-2 transition ${tones[tone]} ${active ? "ring-1 ring-white/18 shadow-[0_0_0_1px_rgba(255,255,255,0.04)]" : "opacity-85"}`}>
      <p className="text-[10px] uppercase tracking-[0.16em] opacity-75">{label}</p>
      <p className="mt-1 text-xs font-semibold">{value}</p>
    </div>
  );
}

function PlannerHeatStrip({ segments }: { segments: Array<{ label: string; units: number }> }) {
  const totalUnits = segments.reduce((sum, segment) => sum + segment.units, 0);
  if (!segments.length) {
    return <div className="mt-3 h-3 rounded-full bg-white/8" />;
  }

  return (
    <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-white/8">
      {segments.map((segment, index) => {
        const share = totalUnits > 0 ? Math.max(segment.units / totalUnits, 0.06) : 1 / segments.length;
        const tone =
          index % 4 === 0
            ? "#f0a63a"
            : index % 4 === 1
              ? "#5b87e5"
              : index % 4 === 2
                ? "#87c6a1"
                : "#d7dde3";
        return (
          <div
            key={`${segment.label}-${index}`}
            className="h-full"
            style={{ width: `${share * 100}%`, backgroundColor: tone }}
            title={`${segment.label}: ${segment.units}`}
          />
        );
      })}
    </div>
  );
}
