export type UnitSystem = "metric" | "imperial";

export type PlannerMetadata = Record<string, unknown>;

export type WarehouseRow = {
  id: string;
  name: string;
  code: string;
  timezone: string;
};

export type ZoneRow = {
  id: string;
  warehouse_id: string;
  name: string;
  code: string;
  is_agv_zone: boolean;
  sequence: number;
  layout_mode: "rack" | "area";
  location_count: number;
  dimensions?: PlannerMetadata | null;
  layout_metadata?: PlannerMetadata | null;
  drawing_source?: PlannerMetadata | null;
};

export type LocationRow = {
  id: string;
  barcode: string;
  aisle: string;
  rack: string;
  level: string;
  position: string;
  location_type: string;
  current_status: string;
  is_agv_accessible: boolean;
  max_weight_kg: number | null;
  coordinate_x: number | null;
  coordinate_y: number | null;
  coordinate_z: number | null;
  dimensions?: PlannerMetadata | null;
  layout_metadata?: PlannerMetadata | null;
  drawing_source?: PlannerMetadata | null;
  wcs_point_metadata?: PlannerMetadata | null;
};

export type InventoryRow = {
  id: string;
  warehouse_id: string;
  location_id: string;
  quantity_on_hand: number;
  quantity_available: number;
  quantity_allocated: number;
};

export type RackGroup = {
  key: string;
  aisle: string;
  rack: string;
  locationCount: number;
  levelCount: number;
  slotCount: number;
  occupiedCount: number;
  agvCount: number;
  maxWeightKg: number | null;
  locationType: string;
};

export type AisleGroup = {
  aisle: string;
  rackCount: number;
  locationCount: number;
  occupiedCount: number;
  agvCount: number;
  maxWeightKg: number | null;
  locationType: string;
};

export type ZoneBlueprintForm = {
  aisles: number;
  racksPerAisle: number;
  levelsPerRack: number;
  slotsPerLevel: number;
};

export type LayoutMode = "rack" | "area";

export type ZoneBlock = ZoneRow & { color: string };

export type InventoryLocationTotals = {
  onHand: number;
  available: number;
  allocated: number;
};

export type ZoneHeatmapItem = {
  label: string;
  name: string;
  units: number;
  occupiedCount: number;
  locationCount: number;
};

export type AisleHeatmapItem = {
  label: string;
  units: number;
  occupiedCount: number;
  locationCount: number;
};

export type RackHeatmapItem = {
  label: string;
  barcode: string;
  units: number;
};

const METERS_TO_FEET = 3.28084;
const KG_TO_LB = 2.20462;

