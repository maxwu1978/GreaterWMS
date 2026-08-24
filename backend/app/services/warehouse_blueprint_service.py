"""Pure domain helpers for warehouse blueprint generation and preview payload shaping.

Extracted from app/api/v1/endpoints/agent.py. These functions perform blueprint
normalization, zone/rack math, and payload shaping only — no database access,
no FastAPI Request/Depends.
"""

from decimal import Decimal

from app.models.warehouse import LocationStatus, LocationType

WAREHOUSE_BLUEPRINT_CREATE_TYPES = {
    "floor_storage",
    "rack_storage",
    "storage",
    "buffer",
    "agv_station",
}
WAREHOUSE_BLUEPRINT_ACCESS_TYPES = {"dock", "reference", "drive_aisle"}
AGV_PLANNING_STANDARD_DOC = "docs/36-agv-planning-standard.md"


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _blueprint_string(value, fallback: str, *, max_length: int = 80) -> str:
    text = str(value or fallback).strip()
    if not text:
        text = fallback
    return text[:max_length]


def _blueprint_int(value, fallback: int, *, minimum: int = 1, maximum: int = 500) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def _blueprint_float(value, fallback: float | None = None) -> float | None:
    if value is None or value == "":
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _blueprint_location_type(raw_type: str) -> str:
    zone_type = str(raw_type or "storage").strip().lower()
    if zone_type == "dock":
        return LocationType.DOCK.value
    if zone_type == "buffer":
        return LocationType.BUFFER.value
    if zone_type == "agv_station":
        return LocationType.AGV_STATION.value
    if zone_type == "drive_aisle":
        return LocationType.DRIVE_AISLE.value
    if zone_type == "reference":
        return LocationType.REFERENCE.value
    if zone_type == "quality":
        return LocationType.QUALITY.value
    if zone_type == "packing":
        return LocationType.PACKING.value
    if zone_type == "charging":
        return LocationType.CHARGING.value
    if zone_type == "staging":
        return LocationType.STAGING.value
    return LocationType.STORAGE.value


def _agent_planner_zone_modes_from_address(address: dict | None) -> dict[str, str]:
    raw = (address or {}).get("_planner_zone_modes", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(zone_id): "area" if str(mode).lower() == "area" else "rack"
        for zone_id, mode in raw.items()
    }


def _zone_blueprint_metadata(address: dict | None, zone_code: str) -> dict:
    layout = (address or {}).get("_blueprint_layout") or {}
    zones = layout.get("zones") if isinstance(layout, dict) else None
    if not isinstance(zones, list):
        return {}
    for zone in zones:
        if isinstance(zone, dict) and zone.get("code") == zone_code:
            return {
                "type": zone.get("type"),
                "is_access_point": zone.get("is_access_point", False),
                "dimensions": zone.get("dimensions") or {},
                "layout_percent": zone.get("layout_percent") or {},
                "metadata": zone.get("metadata") or {},
                "location_count": zone.get("location_count"),
            }
    return {}


def _location_blueprint_metadata(address: dict | None, barcode: str) -> dict:
    raw = (address or {}).get("_blueprint_location_metadata") or {}
    if not isinstance(raw, dict):
        return {}
    value = raw.get(barcode)
    return value if isinstance(value, dict) else {}


def _blueprint_merged_zone_fields(raw: dict) -> dict:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    dimensions = raw.get("dimensions") if isinstance(raw.get("dimensions"), dict) else {}
    layout_metadata = raw.get("layout_metadata") if isinstance(raw.get("layout_metadata"), dict) else {}
    merged = {**metadata, **dimensions, **layout_metadata, **raw}
    return merged


