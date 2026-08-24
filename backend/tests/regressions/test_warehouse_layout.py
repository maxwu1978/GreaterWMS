"""Regression tests: warehouse layout (aisles and racks) (split from tests/test_regressions.py)."""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.warehouses import (
    AisleConfigureRequest,
    AisleCreateRequest,
    AisleDeleteRequest,
    RackConfigureRequest,
    RackCreateRequest,
    RackDeleteRequest,
    configure_aisle,
    configure_rack,
    create_aisle,
    create_rack,
    delete_aisle,
    delete_rack,
)
from app.core.security import TokenPayload, UserRole
from app.models.inventory import SKU, Inventory
from app.models.warehouse import Location, LocationType, Warehouse, Zone


@pytest.mark.asyncio
async def test_create_rack_builds_full_location_skeleton(db: AsyncSession, tenant_id: str):
    warehouse = Warehouse(id="wh-rack-create", tenant_id=tenant_id, name="Planner", code="PLAN")
    zone = Zone(
        id="zone-rack-create",
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        name="Zone A",
        code="ZA",
    )
    db.add_all([warehouse, zone])
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="planner@example.com",
        exp=datetime.now(UTC),
    )

    response = await create_rack(
        warehouse.id,
        RackCreateRequest(
            zone_id=zone.id,
            aisle="03",
            rack="04",
            levels=2,
            slots_per_level=3,
            location_type=LocationType.STORAGE.value,
            is_agv_accessible=True,
            max_weight_kg=1600,
        ),
        current_user=tenant_admin,
        db=db,
    )

    created_locations = (
        (
            await db.execute(
                select(Location).where(
                    Location.warehouse_id == warehouse.id,
                    Location.zone_id == zone.id,
                    Location.aisle == "03",
                    Location.rack == "04",
                )
            )
        )
        .scalars()
        .all()
    )

    assert response.location_count == 6
    assert response.levels == 2
    assert response.slots_per_level == 3
    assert len(created_locations) == 6
    assert all(location.is_agv_accessible is True for location in created_locations)
    assert all(float(location.max_weight_kg) == 1600 for location in created_locations)
    assert {location.level for location in created_locations} == {"01", "02"}
    assert {location.position for location in created_locations} == {"01", "02", "03"}
    assert created_locations[0].barcode.startswith("ZA-03-04-")


@pytest.mark.asyncio
async def test_configure_rack_updates_levels_slots_and_capacity(db: AsyncSession, tenant_id: str):
    warehouse = Warehouse(id="wh-rack-1", tenant_id=tenant_id, name="Planner", code="PLAN")
    zone = Zone(
        id="zone-rack-1", tenant_id=tenant_id, warehouse_id=warehouse.id, name="Zone A", code="ZA"
    )
    db.add_all([warehouse, zone])
    db.add_all(
        [
            Location(
                id="loc-rack-1",
                tenant_id=tenant_id,
                warehouse_id=warehouse.id,
                zone_id=zone.id,
                barcode="ZA-01-01-01-01",
                aisle="01",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                max_weight_kg=900,
            ),
            Location(
                id="loc-rack-2",
                tenant_id=tenant_id,
                warehouse_id=warehouse.id,
                zone_id=zone.id,
                barcode="ZA-01-01-02-01",
                aisle="01",
                rack="01",
                level="02",
                position="01",
                location_type=LocationType.STORAGE.value,
                max_weight_kg=900,
            ),
        ]
    )
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="planner@example.com",
        exp=datetime.now(UTC),
    )

    response = await configure_rack(
        warehouse.id,
        RackConfigureRequest(
            zone_id=zone.id,
            current_aisle="01",
            current_rack="01",
            aisle="02",
            rack="03",
            levels=3,
            slots_per_level=2,
            location_type=LocationType.QUALITY.value,
            is_agv_accessible=True,
            max_weight_kg=1500,
        ),
        current_user=tenant_admin,
        db=db,
    )

    updated_locations = (
        (
            await db.execute(
                select(Location).where(
                    Location.warehouse_id == warehouse.id,
                    Location.zone_id == zone.id,
                    Location.aisle == "02",
                    Location.rack == "03",
                )
            )
        )
        .scalars()
        .all()
    )

    assert response.location_count == 6
    assert response.levels == 3
    assert response.slots_per_level == 2
    assert len(updated_locations) == 6
    assert all(
        location.location_type == LocationType.QUALITY.value for location in updated_locations
    )
    assert all(location.is_agv_accessible is True for location in updated_locations)
    assert all(float(location.max_weight_kg) == 1500 for location in updated_locations)
    assert {location.level for location in updated_locations} == {"01", "02", "03"}
    assert {location.position for location in updated_locations} == {"01", "02"}