export const toDisplayLength = (meters: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? meters * METERS_TO_FEET : meters;

export const fromDisplayLength = (value: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? value / METERS_TO_FEET : value;

export const toDisplayWeight = (kg: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? kg * KG_TO_LB : kg;

export const fromDisplayWeight = (value: number, unitSystem: UnitSystem) =>
  unitSystem === "imperial" ? value / KG_TO_LB : value;

export const lengthUnitLabel = (unitSystem: UnitSystem) => (unitSystem === "imperial" ? "ft" : "m");
export const weightUnitLabel = (unitSystem: UnitSystem) => (unitSystem === "imperial" ? "lb" : "kg");

const padCode = (value: number) => String(value).padStart(2, "0");

const isMetadata = (value: unknown): value is PlannerMetadata =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));

const metadataText = (metadata: PlannerMetadata | null | undefined, keys: string[]) => {
  if (!isMetadata(metadata)) return "";
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return "";
};

const metadataNumber = (metadata: PlannerMetadata | null | undefined, keys: string[]) => {
  if (!isMetadata(metadata)) return null;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return null;
};

const formatNumber = (value: number) =>
  Number.isInteger(value) ? String(value) : value.toFixed(value >= 10 ? 1 : 2).replace(/0+$/, "").replace(/\.$/, "");

export const formatBlueprintDimensions = (dimensions: PlannerMetadata | null | undefined) => {
  if (!isMetadata(dimensions)) return "";

  const standard = metadataText(dimensions, ["standard", "pallet", "label", "size", "name"]);
  if (standard) return standard;

  const widthM = metadataNumber(dimensions, ["width_m", "width"]);
  const depthM = metadataNumber(dimensions, ["depth_m", "length_m", "height_m", "depth", "length", "height"]);
  if (widthM && depthM) return `${formatNumber(widthM)} x ${formatNumber(depthM)} m`;

  const widthFt = metadataNumber(dimensions, ["width_ft"]);
  const depthFt = metadataNumber(dimensions, ["depth_ft", "length_ft", "height_ft"]);
  if (widthFt && depthFt) return `${formatNumber(widthFt)} x ${formatNumber(depthFt)} ft`;

  const anyDimension = metadataText(dimensions, ["width_ft", "depth_ft", "height_ft", "width_m", "depth_m", "height_m"]);
  return anyDimension;
};

export const blueprintMetadataSummary = (zones: ZoneRow[], locations: LocationRow[]) => {
  const zoneWithMetadata =
    zones.find((zone) => isMetadata(zone.dimensions) || isMetadata(zone.layout_metadata) || isMetadata(zone.drawing_source)) ||
    null;
  const locationWithMetadata =
    locations.find(
      (location) =>
        isMetadata(location.dimensions) ||
        isMetadata(location.layout_metadata) ||
        isMetadata(location.drawing_source) ||
        isMetadata(location.wcs_point_metadata),
    ) || null;

  const drawingSource =
    metadataText(zoneWithMetadata?.drawing_source, ["source_name", "file_name", "name", "title"]) ||
    metadataText(locationWithMetadata?.drawing_source, ["source_name", "file_name", "name", "title"]);
  const coordinateSystem =
    metadataText(zoneWithMetadata?.layout_metadata, ["coordinate_system"]) ||
    metadataText(locationWithMetadata?.layout_metadata, ["coordinate_system"]);

  return {
    zoneDimensions: formatBlueprintDimensions(zoneWithMetadata?.dimensions),
    locationDimensions: formatBlueprintDimensions(locationWithMetadata?.dimensions),
    drawingSource,
    coordinateSystem,
    blueprintZoneCount: zones.filter(
      (zone) => isMetadata(zone.dimensions) || isMetadata(zone.layout_metadata) || isMetadata(zone.drawing_source),
    ).length,
    blueprintLocationCount: locations.filter(
      (location) =>
        isMetadata(location.dimensions) ||
        isMetadata(location.layout_metadata) ||
        isMetadata(location.drawing_source) ||
        isMetadata(location.wcs_point_metadata),
    ).length,
  };
};

export const createZoneSkeleton = (
  zoneId: string,
  zoneCode: string,
  blueprint: ZoneBlueprintForm,
  isAgvAccessible: boolean,
  layoutMode: LayoutMode,
) => {
  const rows: Array<{
    zone_id: string;
    barcode: string;
    aisle: string;
    rack: string;
    level: string;
    position: string;
    location_type: string;
    is_agv_accessible: boolean;
  }> = [];

  for (let aisleIndex = 1; aisleIndex <= blueprint.aisles; aisleIndex += 1) {
    for (let rackIndex = 1; rackIndex <= blueprint.racksPerAisle; rackIndex += 1) {
      for (let levelIndex = 1; levelIndex <= blueprint.levelsPerRack; levelIndex += 1) {
        for (let slotIndex = 1; slotIndex <= blueprint.slotsPerLevel; slotIndex += 1) {
          const aisle = padCode(aisleIndex);
          const rack = padCode(rackIndex);
          const level = padCode(levelIndex);
          const position = padCode(slotIndex);
          rows.push({
            zone_id: zoneId,
            barcode:
              layoutMode === "area"
                ? `${zoneCode}-${aisle}-${rack}-${level}-${position}`
                : `${zoneCode}-${aisle}-${rack}-${level}-${position}`,
            aisle,
            rack,
            level,
            position,
            location_type: "storage",
            is_agv_accessible: isAgvAccessible,
          });
        }
      }
    }
  }

  return rows;
};

export const nextGroupedCode = (values: string[], fallback = "01") => {
  const parsed = values
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => Number.isFinite(value));
  return String((parsed.length ? Math.max(...parsed) : 0) + 1).padStart(2, "0") || fallback;
};

export const chunkItems = <T,>(items: T[], size: number) => {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
};

export const toList = <T,>(payload: unknown): T[] => {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object" && Array.isArray((payload as { items?: unknown }).items)) {
    return (payload as { items: T[] }).items;
  }
  return [];
};