def _blueprint_dimensions(raw: dict) -> dict:
    raw = _blueprint_merged_zone_fields(raw)
    dimensions = {}
    for field in (
        "width_ft",
        "depth_ft",
        "height_ft",
        "length_ft",
        "area_sqft",
        "pallet_width_ft",
        "pallet_depth_ft",
        "pallet_width_in",
        "pallet_depth_in",
        "level_clear_height_in",
        "level_clear_height_ft",
        "bay_width_ft",
        "zone_width_ft",
        "zone_depth_ft",
        "slot_area_sqft",
    ):
        value = _blueprint_float(raw.get(field))
        if value is not None:
            dimensions[field] = value
    if "pallet_width_ft" not in dimensions and dimensions.get("pallet_width_in") is not None:
        dimensions["pallet_width_ft"] = round(float(dimensions["pallet_width_in"]) / 12, 3)
    if "pallet_depth_ft" not in dimensions and dimensions.get("pallet_depth_in") is not None:
        dimensions["pallet_depth_ft"] = round(float(dimensions["pallet_depth_in"]) / 12, 3)
    slot_count = _blueprint_int(raw.get("slot_count"), 0, minimum=0, maximum=100000)
    if slot_count:
        dimensions["slot_count"] = slot_count
    for int_field in ("bay_count", "level_count"):
        value = _blueprint_int(raw.get(int_field), 0, minimum=0, maximum=100000)
        if value:
            dimensions[int_field] = value
    slot_layout = raw.get("slot_layout")
    if isinstance(slot_layout, dict):
        normalized_slot_layout = {}
        for int_field in ("rows", "columns"):
            value = _blueprint_int(slot_layout.get(int_field), 0, minimum=0, maximum=10000)
            if value:
                normalized_slot_layout[int_field] = value
        for float_field in (
            "slot_width_ft",
            "slot_depth_ft",
            "offset_x_ft",
            "offset_y_ft",
            "occupied_width_ft",
            "occupied_depth_ft",
            "residual_width_ft",
            "residual_depth_ft",
            "total_slot_footprint_sqft",
        ):
            value = _blueprint_float(slot_layout.get(float_field))
            if value is not None:
                normalized_slot_layout[float_field] = value
        if normalized_slot_layout:
            dimensions["slot_layout"] = normalized_slot_layout
    capacity_adjustment = raw.get("capacity_adjustment")
    if isinstance(capacity_adjustment, dict):
        normalized_capacity = {}
        for key, value in capacity_adjustment.items():
            parsed = _blueprint_float(value)
            normalized_capacity[key] = parsed if parsed is not None else value
        if normalized_capacity:
            dimensions["capacity_adjustment"] = normalized_capacity
    cargo_size = raw.get("cargo_size_in")
    if isinstance(cargo_size, dict):
        normalized_cargo = {}
        for key in ("length", "width", "height"):
            value = _blueprint_float(cargo_size.get(key))
            if value is not None:
                normalized_cargo[key] = value
        if normalized_cargo:
            dimensions["cargo_size_in"] = normalized_cargo
    if raw.get("storage_unit") is not None:
        dimensions["storage_unit"] = str(raw.get("storage_unit"))
    if raw.get("planned_orientation") is not None:
        dimensions["planned_orientation"] = str(raw.get("planned_orientation"))
    if str(raw.get("pallet") or "").upper() == "GMA":
        dimensions.setdefault("pallet_width_ft", 4.0)
        dimensions.setdefault("pallet_depth_ft", 3.33)
    if "area_sqft" not in dimensions:
        width = dimensions.get("zone_width_ft") or dimensions.get("width_ft")
        depth = dimensions.get("zone_depth_ft") or dimensions.get("depth_ft")
        if width is not None and depth is not None:
            dimensions["area_sqft"] = round(width * depth, 2)
    return dimensions