@pytest.mark.asyncio
async def test_delete_rack_rejects_when_inventory_exists(
    db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str
):
    warehouse = Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Planner", code="PLAN")
    zone = Zone(
        id="zone-rack-del", tenant_id=tenant_id, warehouse_id=warehouse.id, name="Zone A", code="ZA"
    )
    location = Location(
        id="loc-rack-del",
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        zone_id=zone.id,
        barcode="ZA-01-01-01-01",
        aisle="01",
        rack="01",
        level="01",
        position="01",
        location_type=LocationType.STORAGE.value,
    )
    sku = SKU(
        id="sku-rack-del",
        tenant_id=tenant_id,
        client_id=client_id,
        sku_code="SKU-RACK",
        name="Rack SKU",
    )
    inventory = Inventory(
        id="inv-rack-del",
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        sku_id=sku.id,
        quantity_on_hand=5,
    )
    db.add_all([warehouse, zone, location, sku, inventory])
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="planner@example.com",
        exp=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc:
        await delete_rack(
            warehouse.id,
            RackDeleteRequest(zone_id=zone.id, aisle="01", rack="01"),
            current_user=tenant_admin,
            db=db,
        )

    assert exc.value.status_code == 400
    assert "still has inventory" in exc.value.detail


@pytest.mark.asyncio
async def test_create_aisle_builds_first_rack_skeleton(
    db: AsyncSession, tenant_id: str, warehouse_id: str
):
    warehouse = Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Planner", code="PLAN")
    zone = Zone(
        id="zone-aisle-create",
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        name="Zone A",
        code="ZA",
    )
    db.add_all([warehouse, zone])
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="planner@example.com",
        exp=datetime.now(UTC),
    )

    response = await create_aisle(
        warehouse.id,
        AisleCreateRequest(
            zone_id=zone.id,
            aisle="03",
            first_rack="01",
            levels=2,
            slots_per_level=3,
            location_type=LocationType.STORAGE.value,
            is_agv_accessible=True,
            max_weight_kg=900,
        ),
        current_user=tenant_admin,
        db=db,
    )

    created_locations = (
        (
            await db.execute(
                select(Location).where(
                    Location.zone_id == zone.id,
                    Location.aisle == "03",
                    Location.rack == "01",
                )
            )
        )
        .scalars()
        .all()
    )

    assert response.aisle == "03"
    assert response.rack_count == 1
    assert response.location_count == 6
    assert len(created_locations) == 6
    assert all(location.is_agv_accessible is True for location in created_locations)