export const locationTypeLabels: Record<string, string> = {
  storage: "Storage",
  staging: "Staging",
  dock: "Dock",
  quality: "Quality",
  packing: "Packing",
  charging: "Charging",
};

export const locationStatusLabels: Record<string, string> = {
  available: "Available",
  occupied: "Occupied",
  reserved: "Reserved",
  blocked: "Blocked",
};

export const zoneTemplates = [
  {
    nameKey: "planner.templateInboundName",
    code: "INBOUND",
    detailKey: "planner.templateInboundDetail",
    sequence: 10,
    is_agv_zone: false,
  },
  {
    nameKey: "planner.templateReserveName",
    code: "RESERVE",
    detailKey: "planner.templateReserveDetail",
    sequence: 20,
    is_agv_zone: true,
  },
  {
    nameKey: "planner.templatePackingName",
    code: "PACK",
    detailKey: "planner.templatePackingDetail",
    sequence: 30,
    is_agv_zone: false,
  },
  {
    nameKey: "planner.templateColdName",
    code: "COLD",
    detailKey: "planner.templateColdDetail",
    sequence: 40,
    is_agv_zone: false,
  },
];

export const timezoneOptions = [
  "Europe/Budapest",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Madrid",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
];

const zonePalette = ["#8db6ff", "#f7bf45", "#87c6a1", "#f28a7d", "#b7a6ff", "#7dd8d1"];

export const withZoneColors = (zones: ZoneRow[]): ZoneBlock[] =>
  zones.map((zone, index) => ({
    ...zone,
    color: zonePalette[index % zonePalette.length],
  }));

export const orderZones = <T extends Pick<ZoneRow, "code" | "sequence">>(zones: T[]): T[] =>
  [...zones].sort((a, b) => (a.sequence === b.sequence ? a.code.localeCompare(b.code) : a.sequence - b.sequence));

export const buildRackGroups = (locations: LocationRow[]): RackGroup[] => {
  const groupedLocations = locations.reduce((acc: Record<string, RackGroup>, location) => {
    const key = `${location.aisle}::${location.rack}`;
    if (!acc[key]) {
      acc[key] = {
        key,
        aisle: location.aisle,
        rack: location.rack,
        locationCount: 0,
        levelCount: 0,
        slotCount: 0,
        occupiedCount: 0,
        agvCount: 0,
        maxWeightKg: location.max_weight_kg ?? null,
        locationType: location.location_type,
      };
    }
    acc[key].locationCount += 1;
    if (location.current_status === "occupied") acc[key].occupiedCount += 1;
    if (location.is_agv_accessible) acc[key].agvCount += 1;
    return acc;
  }, {});

  return (Object.values(groupedLocations) as RackGroup[])
    .map((group) => {
      const rackLocations = locations.filter(
        (location) => location.aisle === group.aisle && location.rack === group.rack,
      );
      return {
        ...group,
        levelCount: new Set(rackLocations.map((location) => location.level)).size,
        slotCount: new Set(rackLocations.map((location) => `${location.level}:${location.position}`)).size,
        maxWeightKg: rackLocations[0]?.max_weight_kg ?? group.maxWeightKg,
        locationType: rackLocations[0]?.location_type ?? group.locationType,
      };
    })
    .sort((a, b) =>
      a.aisle === b.aisle
        ? a.rack.localeCompare(b.rack, undefined, { numeric: true })
        : a.aisle.localeCompare(b.aisle, undefined, { numeric: true }),
    );
};

export const buildAisleGroups = (locations: LocationRow[]): AisleGroup[] => {
  const groupedLocations = locations.reduce((acc: Record<string, AisleGroup>, location) => {
    if (!acc[location.aisle]) {
      acc[location.aisle] = {
        aisle: location.aisle,
        rackCount: 0,
        locationCount: 0,
        occupiedCount: 0,
        agvCount: 0,
        maxWeightKg: location.max_weight_kg ?? null,
        locationType: location.location_type,
      };
    }
    acc[location.aisle].locationCount += 1;
    if (location.current_status === "occupied") acc[location.aisle].occupiedCount += 1;
    if (location.is_agv_accessible) acc[location.aisle].agvCount += 1;
    return acc;
  }, {});

  return (Object.values(groupedLocations) as AisleGroup[])
    .map((group) => {
      const aisleLocations = locations.filter((location) => location.aisle === group.aisle);
      return {
        ...group,
        rackCount: new Set(aisleLocations.map((location) => location.rack)).size,
        maxWeightKg: aisleLocations[0]?.max_weight_kg ?? group.maxWeightKg,
        locationType: aisleLocations[0]?.location_type ?? group.locationType,
      };
    })
    .sort((a, b) => a.aisle.localeCompare(b.aisle, undefined, { numeric: true }));
};