def _normalize_blueprint_zone(raw: dict, index: int) -> dict:
    source = _blueprint_merged_zone_fields(raw)
    zone_type = str(raw.get("type") or raw.get("location_type") or "storage").strip().lower()
    code = _blueprint_string(source.get("code"), f"Z{index + 1}", max_length=20).upper()
    name = _blueprint_string(source.get("name"), code, max_length=100)
    aisles_source = source.get("aisles") if zone_type == "rack_storage" else source.get("rows", source.get("aisles"))
    levels_source = source.get("rows", source.get("levels")) if zone_type == "rack_storage" else source.get("levels")
    aisles = _blueprint_int(aisles_source, 1, maximum=100)
    racks = _blueprint_int(source.get("columns", source.get("racks")), 1, maximum=500)
    levels = _blueprint_int(levels_source, 4 if zone_type == "rack_storage" else 1, maximum=20)
    positions = _blueprint_int(source.get("positions"), 1, maximum=50)
    expected_pcs = source.get("expected_pcs")
    layout_percent = {
        "x": _blueprint_float(source.get("x"), _blueprint_float((source.get("layout_percent") or {}).get("x"), 0)) or 0,
        "y": _blueprint_float(source.get("y"), _blueprint_float((source.get("layout_percent") or {}).get("y"), 0)) or 0,
        "width": _blueprint_float(source.get("w"), _blueprint_float((source.get("layout_percent") or {}).get("width"), 10)) or 10,
        "height": _blueprint_float(source.get("h"), _blueprint_float((source.get("layout_percent") or {}).get("height"), 10)) or 10,
    }
    metadata = {
        key: source.get(key)
        for key in (
            "pallet",
            "width_ft",
            "depth_ft",
            "height_ft",
            "length_ft",
            "area_sqft",
            "storage_unit",
            "cargo_size_in",
            "planned_orientation",
            "slot_count",
            "slot_area_sqft",
            "slot_layout",
            "capacity_adjustment",
            "zone_width_ft",
            "zone_depth_ft",
            "doors",
            "exit",
            "expected_pcs",
            "notes",
            "rows",
            "columns",
            "storage_profile",
            "abc_class",
            "route_role",
            "lane_policy",
            "agv_internal_travel",
            "handoff_strategy",
            "handoff_edges",
            "direction",
            "inbound_end",
            "outbound_end",
            "docking_direction",
            "connector_zone_code",
            "left_side_enclosed",
            "replaces_original_a_storage_width_ft",
            "route_anchor_id",
            "route_exit_id",
            "station_role",
            "dock_doors_are_storage_locations",
        )
        if source.get(key) is not None
    }
    normalized = {
        "name": name,
        "code": code,
        "type": zone_type,
        "layout_mode": "rack" if zone_type == "rack_storage" else "area",
        "layout_percent": layout_percent,
        "aisles": aisles,
        "racks": racks,
        "levels": levels,
        "positions": positions,
        "location_type": _blueprint_location_type(zone_type),
        "metadata": metadata,
        "dimensions": _blueprint_dimensions(source),
        "sequence": _blueprint_int(source.get("sequence"), (index + 1) * 10, minimum=0, maximum=10000),
        "create_locations": zone_type in WAREHOUSE_BLUEPRINT_CREATE_TYPES,
        "is_access_point": zone_type in WAREHOUSE_BLUEPRINT_ACCESS_TYPES,
    }
    if expected_pcs is not None:
        normalized["expected_pcs"] = _blueprint_int(expected_pcs, 0, minimum=0, maximum=100000)
    return normalized


def _generate_blueprint_locations(zone: dict) -> list[dict]:
    if not zone.get("create_locations"):
        return []
    locations: list[dict] = []
    location_dimensions = _blueprint_location_dimensions(zone)
    pick_sequence = 0
    for aisle in range(1, zone["aisles"] + 1):
        for rack in range(1, zone["racks"] + 1):
            for level in range(1, zone["levels"] + 1):
                for position in range(1, zone["positions"] + 1):
                    pick_sequence += 1
                    aisle_code = f"{aisle:02d}"
                    rack_code = f"{rack:02d}"
                    level_code = f"{level:02d}" if zone["type"] == "rack_storage" else "01"
                    position_code = f"{position:02d}"
                    layout = _blueprint_location_layout(zone, aisle, rack, level, position)
                    locations.append(
                        {
                            "barcode": f"{zone['code']}-{aisle_code}-{rack_code}-{level_code}-{position_code}",
                            "aisle": aisle_code,
                            "rack": rack_code,
                            "level": level_code,
                            "position": position_code,
                            "location_type": zone["location_type"],
                            "current_status": LocationStatus.AVAILABLE.value,
                            "pick_sequence": pick_sequence,
                            "blueprint_type": zone["type"],
                            "dimensions": location_dimensions,
                            "layout_percent": layout["absolute"],
                            "slot_layout_percent": layout["relative"],
                        }
                    )
    return locations


