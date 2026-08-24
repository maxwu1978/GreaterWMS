"""Warehouse and Location management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.pagination import PaginationParams, paginate_window
from app.core.plan_limits import check_limit
from app.core.security import TokenPayload, UserRole
from app.models.inventory import Inventory
from app.models.warehouse import Location, LocationStatus, Warehouse, Zone

router = APIRouter()


class WarehouseCreate(BaseModel):
    name: str
    code: str
    timezone: str = "America/Chicago"
    address: dict | None = None


class WarehouseUpdate(BaseModel):
    name: str
    code: str
    timezone: str = "America/Chicago"
    address: dict | None = None


class WarehouseResponse(BaseModel):
    id: str
    name: str
    code: str
    timezone: str
    is_active: bool


class ZoneCreate(BaseModel):
    name: str
    code: str
    is_agv_zone: bool = False
    sequence: int = 0
    layout_mode: str = "rack"
    zone_type: str = "storage"
    coordinate_x: float | None = None
    coordinate_y: float | None = None
    coordinate_z: float | None = None
    dimensions: dict | None = None
    layout_metadata: dict | None = None
    drawing_source: dict | None = None


class ZoneUpdate(BaseModel):
    name: str
    code: str
    is_agv_zone: bool = False
    sequence: int = 0
    layout_mode: str = "rack"
    zone_type: str = "storage"
    coordinate_x: float | None = None
    coordinate_y: float | None = None
    coordinate_z: float | None = None
    dimensions: dict | None = None
    layout_metadata: dict | None = None
    drawing_source: dict | None = None


class ZoneResponse(BaseModel):
    id: str
    warehouse_id: str
    name: str
    code: str
    is_agv_zone: bool
    sequence: int
    layout_mode: str = "rack"
    location_count: int = 0
    zone_type: str = "storage"
    coordinate_x: float | None = None
    coordinate_y: float | None = None
    coordinate_z: float | None = None
    dimensions: dict | None = None
    layout_metadata: dict | None = None
    drawing_source: dict | None = None


class PlannerRulesResponse(BaseModel):
    heavy_items_low: bool = True
    heavy_item_threshold_kg: float = 20.0
    fast_movers_front: bool = True
    slow_movers_deep: bool = True
    separate_hazmat: bool = True
    separate_cold_chain: bool = True
    allow_same_sku_consolidation: bool = True
    different_sku_slot_policy: str = "block"
    lot_expiry_mismatch_policy: str = "warn"
    rack_height_m: float = 7.5
    beam_capacity_kg: float = 1200.0
    aisle_width_m: float = 3.2
    agv_turning_radius_m: float = 1.8


class PlannerRulesUpdate(BaseModel):
    heavy_items_low: bool = True
    heavy_item_threshold_kg: float = 20.0
    fast_movers_front: bool = True
    slow_movers_deep: bool = True
    separate_hazmat: bool = True
    separate_cold_chain: bool = True
    allow_same_sku_consolidation: bool = True
    different_sku_slot_policy: str = "block"
    lot_expiry_mismatch_policy: str = "warn"
    rack_height_m: float = 7.5
    beam_capacity_kg: float = 1200.0
    aisle_width_m: float = 3.2
    agv_turning_radius_m: float = 1.8


class LocationCreate(BaseModel):
    zone_id: str
    barcode: str
    aisle: str
    rack: str
    level: str
    position: str
    location_type: str = "storage"
    coordinate_x: float | None = None
    coordinate_y: float | None = None
    coordinate_z: float | None = None
    is_agv_accessible: bool = False
    max_weight_kg: float | None = None
    dimensions: dict | None = None
    layout_metadata: dict | None = None
    drawing_source: dict | None = None
    wcs_point_metadata: dict | None = None


class LocationUpdate(BaseModel):
    barcode: str
    aisle: str
    rack: str
    level: str
    position: str
    location_type: str = "storage"
    coordinate_x: float | None = None
    coordinate_y: float | None = None
    coordinate_z: float | None = None
    is_agv_accessible: bool = False
    current_status: str = LocationStatus.AVAILABLE.value
    max_weight_kg: float | None = None
    dimensions: dict | None = None
    layout_metadata: dict | None = None
    drawing_source: dict | None = None
    wcs_point_metadata: dict | None = None


class LocationResponse(BaseModel):
    id: str
    barcode: str
    aisle: str
    rack: str
    level: str
    position: str
    location_type: str
    current_status: str
    is_agv_accessible: bool
    max_weight_kg: float | None
    coordinate_x: float | None
    coordinate_y: float | None
    coordinate_z: float | None
    dimensions: dict | None = None
    layout_metadata: dict | None = None
    drawing_source: dict | None = None
    wcs_point_metadata: dict | None = None


class RackConfigureRequest(BaseModel):
    zone_id: str
    current_aisle: str
    current_rack: str
    aisle: str
    rack: str
    levels: int = 1
    slots_per_level: int = 1
    location_type: str = "storage"
    is_agv_accessible: bool = False
    max_weight_kg: float | None = None


class RackCreateRequest(BaseModel):
    zone_id: str
    aisle: str
    rack: str
    levels: int = 1
    slots_per_level: int = 1
    location_type: str = "storage"
    is_agv_accessible: bool = False
    max_weight_kg: float | None = None


class RackDeleteRequest(BaseModel):
    zone_id: str
    aisle: str
    rack: str


class RackConfigureResponse(BaseModel):
    zone_id: str
    aisle: str
    rack: str
    levels: int
    slots_per_level: int
    location_count: int
    location_type: str
    is_agv_accessible: bool
    max_weight_kg: float | None


class AisleConfigureRequest(BaseModel):
    zone_id: str
    current_aisle: str
    aisle: str
    location_type: str = "storage"
    is_agv_accessible: bool = False
    max_weight_kg: float | None = None


class AisleCreateRequest(BaseModel):
    zone_id: str
    aisle: str
    first_rack: str = "01"
    levels: int = 1
    slots_per_level: int = 1
    location_type: str = "storage"
    is_agv_accessible: bool = False
    max_weight_kg: float | None = None


class AisleDeleteRequest(BaseModel):
    zone_id: str
    aisle: str


class AisleConfigureResponse(BaseModel):
    zone_id: str
    aisle: str
    rack_count: int
    location_count: int
    location_type: str
    is_agv_accessible: bool
    max_weight_kg: float | None


@router.get("/{warehouse_id}/locations", response_model=list[LocationResponse])
async def list_locations(
    warehouse_id: str,
    location_type: str | None = Query(None),
    zone_id: str | None = Query(None),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    warehouse_result = await db.execute(
        select(Warehouse.id).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    if not warehouse_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found")

    query = (
        select(Location)
        .where(
            Location.warehouse_id == warehouse_id,
            Location.tenant_id == current_user.tenant_id,
        )
        .order_by(Location.location_type.asc(), Location.barcode.asc())
    )
    if location_type:
        requested_types = [item.strip() for item in location_type.split(",") if item.strip()]
        if requested_types:
            query = query.where(Location.location_type.in_(requested_types))
    if zone_id:
        query = query.where(Location.zone_id == zone_id)

    result = await db.execute(query)
    return [
        LocationResponse(
            id=location.id,
            barcode=location.barcode,
            aisle=location.aisle,
            rack=location.rack,
            level=location.level,
            position=location.position,
            location_type=location.location_type,
            current_status=location.current_status,
            is_agv_accessible=location.is_agv_accessible,
            max_weight_kg=float(location.max_weight_kg)
            if location.max_weight_kg is not None
            else None,
            coordinate_x=float(location.coordinate_x) if location.coordinate_x else None,
            coordinate_y=float(location.coordinate_y) if location.coordinate_y else None,
            coordinate_z=float(location.coordinate_z) if location.coordinate_z else None,
            dimensions=location.dimensions,
            layout_metadata=location.layout_metadata,
            drawing_source=location.drawing_source,
            wcs_point_metadata=location.wcs_point_metadata,
        )
        for location in result.scalars()
    ]


@router.get("/")
async def list_warehouses(
    page: PaginationParams = Depends(),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(Warehouse).where(
        Warehouse.is_active == True,  # noqa: E712
        Warehouse.tenant_id == current_user.tenant_id,
    )
    result = await paginate_window(db, query.order_by(Warehouse.name, Warehouse.code, Warehouse.id), page)
    result["items"] = [
        WarehouseResponse(
            id=w.id,
            name=w.name,
            code=w.code,
            timezone=w.timezone,
            is_active=w.is_active,
        )
        for w in result["items"]
    ]
    return result


@router.post("/", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    body: WarehouseCreate,
    _limits=Depends(check_limit("warehouses")),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    warehouse = Warehouse(
        tenant_id=current_user.tenant_id,
        name=body.name,
        code=body.code,
        timezone=body.timezone,
        address=body.address,
    )
    db.add(warehouse)
    await db.flush()
    return WarehouseResponse(
        id=warehouse.id,
        name=warehouse.name,
        code=warehouse.code,
        timezone=warehouse.timezone,
        is_active=warehouse.is_active,
    )


@router.put("/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse(
    warehouse_id: str,
    body: WarehouseUpdate,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    warehouse.name = body.name
    warehouse.code = body.code
    warehouse.timezone = body.timezone
    warehouse.address = _merge_address_preserving_reserved(warehouse.address, body.address)
    await db.flush()
    return WarehouseResponse(
        id=warehouse.id,
        name=warehouse.name,
        code=warehouse.code,
        timezone=warehouse.timezone,
        is_active=warehouse.is_active,
    )


def _merge_address_preserving_reserved(existing: dict | None, incoming: dict | None) -> dict | None:
    """Merge a user-supplied address over the stored one without touching system keys.

    Warehouse.address doubles as storage for underscore-prefixed system state
    (_planner_rules, _wcs, _planner_zone_modes). A plain overwrite from the
    warehouse-edit form silently wiped putaway rules and WCS credentials; user
    input must never read or write those keys.
    """
    reserved = {k: v for k, v in (existing or {}).items() if k.startswith("_")}
    merged = {k: v for k, v in (incoming or {}).items() if not k.startswith("_")}
    if not merged and not reserved and incoming is None:
        return None
    merged.update(reserved)
    return merged


def _planner_rules_from_address(address: dict | None) -> PlannerRulesResponse:
    raw = (address or {}).get("_planner_rules", {})
    different_sku_policy = str(raw.get("different_sku_slot_policy", "block")).lower()
    if different_sku_policy not in {"block", "warn", "allow"}:
        different_sku_policy = "block"
    lot_expiry_policy = str(raw.get("lot_expiry_mismatch_policy", "warn")).lower()
    if lot_expiry_policy not in {"block", "warn", "allow"}:
        lot_expiry_policy = "warn"
    return PlannerRulesResponse(
        heavy_items_low=raw.get("heavy_items_low", True),
        heavy_item_threshold_kg=float(raw.get("heavy_item_threshold_kg", 20.0)),
        fast_movers_front=raw.get("fast_movers_front", True),
        slow_movers_deep=raw.get("slow_movers_deep", True),
        separate_hazmat=raw.get("separate_hazmat", True),
        separate_cold_chain=raw.get("separate_cold_chain", True),
        allow_same_sku_consolidation=raw.get("allow_same_sku_consolidation", True),
        different_sku_slot_policy=different_sku_policy,
        lot_expiry_mismatch_policy=lot_expiry_policy,
        rack_height_m=float(raw.get("rack_height_m", 7.5)),
        beam_capacity_kg=float(raw.get("beam_capacity_kg", 1200.0)),
        aisle_width_m=float(raw.get("aisle_width_m", 3.2)),
        agv_turning_radius_m=float(raw.get("agv_turning_radius_m", 1.8)),
    )


def _planner_zone_modes_from_address(address: dict | None) -> dict[str, str]:
    raw = (address or {}).get("_planner_zone_modes", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(zone_id): "area" if str(mode).lower() == "area" else "rack"
        for zone_id, mode in raw.items()
    }


@router.get("/{warehouse_id}/planner-rules", response_model=PlannerRulesResponse)
async def get_planner_rules(
    warehouse_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return _planner_rules_from_address(warehouse.address)


@router.put("/{warehouse_id}/planner-rules", response_model=PlannerRulesResponse)
async def update_planner_rules(
    warehouse_id: str,
    body: PlannerRulesUpdate,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    address = dict(warehouse.address or {})
    address["_planner_rules"] = body.model_dump()
    warehouse.address = address
    await db.flush()
    return _planner_rules_from_address(warehouse.address)


@router.get("/{warehouse_id}/zones", response_model=list[ZoneResponse])
async def list_zones(
    warehouse_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    warehouse_result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = warehouse_result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    zone_modes = _planner_zone_modes_from_address(warehouse.address)

    result = await db.execute(
        select(
            Zone.id,
            Zone.warehouse_id,
            Zone.name,
            Zone.code,
            Zone.is_agv_zone,
            Zone.sequence,
            Zone.zone_type,
            Zone.coordinate_x,
            Zone.coordinate_y,
            Zone.coordinate_z,
            Zone.dimensions,
            Zone.layout_metadata,
            Zone.drawing_source,
            func.count(Location.id).label("location_count"),
        )
        .outerjoin(Location, Location.zone_id == Zone.id)
        .where(Zone.warehouse_id == warehouse_id, Zone.tenant_id == current_user.tenant_id)
        .group_by(
            Zone.id,
            Zone.warehouse_id,
            Zone.name,
            Zone.code,
            Zone.is_agv_zone,
            Zone.sequence,
            Zone.zone_type,
            Zone.coordinate_x,
            Zone.coordinate_y,
            Zone.coordinate_z,
            Zone.dimensions,
            Zone.layout_metadata,
            Zone.drawing_source,
        )
        .order_by(Zone.sequence, Zone.code)
    )
    return [
        ZoneResponse(
            id=row.id,
            warehouse_id=row.warehouse_id,
            name=row.name,
            code=row.code,
            is_agv_zone=row.is_agv_zone,
            sequence=row.sequence,
            layout_mode=zone_modes.get(row.id, "rack"),
            location_count=row.location_count or 0,
            zone_type=row.zone_type or "storage",
            coordinate_x=float(row.coordinate_x) if row.coordinate_x else None,
            coordinate_y=float(row.coordinate_y) if row.coordinate_y else None,
            coordinate_z=float(row.coordinate_z) if row.coordinate_z else None,
            dimensions=row.dimensions,
            layout_metadata=row.layout_metadata,
            drawing_source=row.drawing_source,
        )
        for row in result.all()
    ]


@router.post("/{warehouse_id}/zones", response_model=ZoneResponse, status_code=201)
async def create_zone(
    warehouse_id: str,
    body: ZoneCreate,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    warehouse_result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = warehouse_result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    zone = Zone(
        tenant_id=current_user.tenant_id,
        warehouse_id=warehouse.id,
        name=body.name,
        code=body.code,
        is_agv_zone=body.is_agv_zone,
        sequence=body.sequence,
        zone_type=body.zone_type,
        coordinate_x=body.coordinate_x,
        coordinate_y=body.coordinate_y,
        coordinate_z=body.coordinate_z,
        dimensions=body.dimensions,
        layout_metadata=body.layout_metadata,
        drawing_source=body.drawing_source,
    )
    db.add(zone)
    await db.flush()
    address = dict(warehouse.address or {})
    zone_modes = _planner_zone_modes_from_address(address)
    zone_modes[zone.id] = "area" if body.layout_mode == "area" else "rack"
    address["_planner_zone_modes"] = zone_modes
    warehouse.address = address

    return ZoneResponse(
        id=zone.id,
        warehouse_id=zone.warehouse_id,
        name=zone.name,
        code=zone.code,
        is_agv_zone=zone.is_agv_zone,
        sequence=zone.sequence,
        layout_mode=zone_modes.get(zone.id, "rack"),
        location_count=0,
        zone_type=zone.zone_type or "storage",
        coordinate_x=float(zone.coordinate_x) if zone.coordinate_x else None,
        coordinate_y=float(zone.coordinate_y) if zone.coordinate_y else None,
        coordinate_z=float(zone.coordinate_z) if zone.coordinate_z else None,
        dimensions=zone.dimensions,
        layout_metadata=zone.layout_metadata,
        drawing_source=zone.drawing_source,
    )


@router.put("/{warehouse_id}/zones/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    warehouse_id: str,
    zone_id: str,
    body: ZoneUpdate,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    zone_result = await db.execute(
        select(Zone).where(
            Zone.id == zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    zone = zone_result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    warehouse_result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = warehouse_result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    zone.name = body.name
    zone.code = body.code
    zone.is_agv_zone = body.is_agv_zone
    zone.sequence = body.sequence
    zone.zone_type = body.zone_type
    zone.coordinate_x = body.coordinate_x
    zone.coordinate_y = body.coordinate_y
    zone.coordinate_z = body.coordinate_z
    zone.dimensions = body.dimensions
    zone.layout_metadata = body.layout_metadata
    zone.drawing_source = body.drawing_source
    address = dict(warehouse.address or {})
    zone_modes = _planner_zone_modes_from_address(address)
    zone_modes[zone.id] = "area" if body.layout_mode == "area" else "rack"
    address["_planner_zone_modes"] = zone_modes
    warehouse.address = address
    await db.flush()

    location_count_result = await db.execute(
        select(func.count(Location.id)).where(Location.zone_id == zone.id)
    )
    location_count = location_count_result.scalar_one() or 0

    return ZoneResponse(
        id=zone.id,
        warehouse_id=zone.warehouse_id,
        name=zone.name,
        code=zone.code,
        is_agv_zone=zone.is_agv_zone,
        sequence=zone.sequence,
        layout_mode=zone_modes.get(zone.id, "rack"),
        location_count=location_count,
        zone_type=zone.zone_type or "storage",
        coordinate_x=float(zone.coordinate_x) if zone.coordinate_x else None,
        coordinate_y=float(zone.coordinate_y) if zone.coordinate_y else None,
        coordinate_z=float(zone.coordinate_z) if zone.coordinate_z else None,
        dimensions=zone.dimensions,
        layout_metadata=zone.layout_metadata,
        drawing_source=zone.drawing_source,
    )


@router.delete("/{warehouse_id}/zones/{zone_id}", status_code=204)
async def delete_zone(
    warehouse_id: str,
    zone_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    zone_result = await db.execute(
        select(Zone).where(
            Zone.id == zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    zone = zone_result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    location_count_result = await db.execute(
        select(func.count(Location.id)).where(Location.zone_id == zone.id)
    )
    if (location_count_result.scalar_one() or 0) > 0:
        raise HTTPException(
            status_code=400, detail="Cannot delete a zone that still has mapped locations"
        )

    warehouse_result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = warehouse_result.scalar_one_or_none()
    if warehouse:
        address = dict(warehouse.address or {})
        zone_modes = _planner_zone_modes_from_address(address)
        zone_modes.pop(zone.id, None)
        address["_planner_zone_modes"] = zone_modes
        warehouse.address = address

    await db.delete(zone)
    await db.flush()


@router.post("/{warehouse_id}/locations", response_model=LocationResponse, status_code=201)
async def create_location(
    warehouse_id: str,
    body: LocationCreate,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    warehouse_result = await db.execute(
        select(Warehouse.id).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    if not warehouse_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found")

    zone_result = await db.execute(
        select(Zone.id).where(
            Zone.id == body.zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    if not zone_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Zone does not belong to this warehouse")

    location = Location(
        tenant_id=current_user.tenant_id,
        warehouse_id=warehouse_id,
        zone_id=body.zone_id,
        barcode=body.barcode,
        aisle=body.aisle,
        rack=body.rack,
        level=body.level,
        position=body.position,
        location_type=body.location_type,
        coordinate_x=body.coordinate_x,
        coordinate_y=body.coordinate_y,
        coordinate_z=body.coordinate_z,
        is_agv_accessible=body.is_agv_accessible,
        max_weight_kg=body.max_weight_kg,
        dimensions=body.dimensions,
        layout_metadata=body.layout_metadata,
        drawing_source=body.drawing_source,
        wcs_point_metadata=body.wcs_point_metadata,
    )
    db.add(location)
    await db.flush()
    return LocationResponse(
        id=location.id,
        barcode=location.barcode,
        aisle=location.aisle,
        rack=location.rack,
        level=location.level,
        position=location.position,
        location_type=location.location_type,
        current_status=location.current_status,
        is_agv_accessible=location.is_agv_accessible,
        max_weight_kg=float(location.max_weight_kg) if location.max_weight_kg is not None else None,
        coordinate_x=float(location.coordinate_x) if location.coordinate_x else None,
        coordinate_y=float(location.coordinate_y) if location.coordinate_y else None,
        coordinate_z=float(location.coordinate_z) if location.coordinate_z else None,
        dimensions=location.dimensions,
        layout_metadata=location.layout_metadata,
        drawing_source=location.drawing_source,
        wcs_point_metadata=location.wcs_point_metadata,
    )


@router.put("/{warehouse_id}/locations/{location_id}", response_model=LocationResponse)
async def update_location(
    warehouse_id: str,
    location_id: str,
    body: LocationUpdate,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.warehouse_id == warehouse_id,
            Location.tenant_id == current_user.tenant_id,
        )
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    location.barcode = body.barcode
    location.aisle = body.aisle
    location.rack = body.rack
    location.level = body.level
    location.position = body.position
    location.location_type = body.location_type
    location.coordinate_x = body.coordinate_x
    location.coordinate_y = body.coordinate_y
    location.coordinate_z = body.coordinate_z
    location.is_agv_accessible = body.is_agv_accessible
    location.current_status = body.current_status
    location.max_weight_kg = body.max_weight_kg
    location.dimensions = body.dimensions
    location.layout_metadata = body.layout_metadata
    location.drawing_source = body.drawing_source
    location.wcs_point_metadata = body.wcs_point_metadata
    await db.flush()

    return LocationResponse(
        id=location.id,
        barcode=location.barcode,
        aisle=location.aisle,
        rack=location.rack,
        level=location.level,
        position=location.position,
        location_type=location.location_type,
        current_status=location.current_status,
        is_agv_accessible=location.is_agv_accessible,
        max_weight_kg=float(location.max_weight_kg) if location.max_weight_kg is not None else None,
        coordinate_x=float(location.coordinate_x) if location.coordinate_x else None,
        coordinate_y=float(location.coordinate_y) if location.coordinate_y else None,
        coordinate_z=float(location.coordinate_z) if location.coordinate_z else None,
        dimensions=location.dimensions,
        layout_metadata=location.layout_metadata,
        drawing_source=location.drawing_source,
        wcs_point_metadata=location.wcs_point_metadata,
    )


@router.put("/{warehouse_id}/racks/configure", response_model=RackConfigureResponse)
async def configure_rack(
    warehouse_id: str,
    body: RackConfigureRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    warehouse_result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = warehouse_result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    zone_result = await db.execute(
        select(Zone).where(
            Zone.id == body.zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    zone = zone_result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    existing_result = await db.execute(
        select(Location).where(
            Location.warehouse_id == warehouse_id,
            Location.zone_id == body.zone_id,
            Location.tenant_id == current_user.tenant_id,
            Location.aisle == body.current_aisle,
            Location.rack == body.current_rack,
        )
    )
    existing_locations = list(existing_result.scalars())
    if not existing_locations:
        raise HTTPException(status_code=404, detail="Rack not found")

    if body.levels < 1 or body.slots_per_level < 1:
        raise HTTPException(
            status_code=400, detail="Rack must have at least 1 level and 1 slot per level"
        )

    existing_by_key = {
        (location.level, location.position): location for location in existing_locations
    }
    target_keys = {
        (f"{level:02d}", f"{position:02d}")
        for level in range(1, body.levels + 1)
        for position in range(1, body.slots_per_level + 1)
    }
    keys_to_remove = set(existing_by_key) - target_keys
    removable_locations = [existing_by_key[key] for key in keys_to_remove]

    if removable_locations:
        removable_ids = [location.id for location in removable_locations]
        inventory_result = await db.execute(
            select(Inventory.location_id).where(
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.location_id.in_(removable_ids),
                Inventory.quantity_on_hand > 0,
            )
        )
        if inventory_result.first():
            raise HTTPException(
                status_code=400,
                detail="Cannot reduce levels or slots while the removed locations still hold inventory",
            )

    for level, position in sorted(target_keys):
        location = existing_by_key.get((level, position))
        barcode = f"{zone.code}-{body.aisle}-{body.rack}-{level}-{position}"
        if location:
            location.barcode = barcode
            location.aisle = body.aisle
            location.rack = body.rack
            location.level = level
            location.position = position
            location.location_type = body.location_type
            location.is_agv_accessible = body.is_agv_accessible
            location.max_weight_kg = body.max_weight_kg
        else:
            db.add(
                Location(
                    tenant_id=current_user.tenant_id,
                    warehouse_id=warehouse_id,
                    zone_id=body.zone_id,
                    barcode=barcode,
                    aisle=body.aisle,
                    rack=body.rack,
                    level=level,
                    position=position,
                    location_type=body.location_type,
                    is_agv_accessible=body.is_agv_accessible,
                    max_weight_kg=body.max_weight_kg,
                    current_status=LocationStatus.AVAILABLE.value,
                )
            )

    for location in removable_locations:
        await db.delete(location)

    await db.flush()

    return RackConfigureResponse(
        zone_id=body.zone_id,
        aisle=body.aisle,
        rack=body.rack,
        levels=body.levels,
        slots_per_level=body.slots_per_level,
        location_count=body.levels * body.slots_per_level,
        location_type=body.location_type,
        is_agv_accessible=body.is_agv_accessible,
        max_weight_kg=body.max_weight_kg,
    )


@router.post("/{warehouse_id}/racks", response_model=RackConfigureResponse, status_code=201)
async def create_rack(
    warehouse_id: str,
    body: RackCreateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    warehouse_result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == current_user.tenant_id,
            Warehouse.is_active == True,  # noqa: E712
        )
    )
    warehouse = warehouse_result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    zone_result = await db.execute(
        select(Zone).where(
            Zone.id == body.zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    zone = zone_result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    if body.levels < 1 or body.slots_per_level < 1:
        raise HTTPException(
            status_code=400, detail="Rack must have at least 1 level and 1 slot per level"
        )

    existing_result = await db.execute(
        select(Location.id).where(
            Location.warehouse_id == warehouse_id,
            Location.zone_id == body.zone_id,
            Location.tenant_id == current_user.tenant_id,
            Location.aisle == body.aisle,
            Location.rack == body.rack,
        )
    )
    if existing_result.first():
        raise HTTPException(status_code=400, detail="Rack already exists in this zone")

    for level_index in range(1, body.levels + 1):
        for slot_index in range(1, body.slots_per_level + 1):
            level = f"{level_index:02d}"
            position = f"{slot_index:02d}"
            db.add(
                Location(
                    tenant_id=current_user.tenant_id,
                    warehouse_id=warehouse_id,
                    zone_id=body.zone_id,
                    barcode=f"{zone.code}-{body.aisle}-{body.rack}-{level}-{position}",
                    aisle=body.aisle,
                    rack=body.rack,
                    level=level,
                    position=position,
                    location_type=body.location_type,
                    is_agv_accessible=body.is_agv_accessible,
                    max_weight_kg=body.max_weight_kg,
                    current_status=LocationStatus.AVAILABLE.value,
                )
            )

    await db.flush()

    return RackConfigureResponse(
        zone_id=body.zone_id,
        aisle=body.aisle,
        rack=body.rack,
        levels=body.levels,
        slots_per_level=body.slots_per_level,
        location_count=body.levels * body.slots_per_level,
        location_type=body.location_type,
        is_agv_accessible=body.is_agv_accessible,
        max_weight_kg=body.max_weight_kg,
    )


@router.delete("/{warehouse_id}/racks", status_code=204)
async def delete_rack(
    warehouse_id: str,
    body: RackDeleteRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    zone_result = await db.execute(
        select(Zone.id).where(
            Zone.id == body.zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    if not zone_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Zone not found")

    locations_result = await db.execute(
        select(Location).where(
            Location.warehouse_id == warehouse_id,
            Location.zone_id == body.zone_id,
            Location.tenant_id == current_user.tenant_id,
            Location.aisle == body.aisle,
            Location.rack == body.rack,
        )
    )
    locations = list(locations_result.scalars())
    if not locations:
        raise HTTPException(status_code=404, detail="Rack not found")

    inventory_result = await db.execute(
        select(Inventory.location_id).where(
            Inventory.tenant_id == current_user.tenant_id,
            Inventory.location_id.in_([location.id for location in locations]),
            Inventory.quantity_on_hand > 0,
        )
    )
    if inventory_result.first():
        raise HTTPException(status_code=400, detail="Cannot delete a rack that still has inventory")

    for location in locations:
        await db.delete(location)
    await db.flush()


@router.put("/{warehouse_id}/aisles/configure", response_model=AisleConfigureResponse)
async def configure_aisle(
    warehouse_id: str,
    body: AisleConfigureRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    zone_result = await db.execute(
        select(Zone).where(
            Zone.id == body.zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    zone = zone_result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    locations_result = await db.execute(
        select(Location).where(
            Location.warehouse_id == warehouse_id,
            Location.zone_id == body.zone_id,
            Location.tenant_id == current_user.tenant_id,
            Location.aisle == body.current_aisle,
        )
    )
    locations = list(locations_result.scalars())
    if not locations:
        raise HTTPException(status_code=404, detail="Aisle not found")

    target_aisle = body.aisle.strip()
    if not target_aisle:
        raise HTTPException(status_code=400, detail="Aisle code is required")

    if target_aisle != body.current_aisle:
        conflict_result = await db.execute(
            select(Location.id).where(
                Location.warehouse_id == warehouse_id,
                Location.zone_id == body.zone_id,
                Location.tenant_id == current_user.tenant_id,
                Location.aisle == target_aisle,
            )
        )
        if conflict_result.first():
            raise HTTPException(status_code=400, detail="Aisle already exists in this zone")

    for location in locations:
        location.aisle = target_aisle
        location.barcode = (
            f"{zone.code}-{target_aisle}-{location.rack}-{location.level}-{location.position}"
        )
        location.location_type = body.location_type
        location.is_agv_accessible = body.is_agv_accessible
        location.max_weight_kg = body.max_weight_kg

    await db.flush()

    return AisleConfigureResponse(
        zone_id=body.zone_id,
        aisle=target_aisle,
        rack_count=len({location.rack for location in locations}),
        location_count=len(locations),
        location_type=body.location_type,
        is_agv_accessible=body.is_agv_accessible,
        max_weight_kg=body.max_weight_kg,
    )


@router.post("/{warehouse_id}/aisles", response_model=AisleConfigureResponse, status_code=201)
async def create_aisle(
    warehouse_id: str,
    body: AisleCreateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    zone_result = await db.execute(
        select(Zone).where(
            Zone.id == body.zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    zone = zone_result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    if body.levels < 1 or body.slots_per_level < 1:
        raise HTTPException(status_code=400, detail="Aisle must have at least 1 level and 1 slot")

    aisle_code = body.aisle.strip()
    rack_code = body.first_rack.strip()
    if not aisle_code or not rack_code:
        raise HTTPException(status_code=400, detail="Aisle and first rack are required")

    existing_result = await db.execute(
        select(Location.id).where(
            Location.warehouse_id == warehouse_id,
            Location.zone_id == body.zone_id,
            Location.tenant_id == current_user.tenant_id,
            Location.aisle == aisle_code,
        )
    )
    if existing_result.first():
        raise HTTPException(status_code=400, detail="Aisle already exists in this zone")

    for level_index in range(1, body.levels + 1):
        for slot_index in range(1, body.slots_per_level + 1):
            level = f"{level_index:02d}"
            position = f"{slot_index:02d}"
            db.add(
                Location(
                    tenant_id=current_user.tenant_id,
                    warehouse_id=warehouse_id,
                    zone_id=body.zone_id,
                    barcode=f"{zone.code}-{aisle_code}-{rack_code}-{level}-{position}",
                    aisle=aisle_code,
                    rack=rack_code,
                    level=level,
                    position=position,
                    location_type=body.location_type,
                    is_agv_accessible=body.is_agv_accessible,
                    max_weight_kg=body.max_weight_kg,
                    current_status=LocationStatus.AVAILABLE.value,
                )
            )

    await db.flush()

    return AisleConfigureResponse(
        zone_id=body.zone_id,
        aisle=aisle_code,
        rack_count=1,
        location_count=body.levels * body.slots_per_level,
        location_type=body.location_type,
        is_agv_accessible=body.is_agv_accessible,
        max_weight_kg=body.max_weight_kg,
    )


@router.delete("/{warehouse_id}/aisles", status_code=204)
async def delete_aisle(
    warehouse_id: str,
    body: AisleDeleteRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    zone_result = await db.execute(
        select(Zone.id).where(
            Zone.id == body.zone_id,
            Zone.warehouse_id == warehouse_id,
            Zone.tenant_id == current_user.tenant_id,
        )
    )
    if not zone_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Zone not found")

    locations_result = await db.execute(
        select(Location).where(
            Location.warehouse_id == warehouse_id,
            Location.zone_id == body.zone_id,
            Location.tenant_id == current_user.tenant_id,
            Location.aisle == body.aisle,
        )
    )
    locations = list(locations_result.scalars())
    if not locations:
        raise HTTPException(status_code=404, detail="Aisle not found")

    inventory_result = await db.execute(
        select(Inventory.location_id).where(
            Inventory.tenant_id == current_user.tenant_id,
            Inventory.location_id.in_([location.id for location in locations]),
            Inventory.quantity_on_hand > 0,
        )
    )
    if inventory_result.first():
        raise HTTPException(
            status_code=400, detail="Cannot delete an aisle that still has inventory"
        )

    for location in locations:
        await db.delete(location)
    await db.flush()


@router.delete("/{warehouse_id}/locations/{location_id}", status_code=204)
async def delete_location(
    warehouse_id: str,
    location_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Location).where(
            Location.id == location_id,
            Location.warehouse_id == warehouse_id,
            Location.tenant_id == current_user.tenant_id,
        )
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    await db.delete(location)
    await db.flush()