@pytest.mark.asyncio
async def test_configure_aisle_renames_and_updates_locations(
    db: AsyncSession, tenant_id: str, warehouse_id: str
):
    warehouse = Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Planner", code="PLAN")
    zone = Zone(
        id="zone-aisle-update",
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        name="Zone A",
        code="ZA",
    )
    locations = [
        Location(
            id=f"loc-aisle-{index}",
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            zone_id=zone.id,
            barcode=f"ZA-01-0{index}-01-01",
            aisle="01",
            rack=f"0{index}",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            is_agv_accessible=False,
            max_weight_kg=500,
        )
        for index in (1, 2)
    ]
    db.add_all([warehouse, zone, *locations])
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="planner@example.com",
        exp=datetime.now(UTC),
    )

    response = await configure_aisle(
        warehouse.id,
        AisleConfigureRequest(
            zone_id=zone.id,
            current_aisle="01",
            aisle="05",
            location_type=LocationType.QUALITY.value,
            is_agv_accessible=True,
            max_weight_kg=1500,
        ),
        current_user=tenant_admin,
        db=db,
    )

    updated_locations = (
        (
            await db.execute(
                select(Location).where(
                    Location.zone_id == zone.id,
                    Location.aisle == "05",
                )
            )
        )
        .scalars()
        .all()
    )

    assert response.aisle == "05"
    assert response.rack_count == 2
    assert response.location_count == 2
    assert len(updated_locations) == 2
    assert all(
        location.location_type == LocationType.QUALITY.value for location in updated_locations
    )
    assert all(location.is_agv_accessible is True for location in updated_locations)
    assert all(float(location.max_weight_kg) == 1500 for location in updated_locations)


@pytest.mark.asyncio
async def test_delete_aisle_rejects_when_inventory_exists(
    db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str
):
    warehouse = Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Planner", code="PLAN")
    zone = Zone(
        id="zone-aisle-del",
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        name="Zone A",
        code="ZA",
    )
    location = Location(
        id="loc-aisle-del",
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        zone_id=zone.id,
        barcode="ZA-09-01-01-01",
        aisle="09",
        rack="01",
        level="01",
        position="01",
        location_type=LocationType.STORAGE.value,
    )
    sku = SKU(
        id="sku-aisle-del",
        tenant_id=tenant_id,
        client_id=client_id,
        sku_code="SKU-AISLE",
        name="Aisle SKU",
    )
    inventory = Inventory(
        id="inv-aisle-del",
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse.id,
        location_id=location.id,
        sku_id=sku.id,
        quantity_on_hand=5,
    )
    db.add_all([warehouse, zone, location, sku, inventory])
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="planner@example.com",
        exp=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc:
        await delete_aisle(
            warehouse.id,
            AisleDeleteRequest(zone_id=zone.id, aisle="09"),
            current_user=tenant_admin,
            db=db,
        )

    assert exc.value.status_code == 400
    assert "still has inventory" in exc.value.detail


@pytest.mark.asyncio
async def test_warehouse_update_preserves_reserved_address_keys(
    db: AsyncSession, tenant_id: str
):
    """Editing a warehouse's street address must not wipe system keys stored in
    Warehouse.address (_planner_rules, _wcs, _planner_zone_modes, _blueprint_*),
    and user input must not be able to inject underscore-prefixed keys."""
    from app.api.v1.endpoints.warehouses import WarehouseUpdate, update_warehouse

    warehouse = Warehouse(
        id="wh-reserved-keys",
        tenant_id=tenant_id,
        name="Main",
        code="MAIN",
        address={
            "street": "1 Old Rd",
            "city": "Dallas",
            "_planner_rules": {"different_sku_slot_policy": "block"},
            "_wcs": {"base_url": "http://wcs.local", "app_key": "secret"},
            "_planner_zone_modes": {"zone-1": "rack"},
        },
    )
    db.add(warehouse)
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="admin@example.com",
        exp=datetime.now(UTC),
    )
    await update_warehouse(
        warehouse_id="wh-reserved-keys",
        body=WarehouseUpdate(
            name="Main",
            code="MAIN",
            address={"street": "2 New Rd", "city": "Austin", "_wcs": {"app_key": "injected"}},
        ),
        current_user=tenant_admin,
        db=db,
    )

    refreshed = await db.scalar(select(Warehouse).where(Warehouse.id == "wh-reserved-keys"))
    assert refreshed.address["street"] == "2 New Rd"
    assert refreshed.address["city"] == "Austin"
    # System keys survive the user-facing update
    assert refreshed.address["_planner_rules"] == {"different_sku_slot_policy": "block"}
    assert refreshed.address["_wcs"]["app_key"] == "secret"
    assert refreshed.address["_planner_zone_modes"] == {"zone-1": "rack"}