def _blueprint_location_layout(
    zone: dict, aisle: int, rack: int, level: int, position: int
) -> dict:
    zone_layout = zone.get("layout_percent") or {}
    zone_x = float(zone_layout.get("x") or 0)
    zone_y = float(zone_layout.get("y") or 0)
    zone_width = max(0.1, float(zone_layout.get("width") or 10))
    zone_height = max(0.1, float(zone_layout.get("height") or 10))
    columns = max(1, int(zone["racks"]) * int(zone["positions"]))
    rows = max(
        1,
        int(zone["aisles"]) * int(zone["levels"])
        if zone["type"] == "rack_storage"
        else int(zone["aisles"]),
    )
    gap_x = min(0.8, max(0.18, zone_width / max(int(zone["racks"]), 1) * 0.12))
    gap_y = min(0.8, max(0.18, zone_height / max(int(zone["aisles"]), 1) * 0.12))
    column = (rack - 1) * int(zone["positions"]) + (position - 1)
    row = (aisle - 1) * int(zone["levels"]) + (level - 1) if zone["type"] == "rack_storage" else aisle - 1
    slot_layout = (zone.get("dimensions") or {}).get("slot_layout") or {}
    if zone["type"] == "floor_storage" and slot_layout:
        zone_width_ft = _blueprint_float(
            slot_layout.get("zone_width_ft"),
            _blueprint_float((zone.get("dimensions") or {}).get("zone_width_ft")),
        )
        zone_depth_ft = _blueprint_float(
            slot_layout.get("zone_depth_ft"),
            _blueprint_float((zone.get("dimensions") or {}).get("zone_depth_ft")),
        )
        slot_width_ft = _blueprint_float(
            slot_layout.get("slot_width_ft"),
            _blueprint_float((zone.get("dimensions") or {}).get("pallet_width_ft")),
        )
        slot_depth_ft = _blueprint_float(
            slot_layout.get("slot_depth_ft"),
            _blueprint_float((zone.get("dimensions") or {}).get("pallet_depth_ft")),
        )
        if zone_width_ft and zone_depth_ft and slot_width_ft and slot_depth_ft:
            offset_x = zone_width * (_blueprint_float(slot_layout.get("offset_x_ft"), 0) or 0) / zone_width_ft
            offset_y = zone_height * (_blueprint_float(slot_layout.get("offset_y_ft"), 0) or 0) / zone_depth_ft
            cell_width = max(0.1, zone_width * slot_width_ft / zone_width_ft)
            cell_height = max(0.1, zone_height * slot_depth_ft / zone_depth_ft)
            absolute = {
                "x": round(zone_x + offset_x + column * cell_width, 3),
                "y": round(zone_y + offset_y + row * cell_height, 3),
                "width": round(cell_width, 3),
                "height": round(cell_height, 3),
            }
            return {
                "absolute": absolute,
                "relative": {
                    "x": round(absolute["x"] - zone_x, 3),
                    "y": round(absolute["y"] - zone_y, 3),
                    "width": absolute["width"],
                    "height": absolute["height"],
                },
            }
    cell_width = max(0.1, (zone_width - gap_x * (columns + 1)) / columns)
    cell_height = max(0.1, (zone_height - gap_y * (rows + 1)) / rows)
    absolute = {
        "x": round(zone_x + gap_x + column * (cell_width + gap_x), 3),
        "y": round(zone_y + gap_y + row * (cell_height + gap_y), 3),
        "width": round(cell_width, 3),
        "height": round(cell_height, 3),
    }
    return {
        "absolute": absolute,
        "relative": {
            "x": round(absolute["x"] - zone_x, 3),
            "y": round(absolute["y"] - zone_y, 3),
            "width": absolute["width"],
            "height": absolute["height"],
        },
    }