export const buildInventoryByLocation = (inventoryItems: InventoryRow[]) => {
  const totals: globalThis.Map<string, InventoryLocationTotals> = new globalThis.Map();
  inventoryItems.forEach((item) => {
    const existing = totals.get(item.location_id) || { onHand: 0, available: 0, allocated: 0 };
    existing.onHand += Number(item.quantity_on_hand || 0);
    existing.available += Number(item.quantity_available || 0);
    existing.allocated += Number(item.quantity_allocated || 0);
    totals.set(item.location_id, existing);
  });
  return totals;
};

export const groupLocationsByZoneCode = (locations: LocationRow[]) => {
  const groups: globalThis.Map<string, LocationRow[]> = new globalThis.Map();
  locations.forEach((location) => {
    const zoneCode = String(location.barcode || "")
      .split("-")[0]
      ?.toUpperCase();
    if (!zoneCode) return;
    const existing = groups.get(zoneCode) || [];
    existing.push(location);
    groups.set(zoneCode, existing);
  });
  return groups;
};

export const buildZoneHeatmap = (
  orderedZones: ZoneBlock[],
  zoneLocationGroups: globalThis.Map<string, LocationRow[]>,
  inventoryByLocation: globalThis.Map<string, InventoryLocationTotals>,
): ZoneHeatmapItem[] =>
  orderedZones.map((zone) => {
    const zoneLocations = zoneLocationGroups.get(zone.code.toUpperCase()) || [];
    const totals = zoneLocations.reduce(
      (acc, location) => {
        const inventory = inventoryByLocation.get(location.id);
        acc.units += inventory?.onHand || 0;
        if ((inventory?.onHand || 0) > 0) acc.occupiedCount += 1;
        return acc;
      },
      { units: 0, occupiedCount: 0 },
    );
    return {
      label: zone.code,
      name: zone.name,
      units: totals.units,
      occupiedCount: totals.occupiedCount,
      locationCount: zoneLocations.length,
    };
  });

export const buildAisleHeatmap = (
  locations: LocationRow[],
  inventoryByLocation: globalThis.Map<string, InventoryLocationTotals>,
): AisleHeatmapItem[] => {
  const aisleMap: globalThis.Map<string, AisleHeatmapItem> = new globalThis.Map();
  locations.forEach((location) => {
    const existing = aisleMap.get(location.aisle) || {
      label: location.aisle,
      units: 0,
      occupiedCount: 0,
      locationCount: 0,
    };
    const inventory = inventoryByLocation.get(location.id);
    existing.units += inventory?.onHand || 0;
    if ((inventory?.onHand || 0) > 0) existing.occupiedCount += 1;
    existing.locationCount += 1;
    aisleMap.set(location.aisle, existing);
  });
  return Array.from(aisleMap.values()).sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
};

export const buildRackHeatmap = (
  locations: LocationRow[],
  selectedRack: Pick<RackGroup, "aisle" | "rack"> | null,
  inventoryByLocation: globalThis.Map<string, InventoryLocationTotals>,
): RackHeatmapItem[] => {
  if (!selectedRack) return [];
  return locations
    .filter((location) => location.aisle === selectedRack.aisle && location.rack === selectedRack.rack)
    .map((location) => {
      const inventory = inventoryByLocation.get(location.id);
      return {
        label: `${location.level}-${location.position}`,
        barcode: location.barcode,
        units: inventory?.onHand || 0,
      };
    })
    .sort((a, b) => a.barcode.localeCompare(b.barcode, undefined, { numeric: true }));
};

export const filterRackGroupsByAisle = (rackGroups: RackGroup[], focusedAisleKey: string | null) =>
  focusedAisleKey ? rackGroups.filter((rack) => rack.aisle === focusedAisleKey) : rackGroups;
