"""Seed a representative WMS performance fixture for staging query-plan checks.

Usage:
    DATABASE_URL="postgresql+asyncpg://..." python scripts/seed_performance_fixture.py --confirm-seed
    DATABASE_URL="postgresql+asyncpg://..." python scripts/seed_performance_fixture.py --confirm-seed --replace

The script is intentionally staging-oriented. By default it only runs when the
DATABASE_URL points at Neon. Use --allow-non-neon only for local development or
a known non-production staging database.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select, text

from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.models.billing import BillingLineItem, BillingPeriod, Invoice, RateCard
from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    InboundPackageStatus,
    InboundStatus,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
    ReceivingLabel,
    ReceivingObservedCode,
)
from app.models.task import PickAllocation, PutawayAllocation, Task, TaskStatus, TaskType
from app.models.tenant import Tenant, User
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.outbound_readiness import (
    PICK_READINESS_RANKS,
    shipping_readiness_rank_from_values,
)

TENANT_ID = "perf-tenant-001"
TENANT_CODE = "PERFSEED"
WAREHOUSE_ID = "perf-warehouse-001"
ZONE_ID = "perf-zone-ambient"
STAGING_LOCATIONS_PER_WAREHOUSE = 5

INSERT_ORDER = [
    Tenant,
    Client,
    User,
    Warehouse,
    Zone,
    Location,
    SKU,
    Inventory,
    InventoryTransaction,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    ReceivingLabel,
    ReceivingObservedCode,
    OutboundOrder,
    OutboundOrderLine,
    Task,
    PickAllocation,
    PutawayAllocation,
    RateCard,
    BillingPeriod,
    BillingLineItem,
    Invoice,
]


def _storage_location_id(index: int) -> str:
    return f"perf-loc-storage-{index:05d}"


def _staging_location_id(index: int) -> str:
    return f"perf-loc-stage-{index:03d}"


def _warehouse_id(index: int) -> str:
    return WAREHOUSE_ID if index == 0 else f"perf-warehouse-{index + 1:03d}"


def _zone_id(index: int) -> str:
    return ZONE_ID if index == 0 else f"perf-zone-ambient-{index + 1:03d}"


def _sku_id(index: int) -> str:
    return f"perf-sku-{index:05d}"


def _client_id(index: int) -> str:
    return f"perf-client-{index:03d}"


def _profile_index(index: int, count: int, profile: str, salt: int) -> int:
    if count <= 1:
        return 0
    if profile != "production-like":
        return index % count

    # Deterministic skew: lower indexes become hotter, which better resembles
    # real warehouses where a few clients/SKUs/warehouses dominate volume.
    raw = ((index + 1) * (salt * 2_654_435_761) + salt) % 1_000_003
    fraction = raw / 1_000_003
    return min(count - 1, int((fraction**2.35) * count))


def _sku_index_for_record(index: int, args: argparse.Namespace, salt: int = 31) -> int:
    return _profile_index(index, args.skus, args.profile, salt)


def _client_index_for_sku(sku_index: int, args: argparse.Namespace) -> int:
    return _profile_index(sku_index, args.clients, args.profile, 17)


def _client_index_for_record(index: int, args: argparse.Namespace, salt: int = 43) -> int:
    return _profile_index(index, args.clients, args.profile, salt)


def _warehouse_index_for_record(index: int, args: argparse.Namespace, salt: int = 61) -> int:
    return _profile_index(index, args.warehouses, args.profile, salt)


def _storage_index_for_warehouse(seed: int, warehouse_index: int, args: argparse.Namespace) -> int:
    slots = max(1, (args.locations - warehouse_index + args.warehouses - 1) // args.warehouses)
    return warehouse_index + (seed % slots) * args.warehouses


def _staging_index_for_warehouse(seed: int, warehouse_index: int) -> int:
    return warehouse_index * STAGING_LOCATIONS_PER_WAREHOUSE + (
        seed % STAGING_LOCATIONS_PER_WAREHOUSE
    )


def _require_safe_target(allow_non_neon: bool) -> None:
    db_url = settings.DATABASE_URL.lower()
    if "neon.tech" in db_url or allow_non_neon:
        return
    raise SystemExit(
        "Refusing to seed a non-Neon database. "
        "Use --allow-non-neon only for local or known staging databases."
    )


async def _delete_existing_fixture() -> None:
    async with async_session_factory() as session:
        existing_id = await session.scalar(select(Tenant.id).where(Tenant.code == TENANT_CODE))
        if not existing_id:
            return

        for model in [
            PickAllocation,
            PutawayAllocation,
            Task,
            Invoice,
            BillingLineItem,
            BillingPeriod,
            RateCard,
            InventoryTransaction,
            Inventory,
            ReceivingObservedCode,
            HandlingUnit,
            ReceivingLabel,
            InboundPackage,
            InboundOrderLine,
            InboundOrder,
            OutboundOrderLine,
            OutboundOrder,
            SKU,
            Location,
            Zone,
            Warehouse,
            User,
            Client,
        ]:
            await session.execute(delete(model).where(model.tenant_id == existing_id))
        await session.execute(delete(Tenant).where(Tenant.id == existing_id))
        await session.commit()


async def _ensure_empty_or_replace(replace: bool) -> None:
    async with async_session_factory() as session:
        existing = await session.scalar(select(Tenant.id).where(Tenant.code == TENANT_CODE))
        if existing and not replace:
            raise SystemExit(
                f"Fixture tenant {TENANT_CODE} already exists. Re-run with --replace to rebuild it."
            )
    if replace:
        await _delete_existing_fixture()


def _build_master_data(args: argparse.Namespace) -> list[object]:
    objects: list[object] = [
        Tenant(
            id=TENANT_ID,
            name="Performance Seed 3PL",
            code=TENANT_CODE,
            contact_email="performance-seed@example.com",
            plan_tier="enterprise",
            settings={
                "performance_fixture": True,
                "profile": args.profile,
                "warehouses": args.warehouses,
            },
        ),
    ]

    for warehouse_index in range(args.warehouses):
        warehouse_suffix = "" if warehouse_index == 0 else f" {warehouse_index + 1:03d}"
        code_suffix = "" if warehouse_index == 0 else f"{warehouse_index + 1:03d}"
        objects.extend(
            [
                Warehouse(
                    id=_warehouse_id(warehouse_index),
                    tenant_id=TENANT_ID,
                    name=f"Performance Warehouse{warehouse_suffix}",
                    code=f"PERFWH{code_suffix}",
                    timezone="UTC",
                ),
                Zone(
                    id=_zone_id(warehouse_index),
                    tenant_id=TENANT_ID,
                    warehouse_id=_warehouse_id(warehouse_index),
                    name=f"Ambient Storage{warehouse_suffix}",
                    code=f"AMB{code_suffix}",
                    sequence=warehouse_index + 1,
                ),
            ]
        )

    for index in range(args.clients):
        objects.append(
            Client(
                id=_client_id(index),
                tenant_id=TENANT_ID,
                name=f"Performance Client {index:03d}",
                code=f"PC{index:03d}",
                contact_email=f"client{index:03d}@example.com",
                billing_enabled=True,
                portal_access=True,
            )
        )

    for index in range(args.locations):
        warehouse_index = index % args.warehouses
        local_index = index // args.warehouses
        aisle = local_index // 100 + 1
        rack = local_index // 10 % 10 + 1
        level = local_index % 5 + 1
        position = local_index % 20 + 1
        barcode_prefix = f"W{warehouse_index + 1:02d}-" if args.warehouses > 1 else ""
        objects.append(
            Location(
                id=_storage_location_id(index),
                tenant_id=TENANT_ID,
                warehouse_id=_warehouse_id(warehouse_index),
                zone_id=_zone_id(warehouse_index),
                barcode=f"{barcode_prefix}A-{aisle:02d}-{rack:02d}-{level:02d}-{position:02d}",
                aisle=f"{aisle:02d}",
                rack=f"{rack:02d}",
                level=f"{level:02d}",
                position=f"{position:02d}",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.OCCUPIED.value,
                pick_sequence=index,
            )
        )

    for warehouse_index in range(args.warehouses):
        for slot in range(STAGING_LOCATIONS_PER_WAREHOUSE):
            staging_index = _staging_index_for_warehouse(slot, warehouse_index)
            barcode_prefix = f"W{warehouse_index + 1:02d}-" if args.warehouses > 1 else ""
            objects.append(
                Location(
                    id=_staging_location_id(staging_index),
                    tenant_id=TENANT_ID,
                    warehouse_id=_warehouse_id(warehouse_index),
                    zone_id=_zone_id(warehouse_index),
                    barcode=f"{barcode_prefix}STAGE-{slot + 1:02d}",
                    aisle="STAGE",
                    rack=f"{slot + 1:02d}",
                    level="01",
                    position="01",
                    location_type=LocationType.STAGING.value,
                    current_status=LocationStatus.OCCUPIED.value,
                    pick_sequence=10_000 + staging_index,
                )
            )

    for index in range(args.skus):
        client_index = _client_index_for_sku(index, args)
        objects.append(
            SKU(
                id=_sku_id(index),
                tenant_id=TENANT_ID,
                client_id=_client_id(client_index),
                sku_code=f"PERF-SKU-{index:05d}",
                barcode=f"PERFBC{index:05d}",
                name=f"Performance SKU {index:05d}",
                weight_kg=1 + (index % 30) / 10,
            )
        )

    return objects


def _build_inventory(args: argparse.Namespace) -> list[object]:
    objects: list[object] = []
    now = datetime.now(UTC)
    for index in range(args.inventory):
        sku_index = _sku_index_for_record(index, args)
        client_index = _client_index_for_sku(sku_index, args)
        warehouse_index = _warehouse_index_for_record(index, args)
        location_index = _storage_index_for_warehouse(index, warehouse_index, args)
        on_hand = 12 + (index % 80)
        if args.profile == "production-like" and sku_index < max(1, args.skus // 20):
            on_hand += 40 + (index % 120)
        allocated = min(on_hand, index % 11)
        objects.append(
            Inventory(
                id=f"perf-inv-{index:06d}",
                tenant_id=TENANT_ID,
                client_id=_client_id(client_index),
                warehouse_id=_warehouse_id(warehouse_index),
                location_id=_storage_location_id(location_index),
                sku_id=_sku_id(sku_index),
                quantity_on_hand=on_hand,
                quantity_allocated=allocated,
                quantity_damaged=1 if index % 37 == 0 else 0,
                lot_number=f"LOT-{index % 120:03d}",
                received_at=now - timedelta(days=index % 180),
            )
        )
    return objects


def _build_inbound(args: argparse.Namespace) -> list[object]:
    objects: list[object] = []
    statuses = [
        InboundStatus.EXPECTED.value,
        InboundStatus.ARRIVED.value,
        InboundStatus.RECEIVING.value,
        InboundStatus.PUTAWAY.value,
        InboundStatus.COMPLETED.value,
    ]
    package_statuses = [
        InboundPackageStatus.EXPECTED.value,
        InboundPackageStatus.RECEIVING.value,
        InboundPackageStatus.RECEIVED.value,
        InboundPackageStatus.STAGED.value,
        InboundPackageStatus.PUTAWAY_PENDING.value,
        InboundPackageStatus.STORED.value,
    ]
    for index in range(args.inbound_orders):
        sku_index = _sku_index_for_record(index, args, salt=67)
        client_index = _client_index_for_sku(sku_index, args)
        warehouse_index = _warehouse_index_for_record(index, args, salt=71)
        staging_index = _staging_index_for_warehouse(index, warehouse_index)
        status = statuses[index % len(statuses)]
        order_id = f"perf-inbound-{index:06d}"
        line_id = f"perf-inbound-line-{index:06d}"
        package_id = f"perf-inbound-package-{index:06d}"
        label_id = f"perf-label-{index:06d}"
        expected_qty = 5 + (index % 20)
        received_qty = expected_qty if status in {"putaway", "completed"} else 0
        created_at = datetime.now(UTC) - timedelta(days=index % 120, minutes=index % 1440)
        objects.extend(
            [
                InboundOrder(
                    id=order_id,
                    tenant_id=TENANT_ID,
                    client_id=_client_id(client_index),
                    warehouse_id=_warehouse_id(warehouse_index),
                    order_number=f"PERF-IN-{index:06d}",
                    reference_number=f"PIN-{index:06d}",
                    status=status,
                    expected_date=created_at + timedelta(days=2),
                    received_date=created_at if status in {"putaway", "completed"} else None,
                    created_at=created_at,
                ),
                InboundOrderLine(
                    id=line_id,
                    tenant_id=TENANT_ID,
                    order_id=order_id,
                    sku_id=_sku_id(sku_index),
                    line_number=1,
                    quantity_expected=expected_qty,
                    quantity_received=received_qty,
                    staging_location_id=_staging_location_id(staging_index),
                ),
                InboundPackage(
                    id=package_id,
                    tenant_id=TENANT_ID,
                    order_id=order_id,
                    order_line_id=line_id,
                    package_number=1,
                    label_sequence=1,
                    package_type="carton",
                    status=package_statuses[index % len(package_statuses)],
                    expected_qty=expected_qty,
                    received_qty=received_qty,
                    staging_location_id=_staging_location_id(staging_index),
                    external_tracking_number=f"TRK-PERF-IN-{index:06d}",
                    created_at=created_at,
                ),
                ReceivingLabel(
                    id=label_id,
                    tenant_id=TENANT_ID,
                    order_id=order_id,
                    order_line_id=line_id,
                    inbound_package_id=package_id,
                    sku_id=_sku_id(sku_index),
                    label_code=f"RCV-PERF-{index:06d}",
                    expected_qty=expected_qty,
                    received_qty=received_qty,
                    status="received" if received_qty else "pending",
                    created_at=created_at,
                    extra_data={"print_count": 0 if index % 4 == 0 else 1},
                ),
            ]
        )
    return objects


def _build_outbound_and_tasks(args: argparse.Namespace) -> list[object]:
    objects: list[object] = []
    outbound_statuses = [
        OutboundStatus.PENDING.value,
        OutboundStatus.ALLOCATED.value,
        OutboundStatus.PICKING.value,
        OutboundStatus.PICKED.value,
        OutboundStatus.PACKING.value,
        OutboundStatus.PACKED.value,
        OutboundStatus.SHIPPED.value,
    ]
    for index in range(args.outbound_orders):
        sku_index = _sku_index_for_record(index, args, salt=83)
        client_index = _client_index_for_sku(sku_index, args)
        warehouse_index = _warehouse_index_for_record(index, args, salt=89)
        pick_location_index = _storage_index_for_warehouse(index, warehouse_index, args)
        status = outbound_statuses[index % len(outbound_statuses)]
        order_id = f"perf-outbound-{index:06d}"
        line_id = f"perf-outbound-line-{index:06d}"
        created_at = datetime.now(UTC) - timedelta(days=index % 90, minutes=index % 1440)
        carrier = (
            "UPS" if status in {OutboundStatus.PACKED.value, OutboundStatus.SHIPPED.value} else None
        )
        tracking = f"1ZPERF{index:06d}" if status == OutboundStatus.SHIPPED.value else None
        pick_rank = PICK_READINESS_RANKS["not_applicable"]
        if status == OutboundStatus.PENDING.value:
            pick_rank = PICK_READINESS_RANKS[
                "short_stock" if index % 3 == 0 else "ready_to_allocate"
            ]
        elif status == OutboundStatus.ALLOCATED.value:
            pick_rank = PICK_READINESS_RANKS["ready_to_release"]
        elif status == OutboundStatus.PICKING.value:
            pick_rank = PICK_READINESS_RANKS["pick_tasks_released"]
        elif status == OutboundStatus.PICKED.value:
            pick_rank = PICK_READINESS_RANKS["ready_to_pack"]
        elif status == OutboundStatus.PACKED.value:
            pick_rank = PICK_READINESS_RANKS["ready_to_ship"]
        elif status == OutboundStatus.SHIPPED.value:
            pick_rank = PICK_READINESS_RANKS["shipped"]
        objects.extend(
            [
                OutboundOrder(
                    id=order_id,
                    tenant_id=TENANT_ID,
                    client_id=_client_id(client_index),
                    warehouse_id=_warehouse_id(warehouse_index),
                    order_number=f"PERF-OUT-{index:06d}",
                    reference_number=f"POUT-{index:06d}",
                    status=status,
                    carrier=carrier,
                    tracking_number=tracking,
                    pick_readiness_rank=pick_rank,
                    shipping_readiness_rank=shipping_readiness_rank_from_values(
                        status,
                        carrier,
                        tracking,
                    ),
                    required_ship_date=created_at + timedelta(days=2),
                    shipped_date=created_at if status == OutboundStatus.SHIPPED.value else None,
                    created_at=created_at,
                ),
                OutboundOrderLine(
                    id=line_id,
                    tenant_id=TENANT_ID,
                    order_id=order_id,
                    sku_id=_sku_id(sku_index),
                    quantity_ordered=2 + (index % 12),
                    quantity_allocated=2 if status != OutboundStatus.PENDING.value else 0,
                    quantity_picked=2
                    if status in {"picked", "packing", "packed", "shipped"}
                    else 0,
                    quantity_shipped=2 if status == OutboundStatus.SHIPPED.value else 0,
                    pick_location_id=_storage_location_id(pick_location_index),
                ),
            ]
        )

    for index in range(args.tasks):
        task_type = TaskType.PUTAWAY.value if index % 2 == 0 else TaskType.PICK.value
        status = TaskStatus.PENDING.value if index % 5 != 0 else TaskStatus.COMPLETED.value
        reference_count = args.inbound_orders if task_type == TaskType.PUTAWAY.value else args.outbound_orders
        reference_index = index % max(1, reference_count)
        warehouse_index = _warehouse_index_for_record(
            reference_index,
            args,
            salt=71 if task_type == TaskType.PUTAWAY.value else 89,
        )
        source_location_index = _storage_index_for_warehouse(index, warehouse_index, args)
        destination_location_index = _storage_index_for_warehouse(index * 7, warehouse_index, args)
        staging_index = _staging_index_for_warehouse(index, warehouse_index)
        created_at = datetime.now(UTC) - timedelta(days=index % 45, minutes=index % 1440)
        objects.append(
            Task(
                id=f"perf-task-{index:06d}",
                tenant_id=TENANT_ID,
                warehouse_id=_warehouse_id(warehouse_index),
                task_type=task_type,
                status=status,
                priority=1 + (index % 10),
                sku_id=_sku_id(_sku_index_for_record(index, args, salt=97)),
                quantity=1 + (index % 20),
                source_location_id=_staging_location_id(staging_index)
                if task_type == TaskType.PUTAWAY.value
                else _storage_location_id(source_location_index),
                destination_location_id=_storage_location_id(destination_location_index)
                if task_type == TaskType.PUTAWAY.value
                else None,
                reference_type="inbound_order"
                if task_type == TaskType.PUTAWAY.value
                else "outbound_order",
                reference_id=f"perf-inbound-{reference_index:06d}"
                if task_type == TaskType.PUTAWAY.value
                else f"perf-outbound-{reference_index:06d}",
                completed_at=created_at if status == TaskStatus.COMPLETED.value else None,
                created_at=created_at,
            )
        )
    return objects


def _build_billing(args: argparse.Namespace) -> list[object]:
    objects: list[object] = []
    today = date.today()
    for client_index in range(args.clients):
        objects.append(
            RateCard(
                id=f"perf-rate-card-{client_index:03d}",
                tenant_id=TENANT_ID,
                client_id=_client_id(client_index),
                name=f"Performance Rate Card {client_index:03d}",
                effective_from=today - timedelta(days=90),
                rules={"storage_per_unit_day": 0.01, "pick_per_order": 2.5},
                is_active=True,
            )
        )

    for index in range(args.invoices):
        client_index = _client_index_for_record(index, args, salt=103)
        period_id = f"perf-period-{index:06d}"
        objects.extend(
            [
                BillingPeriod(
                    id=period_id,
                    tenant_id=TENANT_ID,
                    client_id=_client_id(client_index),
                    period_start=today - timedelta(days=30),
                    period_end=today - timedelta(days=1),
                    status="invoiced",
                ),
                BillingLineItem(
                    id=f"perf-billing-line-{index:06d}",
                    tenant_id=TENANT_ID,
                    billing_period_id=period_id,
                    charge_type="storage",
                    description="Performance storage charge",
                    quantity=100 + index,
                    unit_price=0.05,
                    total_amount=5 + index,
                    extra_data={"performance_fixture": True},
                ),
                Invoice(
                    id=f"perf-invoice-{index:06d}",
                    tenant_id=TENANT_ID,
                    client_id=_client_id(client_index),
                    billing_period_id=period_id,
                    invoice_number=f"PERF-INV-{index:06d}",
                    status=["draft", "sent", "paid", "overdue"][index % 4],
                    subtotal=100 + index,
                    tax_amount=0,
                    total_amount=100 + index,
                    issued_date=today - timedelta(days=index % 60),
                    due_date=today + timedelta(days=14 - (index % 28)),
                ),
            ]
        )
    return objects


async def _insert_batches(objects: list[object], batch_size: int = 1000) -> None:
    remaining_objects = list(objects)

    async with async_session_factory() as session:
        for model in INSERT_ORDER:
            matching = [obj for obj in remaining_objects if isinstance(obj, model)]
            if not matching:
                continue
            remaining_objects = [obj for obj in remaining_objects if not isinstance(obj, model)]
            for start in range(0, len(matching), batch_size):
                session.add_all(matching[start : start + batch_size])
                await session.flush()
        for start in range(0, len(remaining_objects), batch_size):
            session.add_all(remaining_objects[start : start + batch_size])
            await session.flush()
        await session.commit()


async def _refresh_statistics() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE"))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-seed", action="store_true", help="Required safety flag.")
    parser.add_argument("--replace", action="store_true", help="Delete and rebuild PERFSEED first.")
    parser.add_argument(
        "--allow-non-neon", action="store_true", help="Allow local/non-Neon staging DBs."
    )
    parser.add_argument(
        "--profile",
        choices=["uniform", "production-like"],
        default="uniform",
        help="Data distribution profile. production-like uses deterministic skew.",
    )
    parser.add_argument("--warehouses", type=int, default=1)
    parser.add_argument("--clients", type=int, default=8)
    parser.add_argument("--skus", type=int, default=240)
    parser.add_argument("--locations", type=int, default=800)
    parser.add_argument("--inventory", type=int, default=5000)
    parser.add_argument("--inbound-orders", type=int, default=1200)
    parser.add_argument("--outbound-orders", type=int, default=2400)
    parser.add_argument("--tasks", type=int, default=1600)
    parser.add_argument("--invoices", type=int, default=300)
    args = parser.parse_args()

    if not args.confirm_seed:
        raise SystemExit("Pass --confirm-seed to create staging performance data.")
    if args.warehouses < 1:
        raise SystemExit("--warehouses must be at least 1.")
    if args.clients < 1:
        raise SystemExit("--clients must be at least 1.")
    if args.skus < 1:
        raise SystemExit("--skus must be at least 1.")
    if args.locations < args.warehouses:
        raise SystemExit("--locations must be at least --warehouses.")
    _require_safe_target(args.allow_non_neon)
    await _ensure_empty_or_replace(args.replace)

    objects = []
    objects.extend(_build_master_data(args))
    objects.extend(_build_inventory(args))
    objects.extend(_build_inbound(args))
    objects.extend(_build_outbound_and_tasks(args))
    objects.extend(_build_billing(args))
    await _insert_batches(objects)
    await _refresh_statistics()

    print(f"DATABASE_URL driver: {settings.DATABASE_URL.split(':', 1)[0]}")
    print(f"Seed tenant: {TENANT_CODE} ({TENANT_ID})")
    print(
        "Inserted: "
        f"profile={args.profile}, {args.warehouses} warehouses, "
        f"{args.clients} clients, {args.skus} SKUs, "
        f"{args.locations + args.warehouses * STAGING_LOCATIONS_PER_WAREHOUSE} locations, "
        f"{args.inventory} inventory rows, {args.inbound_orders} inbound orders, "
        f"{args.outbound_orders} outbound orders, {args.tasks} tasks, {args.invoices} invoices"
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