def _blueprint_location_dimensions(zone: dict) -> dict:
    zone_dimensions = dict(zone.get("dimensions") or {})
    metadata = zone.get("metadata") or {}
    if str(metadata.get("pallet") or "").upper() == "GMA":
        return {
            "unit": "ft",
            "width_ft": zone_dimensions.get("pallet_width_ft", 4.0),
            "depth_ft": zone_dimensions.get("pallet_depth_ft", 3.33),
            "height_ft": zone_dimensions.get("height_ft"),
            "standard": "GMA pallet 48x40 in",
        }
    return {
        "unit": "ft",
        "width_ft": zone_dimensions.get("width_ft"),
        "depth_ft": zone_dimensions.get("depth_ft"),
        "height_ft": zone_dimensions.get("height_ft"),
        "length_ft": zone_dimensions.get("length_ft"),
    }


def _blueprint_point_token(value, fallback: str) -> str:
    text = str(value or fallback).strip().upper()
    cleaned = "".join(character if character.isalnum() else "-" for character in text)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or fallback


def _blueprint_wcs_role(zone_type: str, location_type: str | None = None) -> str:
    if zone_type == "dock":
        return "dock"
    if zone_type in {"buffer", "staging", "quality", "packing"} or location_type in {
        LocationType.BUFFER.value,
        LocationType.STAGING.value,
        LocationType.QUALITY.value,
        LocationType.PACKING.value,
    }:
        return "buffer"
    if zone_type in {"agv_station", "charging"} or location_type in {
        LocationType.AGV_STATION.value,
        LocationType.CHARGING.value,
    }:
        return "agv_station"
    if zone_type in {"drive_aisle", "reference"}:
        return "aisle_group"
    return "storage"


def _blueprint_wcs_prefix(role: str) -> str:
    return {
        "dock": "DOCK",
        "buffer": "BUF",
        "agv_station": "AGV",
        "aisle_group": "AISLE",
    }.get(role, "STO")


def _blueprint_wcs_point_mapping(
    warehouse_code: str,
    *,
    zone: dict,
    location: dict | None = None,
    code: str | None = None,
    layout_percent: dict | None = None,
    virtual: bool = False,
) -> dict:
    site = _blueprint_point_token(warehouse_code, "WMS")
    role = _blueprint_wcs_role(zone["type"], location.get("location_type") if location else None)
    barcode = _blueprint_point_token(
        code or (location or {}).get("barcode") or zone["code"],
        f"{site}-{_blueprint_wcs_prefix(role)}",
    )
    aisle = _blueprint_point_token((location or {}).get("aisle") or zone["code"], "00")
    zone_metadata = zone.get("metadata") or {}
    point_layout = layout_percent or (location or {}).get("layout_percent") or zone["layout_percent"]
    point_dimensions = (location or {}).get("dimensions") or zone.get("dimensions") or {}
    wcs_metadata = {
        "source": "blueprint_draft",
        "layout_percent": point_layout,
        "dimensions": point_dimensions,
        "zone_code": zone["code"],
        "zone_type": zone["type"],
        "route_role": zone_metadata.get("route_role"),
        "route_anchor_id": zone_metadata.get("route_anchor_id"),
        "route_exit_id": zone_metadata.get("route_exit_id"),
        "lane_policy": zone_metadata.get("lane_policy"),
        "agv_internal_travel": zone_metadata.get("agv_internal_travel"),
        "handoff_strategy": zone_metadata.get("handoff_strategy"),
        "handoff_edges": zone_metadata.get("handoff_edges"),
        "docking_direction": zone_metadata.get("docking_direction"),
        "planning_standard": AGV_PLANNING_STANDARD_DOC,
    }
    wcs_metadata = {key: value for key, value in wcs_metadata.items() if value is not None}
    if virtual:
        wcs_metadata["virtual"] = True
        wcs_metadata["external_point"] = True
    return {
        "location_id": None,
        "location_barcode": barcode,
        "point_code": f"{site}-{_blueprint_wcs_prefix(role)}-{barcode}",
        "point_type": role,
        "point_role": role,
        "point_name": f"{zone['name']} {barcode}",
        "buffer_code": f"{site}-BUF-{aisle}" if role == "buffer" else None,
        "aisle_group": f"{site}-AISLE-{aisle}",
        "agv_reachable": role != "aisle_group",
        "station_role": zone_metadata.get("station_role"),
        "virtual": virtual,
        "source": "blueprint_draft",
        "layout_percent": point_layout,
        "dimensions": point_dimensions,
        "wcs_metadata": wcs_metadata,
    }


def _blueprint_dock_doors(zone: dict, warehouse_code: str) -> list[dict]:
    if zone["type"] != "dock":
        return []
    raw_doors = str((zone.get("metadata") or {}).get("doors") or "").strip()
    door_codes: list[str] = []
    if "-" in raw_doors:
        start_text, end_text = raw_doors.split("-", 1)
        start = _blueprint_int(start_text, 1, minimum=1, maximum=999)
        end = _blueprint_int(end_text, start, minimum=start, maximum=999)
        door_codes = [str(value) for value in range(start, end + 1)]
    elif raw_doors:
        door_codes = [part.strip() for part in raw_doors.split(",") if part.strip()]
    if not door_codes:
        door_codes = [zone["code"]]

    zone_layout = zone.get("layout_percent") or {}
    height = float(zone_layout.get("height") or 10)
    door_height = height / max(len(door_codes), 1)
    doors = []
    for index, door_number in enumerate(door_codes):
        layout_percent = {
            "x": zone_layout.get("x", 0),
            "y": round(float(zone_layout.get("y") or 0) + door_height * index, 3),
            "width": zone_layout.get("width", 8),
            "height": round(door_height, 3),
        }
        code = f"DOCK-{door_number}"
        doors.append(
            {
                "code": code,
                "door_number": door_number,
                "type": "dock",
                "layout_percent": layout_percent,
                "agv_usage": "unload_and_ship",
                "wcs_mapping": _blueprint_wcs_point_mapping(
                    warehouse_code,
                    zone=zone,
                    code=code,
                    layout_percent=layout_percent,
                    virtual=True,
                ),
            }
        )
    return doors


def _blueprint_wcs_mapping_draft(zones: list[dict], warehouse_code: str) -> list[dict]:
    mappings: list[dict] = []
    for zone in zones:
        for location in zone.get("locations", []):
            mappings.append(_blueprint_wcs_point_mapping(warehouse_code, zone=zone, location=location))
        if zone.get("is_access_point"):
            mappings.extend(door["wcs_mapping"] for door in _blueprint_dock_doors(zone, warehouse_code))
    return mappings


def _blueprint_area_summaries(zones: list[dict]) -> dict:
    abc_floor_areas = [
        {
            "code": zone["code"],
            "name": zone["name"],
            "dimensions": zone.get("dimensions") or {},
            "layout_percent": zone["layout_percent"],
            "location_count": len(zone.get("locations", [])),
            "abc_class": (zone.get("metadata") or {}).get("abc_class") or zone["code"].split("-")[-1],
        }
        for zone in zones
        if zone["type"] == "floor_storage"
    ]
    rack_areas = [
        {
            "code": zone["code"],
            "name": zone["name"],
            "dimensions": zone.get("dimensions") or {},
            "layout_percent": zone["layout_percent"],
            "location_count": len(zone.get("locations", [])),
            "levels": zone.get("levels"),
            "racks": zone.get("racks"),
        }
        for zone in zones
        if zone["type"] == "rack_storage"
    ]
    return {"abc_floor_areas": abc_floor_areas, "rack_areas": rack_areas}


def _blueprint_validation(zones: list[dict]) -> list[dict]:
    checks: list[dict] = []
    for zone in zones:
        generated_count = len(zone["locations"])
        expected = zone.get("expected_pcs")
        if expected is not None:
            checks.append(
                {
                    "zone_code": zone["code"],
                    "check": "expected_location_count",
                    "ok": generated_count == expected,
                    "expected": expected,
                    "actual": generated_count,
                }
            )
        if str(zone.get("metadata", {}).get("pallet", "")).upper() == "GMA":
            dimensions = zone.get("dimensions") or {}
            width_ft = _blueprint_float(
                dimensions.get("pallet_width_ft"),
                _blueprint_float(zone.get("metadata", {}).get("width_ft")),
            )
            depth_ft = _blueprint_float(
                dimensions.get("pallet_depth_ft"),
                _blueprint_float(zone.get("metadata", {}).get("depth_ft")),
            )
            checks.append(
                {
                    "zone_code": zone["code"],
                    "check": "gma_pallet_size",
                    "ok": width_ft == 4 and depth_ft is not None and abs(depth_ft - 3.33) <= 0.02,
                    "expected": {"width_ft": 4, "depth_ft": 3.33},
                    "actual": {"width_ft": width_ft, "depth_ft": depth_ft},
                }
            )
    return checks


# ── Dallas AGV planning additions (ported from origin/main) ──


def _blueprint_list(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _blueprint_agv_planning(args: dict) -> dict:
    layout = args.get("layout") if isinstance(args.get("layout"), dict) else {}
    planning_standard = dict(args.get("planning_standard") or layout.get("planning_standard") or {})
    planning_standard.setdefault("document", AGV_PLANNING_STANDARD_DOC)
    route_policy = dict(args.get("route_policy") or layout.get("route_policy") or {})
    return {
        "planning_standard": planning_standard,
        "route_policy": route_policy,
        "route_nodes": _blueprint_list(args.get("route_nodes") or layout.get("route_nodes")),
        "agv_paths": _blueprint_list(args.get("agv_paths") or layout.get("agv_paths")),
        "stations": _blueprint_list(args.get("stations") or layout.get("stations")),
        "safety_zones": _blueprint_list(args.get("safety_zones") or layout.get("safety_zones")),
    }


def _blueprint_width_ft(value, *, fallback: float | None = None) -> float | None:
    if isinstance(value, dict):
        width_ft = _blueprint_float(value.get("width_ft"))
        if width_ft is not None:
            return width_ft
        width_m = _blueprint_float(value.get("width_m"))
        if width_m is not None:
            return round(width_m * 3.28084, 3)
    return fallback


def _blueprint_agv_planning_validation(agv_planning: dict, zones: list[dict]) -> list[dict]:
    route_policy = agv_planning.get("route_policy") or {}
    agv_paths = agv_planning.get("agv_paths") or []
    route_nodes = agv_planning.get("route_nodes") or []
    stations = agv_planning.get("stations") or []
    safety_zones = agv_planning.get("safety_zones") or []
    checks: list[dict] = []
    has_agv_layout = any(
        zone["type"] in {"floor_storage", "rack_storage", "dock", "drive_aisle", "reference"}
        for zone in zones
    )
    if not has_agv_layout:
        return checks

    main_width_ft = _blueprint_width_ft(
        {"width_ft": route_policy.get("main_aisle_width_ft"), "width_m": route_policy.get("main_aisle_width_m")}
    )
    branch_width_ft = _blueprint_width_ft(
        {"width_ft": route_policy.get("branch_aisle_width_ft"), "width_m": route_policy.get("branch_aisle_width_m")}
    )
    checks.extend(
        [
            {
                "check": "agv_planning_standard_document",
                "ok": (agv_planning.get("planning_standard") or {}).get("document")
                == AGV_PLANNING_STANDARD_DOC,
                "expected": AGV_PLANNING_STANDARD_DOC,
                "actual": (agv_planning.get("planning_standard") or {}).get("document"),
            },
            {
                "check": "agv_route_policy_present",
                "ok": bool(route_policy),
                "expected": "route_policy with traffic pattern and lane widths",
                "actual": sorted(route_policy.keys()) if route_policy else [],
            },
            {
                "check": "agv_main_aisle_width",
                "ok": main_width_ft is not None and main_width_ft >= 7.87,
                "expected": ">= 7.87 ft / 2400 mm for one-way rack-storage main aisle",
                "actual": main_width_ft,
            },
            {
                "check": "agv_branch_aisle_width",
                "ok": branch_width_ft is not None and branch_width_ft >= 8.2,
                "expected": ">= 8.2 ft / 2500 mm for pallet-jack or forklift AGV branch pickup aisle",
                "actual": branch_width_ft,
            },
            {
                "check": "agv_paths_present",
                "ok": bool(agv_paths),
                "expected": "at least one AGV-PATH route",
                "actual": len(agv_paths),
            },
            {
                "check": "agv_route_nodes_present",
                "ok": bool(route_nodes),
                "expected": "route nodes for path and station anchoring",
                "actual": len(route_nodes),
            },
            {
                "check": "agv_stations_have_anchor_and_direction",
                "ok": all(station.get("route_anchor_id") and station.get("docking_direction") for station in stations)
                and bool(stations),
                "expected": "station center points with route_anchor_id and docking_direction",
                "actual": len(stations),
            },
            {
                "check": "agv_safety_zones_present",
                "ok": bool(safety_zones),
                "expected": "slow or safety zones at dock, turns, crossings, or storage faces",
                "actual": len(safety_zones),
            },
            {
                "check": "dock_doors_not_storage",
                "ok": route_policy.get("dock_doors_are_storage_locations") is False,
                "expected": False,
                "actual": route_policy.get("dock_doors_are_storage_locations"),
            },
        ]
    )
    return checks


def _blueprint_station_wcs_mapping(warehouse_code: str, station: dict) -> dict:
    site = _blueprint_point_token(warehouse_code, "WMS")
    station_code = _blueprint_point_token(station.get("code"), "STATION")
    station_role = str(station.get("station_role") or "wait").lower()
    point_role = "agv_station" if station_role == "charging" else "buffer"
    prefix = _blueprint_wcs_prefix(point_role)
    layout_percent = {
        "x": _blueprint_float(station.get("x"), 0) or 0,
        "y": _blueprint_float(station.get("y"), 0) or 0,
        "width": _blueprint_float(station.get("width"), 1) or 1,
        "height": _blueprint_float(station.get("height"), 1) or 1,
    }
    return {
        "location_id": None,
        "location_barcode": station_code,
        "point_code": f"{site}-{prefix}-{station_code}",
        "point_type": point_role,
        "point_role": point_role,
        "point_name": station.get("name") or station_code,
        "buffer_code": f"{site}-BUF-{station_code}" if point_role == "buffer" else None,
        "aisle_group": station.get("aisle_group") or f"{site}-AISLE-{station_code}",
        "station_role": station_role,
        "agv_reachable": True,
        "virtual": True,
        "source": "blueprint_draft",
        "layout_percent": layout_percent,
        "dimensions": station.get("dimensions") or {},
        "wcs_metadata": {
            "source": "blueprint_draft",
            "virtual": True,
            "external_point": True,
            "station_role": station_role,
            "route_anchor_id": station.get("route_anchor_id"),
            "docking_direction": station.get("docking_direction"),
            "route_role": station_role,
            "layout_percent": layout_percent,
            "planning_standard": AGV_PLANNING_STANDARD_DOC,
        },
    }
