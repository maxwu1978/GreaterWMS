"""Order management endpoints — inbound and outbound."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import client_scope_filter, require_permission, require_role
from app.core.security import TokenPayload, UserPermission, UserRole
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
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.warehouse import Warehouse
from app.services.csv_import import load_csv_rows, parse_mapping, suggest_mapping
from app.services.outbound_readiness import (
    pick_readiness_from_summary,
    pick_readiness_rank,
    refresh_outbound_readiness_projection,
    shipping_readiness_rank_from_values,
)
from app.services.outbound_readiness import (
    refresh_outbound_readiness_projections as refresh_outbound_readiness_projection_batch,
)
from app.services.putaway_execution_service import PutawayExecutionService
from app.services.receiving_service import ReceivingService

router = APIRouter()

ORDER_LIST_DEFAULT_LIMIT = 100
ORDER_LIST_MAX_LIMIT = 500
ORDER_LIST_SORT_DIRECTIONS = {"asc", "desc"}
INBOUND_LIST_LIFECYCLES = {"all", "active", "archived", "voided", "completed"}
INBOUND_LIST_OPERATIONS = {
    "needs_action",
    "supervisor_review",
    "package_open",
    "putaway_pending",
    "print_pending",
    "prebooked",
    "dock_created",
    "recently_changed",
}
INBOUND_RECEIVING_STAGE_STATUSES = {
    InboundStatus.EXPECTED.value,
    InboundStatus.ARRIVED.value,
    InboundStatus.RECEIVING.value,
}
INBOUND_OPEN_PACKAGE_STATUSES = {
    InboundPackageStatus.EXPECTED.value,
    InboundPackageStatus.RECEIVING.value,
    InboundPackageStatus.RECEIVED.value,
    InboundPackageStatus.STAGED.value,
}

REQUIRED_OUTBOUND_FIELDS = [
    "order_number",
    "client_code",
    "warehouse_code",
    "sku_code",
    "quantity",
]
OPTIONAL_OUTBOUND_FIELDS = [
    "reference_number",
    "carrier",
]
OUTBOUND_IMPORT_ALIASES = {
    "order_number": [
        "order_number",
        "sales_order",
        "so_number",
        "so",
        "outbound_order",
        "shipment_order",
    ],
    "client_code": ["client_code", "customer_code", "customer", "client", "account_code"],
    "warehouse_code": [
        "warehouse_code",
        "warehouse",
        "site_code",
        "site",
        "facility",
        "facility_code",
    ],
    "sku_code": [
        "sku_code",
        "sku",
        "sku_no",
        "item",
        "item_no",
        "item_number",
        "item_code",
        "product_code",
        "part_number",
    ],
    "quantity": ["quantity", "qty", "qty_ordered", "ordered_qty", "units", "pieces"],
    "reference_number": [
        "reference_number",
        "reference",
        "customer_reference",
        "customer_ref",
        "external_reference",
        "sales_reference",
    ],
    "carrier": ["carrier", "ship_via", "shipping_carrier", "service_carrier"],
}


class InboundOrderResponse(BaseModel):
    id: str
    client_id: str
    warehouse_id: str
    order_number: str
    status: str
    reference_number: str | None
    archived: bool = False
    voided: bool = False
    can_delete: bool = False
    can_void: bool = False
    can_archive: bool = False
    total_packages: int = 0
    packages_open: int = 0
    packages_putaway_pending: int = 0
    packages_stored: int = 0
    packages_needing_action: int = 0
    packages_prebooked: int = 0
    packages_dock_created: int = 0
    supervisor_review_needed: bool = False
    internal_labels_total: int = 0
    internal_labels_print_pending: int = 0
    latest_activity_at: str | None = None


class ArchiveInboundRequest(BaseModel):
    archived: bool = True


class OutboundOrderResponse(BaseModel):
    id: str
    client_id: str
    warehouse_id: str
    order_number: str
    status: str
    reference_number: str | None
    carrier: str | None
    tracking_number: str | None
    total_items: int = 0
    total_allocated: int = 0
    total_picked: int = 0
    pick_shortage_units: int = 0
    pick_readiness: str = "not_applicable"


class OutboundReadinessRefreshRequest(BaseModel):
    tenant_id: str | None = Field(
        default=None,
        description="Platform admins may target a tenant; tenant users always use their own tenant.",
    )
    warehouse_id: str | None = None
    order_id: str | None = None
    statuses: list[str] | None = None
    dry_run: bool = True
    limit: int = Field(default=500, ge=1, le=2000)


class OutboundReadinessChangeResponse(BaseModel):
    order_id: str
    order_number: str
    status: str
    pick_readiness: str
    old_pick_rank: int
    new_pick_rank: int
    old_shipping_rank: int
    new_shipping_rank: int


class OutboundReadinessRefreshResponse(BaseModel):
    tenant_id: str
    scanned_orders: int
    updated_orders: int
    unchanged_orders: int
    dry_run: bool
    changes: list[OutboundReadinessChangeResponse]


class OutboundOrderLineInput(BaseModel):
    sku_id: str
    quantity: int


class CreateOutboundRequest(BaseModel):
    client_id: str
    warehouse_id: str
    order_number: str
    reference_number: str | None = None
    carrier: str | None = None
    lines: list[OutboundOrderLineInput]


def _set_order_list_pagination_headers(
    response: Response,
    *,
    offset: int,
    limit: int,
    returned_count: int,
    has_more: bool,
) -> None:
    response.headers["X-Offset"] = str(offset)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Returned-Count"] = str(returned_count)
    response.headers["X-Has-More"] = "true" if has_more else "false"


def _split_csv_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _inbound_extra_flag(key: str):
    return func.coalesce(InboundOrder.extra_data[key].as_boolean(), False)


def _inbound_package_exists(tenant_id: str, *criteria):
    return (
        select(InboundPackage.id)
        .where(
            InboundPackage.tenant_id == tenant_id,
            InboundPackage.order_id == InboundOrder.id,
            *criteria,
        )
        .exists()
    )


def _inbound_print_pending_exists(tenant_id: str):
    return (
        select(ReceivingLabel.id)
        .where(
            ReceivingLabel.tenant_id == tenant_id,
            ReceivingLabel.order_id == InboundOrder.id,
            ReceivingLabel.status == "received",
            func.coalesce(ReceivingLabel.extra_data["print_count"].as_integer(), 0) <= 0,
        )
        .exists()
    )


def _inbound_recent_activity_exists(tenant_id: str, recent_cutoff: datetime):
    return or_(
        InboundOrder.updated_at >= recent_cutoff,
        _inbound_package_exists(tenant_id, InboundPackage.updated_at >= recent_cutoff),
        (
            select(ReceivingLabel.id)
            .where(
                ReceivingLabel.tenant_id == tenant_id,
                ReceivingLabel.order_id == InboundOrder.id,
                ReceivingLabel.updated_at >= recent_cutoff,
            )
            .exists()
        ),
    )


def _inbound_operation_expression(tenant_id: str, operation: str, recent_hours: int):
    package_open = _inbound_package_exists(
        tenant_id,
        InboundPackage.status.in_(INBOUND_OPEN_PACKAGE_STATUSES),
    )
    putaway_pending = _inbound_package_exists(
        tenant_id,
        InboundPackage.status == InboundPackageStatus.PUTAWAY_PENDING.value,
    )
    print_pending = _inbound_print_pending_exists(tenant_id)
    prebooked = _inbound_package_exists(
        tenant_id,
        or_(
            InboundOrder.received_date.is_(None),
            InboundPackage.created_at <= InboundOrder.received_date,
        ),
    )
    dock_created = _inbound_package_exists(
        tenant_id,
        InboundOrder.received_date.is_not(None),
        InboundPackage.created_at > InboundOrder.received_date,
    )

    if operation == "needs_action":
        return or_(package_open, putaway_pending, print_pending)
    if operation == "supervisor_review":
        return prebooked & dock_created & or_(package_open, putaway_pending, print_pending)
    if operation == "package_open":
        return package_open
    if operation == "putaway_pending":
        return putaway_pending
    if operation == "print_pending":
        return print_pending
    if operation == "prebooked":
        return prebooked
    if operation == "dock_created":
        return dock_created
    if operation == "recently_changed":
        bounded_hours = min(max(recent_hours, 1), 24 * 14)
        recent_cutoff = datetime.now(UTC) - timedelta(hours=bounded_hours)
        return _inbound_recent_activity_exists(tenant_id, recent_cutoff)

    raise HTTPException(status_code=400, detail="Unsupported inbound operation filter")


_INBOUND_STATUS_PRIORITY = {
    InboundStatus.RECEIVING.value: 60,
    InboundStatus.ARRIVED.value: 50,
    InboundStatus.EXPECTED.value: 40,
    InboundStatus.PUTAWAY.value: 30,
    InboundStatus.DRAFT.value: 20,
    InboundStatus.COMPLETED.value: 10,
    InboundStatus.CANCELLED.value: 0,
}


async def _sync_putaway_state(db: AsyncSession, tenant_id: str, order: InboundOrder) -> None:
    if order.status != InboundStatus.PUTAWAY.value:
        return

    existing_tasks = await db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.tenant_id == tenant_id,
            Task.reference_type == "inbound_order",
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
            Task.status != TaskStatus.CANCELLED.value,
        )
    )
    if existing_tasks:
        return

    line_result = await db.execute(
        select(InboundOrderLine).where(
            InboundOrderLine.tenant_id == tenant_id,
            InboundOrderLine.order_id == order.id,
        )
    )
    lines = line_result.scalars().all()

    created_any = False
    any_received = False
    execution_service = PutawayExecutionService(db, tenant_id)
    for line in lines:
        good_qty = max(0, (line.quantity_received or 0) - (line.quantity_damaged or 0))
        if good_qty > 0:
            any_received = True
        if good_qty <= 0 or not line.staging_location_id:
            continue

        inventory_qty = await db.scalar(
            select(func.coalesce(func.sum(Inventory.quantity_on_hand), 0)).where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == order.warehouse_id,
                Inventory.location_id == line.staging_location_id,
                Inventory.sku_id == line.sku_id,
            )
        )
        if not inventory_qty or inventory_qty <= 0:
            continue

        db.add(
            Task(
                tenant_id=tenant_id,
                warehouse_id=order.warehouse_id,
                task_type=TaskType.PUTAWAY.value,
                status=TaskStatus.PENDING.value,
                priority=5,
                sku_id=line.sku_id,
                quantity=min(good_qty, int(inventory_qty)),
                execution_mode=(
                    await execution_service.decide(
                        warehouse_id=order.warehouse_id,
                        source_location_id=line.staging_location_id,
                        handling_unit_id=None,
                    )
                ).mode,
                source_location_id=line.staging_location_id,
                reference_type="inbound_order",
                reference_id=order.id,
                assigned_type=AssignedType.UNASSIGNED.value,
            )
        )
        created_any = True

    if created_any:
        await db.flush()
        return

    if any_received:
        order.status = InboundStatus.RECEIVING.value
        await db.flush()


def _dedupe_inbound_orders(orders: list[InboundOrder]) -> list[InboundOrder]:
    grouped: dict[tuple[str, str], InboundOrder] = {}
    for order in orders:
        key = (order.warehouse_id, order.order_number)
        current = grouped.get(key)
        if not current:
            grouped[key] = order
            continue

        current_priority = _INBOUND_STATUS_PRIORITY.get(current.status, 0)
        candidate_priority = _INBOUND_STATUS_PRIORITY.get(order.status, 0)
        if candidate_priority > current_priority:
            grouped[key] = order
            continue
        if candidate_priority == current_priority and (order.created_at or order.updated_at) > (
            current.created_at or current.updated_at
        ):
            grouped[key] = order

    deduped: list[InboundOrder] = []
    emitted: set[tuple[str, str]] = set()
    for order in orders:
        key = (order.warehouse_id, order.order_number)
        if key in emitted or grouped.get(key) is not order:
            continue
        deduped.append(order)
        emitted.add(key)
    return deduped


async def _inbound_lifecycle_flags(
    db: AsyncSession, tenant_id: str, order: InboundOrder
) -> dict[str, bool]:
    archived = bool((order.extra_data or {}).get("archived", False))
    voided = bool((order.extra_data or {}).get("voided", False))
    lines_result = await db.execute(
        select(InboundOrderLine).where(
            InboundOrderLine.tenant_id == tenant_id,
            InboundOrderLine.order_id == order.id,
        )
    )
    lines = lines_result.scalars().all()
    has_received_quantities = any(
        (line.quantity_received or 0) > 0 or (line.quantity_damaged or 0) > 0 for line in lines
    )
    has_observed_codes = bool(
        await db.scalar(
            select(ReceivingObservedCode.id).where(
                ReceivingObservedCode.tenant_id == tenant_id,
                ReceivingObservedCode.order_id == order.id,
            )
        )
    )
    has_internal_labels = bool(
        await db.scalar(
            select(ReceivingLabel.id).where(
                ReceivingLabel.tenant_id == tenant_id,
                ReceivingLabel.order_id == order.id,
            )
        )
    )
    has_handling_units = bool(
        await db.scalar(
            select(HandlingUnit.id).where(
                HandlingUnit.tenant_id == tenant_id,
                HandlingUnit.order_id == order.id,
            )
        )
    )
    has_inventory_transactions = bool(
        await db.scalar(
            select(InventoryTransaction.id).where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.reference_type == "inbound_order",
                InventoryTransaction.reference_id == order.id,
            )
        )
    )
    has_tasks = bool(
        await db.scalar(
            select(Task.id).where(
                Task.tenant_id == tenant_id,
                Task.reference_type == "inbound_order",
                Task.reference_id == order.id,
            )
        )
    )
    has_confirmed_activity = (
        has_received_quantities
        or has_internal_labels
        or has_handling_units
        or has_inventory_transactions
        or has_tasks
    )
    can_delete = (
        order.status
        in {InboundStatus.DRAFT.value, InboundStatus.EXPECTED.value, InboundStatus.CANCELLED.value}
        and not has_observed_codes
        and not has_confirmed_activity
    )
    can_void = (
        order.status
        in {
            InboundStatus.DRAFT.value,
            InboundStatus.EXPECTED.value,
            InboundStatus.ARRIVED.value,
            InboundStatus.RECEIVING.value,
        }
        and not has_confirmed_activity
    )
    can_archive = order.status != InboundStatus.RECEIVING.value
    return {
        "archived": archived,
        "voided": voided,
        "can_delete": can_delete,
        "can_void": can_void,
        "can_archive": can_archive,
    }


async def _inbound_operational_summary(
    db: AsyncSession, tenant_id: str, order: InboundOrder
) -> dict[str, int]:
    package_result = await db.execute(
        select(InboundPackage).where(
            InboundPackage.tenant_id == tenant_id,
            InboundPackage.order_id == order.id,
        )
    )
    packages = package_result.scalars().all()

    label_result = await db.execute(
        select(ReceivingLabel).where(
            ReceivingLabel.tenant_id == tenant_id,
            ReceivingLabel.order_id == order.id,
        )
    )
    labels = label_result.scalars().all()

    def infer_origin(package: InboundPackage) -> str:
        if order.received_date and package.created_at:
            received_reference = (
                order.received_date
                if order.received_date.tzinfo
                else order.received_date.replace(tzinfo=UTC)
            )
            created_reference = (
                package.created_at
                if package.created_at.tzinfo
                else package.created_at.replace(tzinfo=UTC)
            )
            if created_reference > received_reference:
                return "dock_created"
        return "prebooked"

    packages_open = sum(
        1
        for package in packages
        if package.status in {"expected", "receiving", "received", "staged"}
    )
    packages_putaway_pending = sum(1 for package in packages if package.status == "putaway_pending")
    packages_stored = sum(1 for package in packages if package.status == "stored")
    packages_prebooked = sum(1 for package in packages if infer_origin(package) == "prebooked")
    packages_dock_created = sum(
        1 for package in packages if infer_origin(package) == "dock_created"
    )
    internal_labels_print_pending = sum(
        1
        for label in labels
        if label.status == "received" and int((label.extra_data or {}).get("print_count", 0)) <= 0
    )
    mixed_package_origin = packages_prebooked > 0 and packages_dock_created > 0
    supervisor_review_needed = mixed_package_origin and (
        packages_open > 0 or packages_putaway_pending > 0 or internal_labels_print_pending > 0
    )

    def _normalize_timestamp(value: datetime | None) -> datetime | None:
        if not value:
            return None
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    latest_activity = _normalize_timestamp(order.updated_at or order.created_at)
    for package in packages:
        package_timestamp = _normalize_timestamp(
            getattr(package, "updated_at", None) or getattr(package, "created_at", None)
        )
        if package_timestamp and (latest_activity is None or package_timestamp > latest_activity):
            latest_activity = package_timestamp
    for label in labels:
        label_timestamp = _normalize_timestamp(
            getattr(label, "updated_at", None) or getattr(label, "created_at", None)
        )
        if label_timestamp and (latest_activity is None or label_timestamp > latest_activity):
            latest_activity = label_timestamp

    return {
        "total_packages": len(packages),
        "packages_open": packages_open,
        "packages_putaway_pending": packages_putaway_pending,
        "packages_stored": packages_stored,
        "packages_needing_action": packages_open + packages_putaway_pending,
        "packages_prebooked": packages_prebooked,
        "packages_dock_created": packages_dock_created,
        "supervisor_review_needed": supervisor_review_needed,
        "internal_labels_total": len(labels),
        "internal_labels_print_pending": internal_labels_print_pending,
        "latest_activity_at": latest_activity.isoformat() if latest_activity else None,
    }


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if not value:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _infer_inbound_package_origin(order: InboundOrder, package: InboundPackage) -> str:
    if order.received_date and package.created_at:
        received_reference = _normalize_timestamp(order.received_date)
        created_reference = _normalize_timestamp(package.created_at)
        if received_reference and created_reference and created_reference > received_reference:
            return "dock_created"
    return "prebooked"


async def _build_inbound_order_list_metadata(
    db: AsyncSession, tenant_id: str, orders: list[InboundOrder]
) -> dict[str, dict]:
    order_ids = [order.id for order in orders]
    if not order_ids:
        return {}

    metadata: dict[str, dict[str, Any]] = {
        order.id: {
            "archived": bool((order.extra_data or {}).get("archived", False)),
            "voided": bool((order.extra_data or {}).get("voided", False)),
            "can_delete": False,
            "can_void": False,
            "can_archive": order.status != InboundStatus.RECEIVING.value,
            "total_packages": 0,
            "packages_open": 0,
            "packages_putaway_pending": 0,
            "packages_stored": 0,
            "packages_needing_action": 0,
            "packages_prebooked": 0,
            "packages_dock_created": 0,
            "supervisor_review_needed": False,
            "internal_labels_total": 0,
            "internal_labels_print_pending": 0,
            "latest_activity_at": None,
        }
        for order in orders
    }
    order_by_id = {order.id: order for order in orders}
    latest_activity = {
        order.id: _normalize_timestamp(order.updated_at or order.created_at) for order in orders
    }

    lines_result = await db.execute(
        select(
            InboundOrderLine.order_id,
            InboundOrderLine.quantity_received,
            InboundOrderLine.quantity_damaged,
        ).where(
            InboundOrderLine.tenant_id == tenant_id,
            InboundOrderLine.order_id.in_(order_ids),
        )
    )
    orders_with_received_quantities: set[str] = set()
    for order_id, quantity_received, quantity_damaged in lines_result.all():
        if (quantity_received or 0) > 0 or (quantity_damaged or 0) > 0:
            orders_with_received_quantities.add(order_id)

    observed_result = await db.execute(
        select(ReceivingObservedCode.order_id).where(
            ReceivingObservedCode.tenant_id == tenant_id,
            ReceivingObservedCode.order_id.in_(order_ids),
        )
    )
    orders_with_observed_codes = set(observed_result.scalars().all())

    handling_unit_result = await db.execute(
        select(HandlingUnit.order_id).where(
            HandlingUnit.tenant_id == tenant_id,
            HandlingUnit.order_id.in_(order_ids),
        )
    )
    orders_with_handling_units = set(handling_unit_result.scalars().all())

    inventory_tx_result = await db.execute(
        select(InventoryTransaction.reference_id).where(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.reference_type == "inbound_order",
            InventoryTransaction.reference_id.in_(order_ids),
        )
    )
    orders_with_inventory_transactions = set(inventory_tx_result.scalars().all())

    task_result = await db.execute(
        select(Task.reference_id).where(
            Task.tenant_id == tenant_id,
            Task.reference_type == "inbound_order",
            Task.reference_id.in_(order_ids),
        )
    )
    orders_with_tasks = set(task_result.scalars().all())

    package_result = await db.execute(
        select(InboundPackage).where(
            InboundPackage.tenant_id == tenant_id,
            InboundPackage.order_id.in_(order_ids),
        )
    )
    package_origin_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"prebooked": 0, "dock_created": 0}
    )
    for package in package_result.scalars().all():
        order = order_by_id.get(package.order_id)
        order_metadata = metadata.get(package.order_id)
        if not order or not order_metadata:
            continue

        order_metadata["total_packages"] += 1
        if package.status in {"expected", "receiving", "received", "staged"}:
            order_metadata["packages_open"] += 1
        elif package.status == "putaway_pending":
            order_metadata["packages_putaway_pending"] += 1
        elif package.status == "stored":
            order_metadata["packages_stored"] += 1

        origin = _infer_inbound_package_origin(order, package)
        package_origin_counts[package.order_id][origin] += 1

        package_timestamp = _normalize_timestamp(package.updated_at or package.created_at)
        current_latest = latest_activity.get(package.order_id)
        if package_timestamp and (current_latest is None or package_timestamp > current_latest):
            latest_activity[package.order_id] = package_timestamp

    label_result = await db.execute(
        select(ReceivingLabel).where(
            ReceivingLabel.tenant_id == tenant_id,
            ReceivingLabel.order_id.in_(order_ids),
        )
    )
    orders_with_internal_labels: set[str] = set()
    for label in label_result.scalars().all():
        order_metadata = metadata.get(label.order_id)
        if not order_metadata:
            continue

        orders_with_internal_labels.add(label.order_id)
        order_metadata["internal_labels_total"] += 1
        try:
            print_count = int((label.extra_data or {}).get("print_count", 0) or 0)
        except (TypeError, ValueError):
            print_count = 0
        if label.status == "received" and print_count <= 0:
            order_metadata["internal_labels_print_pending"] += 1

        label_timestamp = _normalize_timestamp(label.updated_at or label.created_at)
        current_latest = latest_activity.get(label.order_id)
        if label_timestamp and (current_latest is None or label_timestamp > current_latest):
            latest_activity[label.order_id] = label_timestamp

    for order in orders:
        order_metadata = metadata[order.id]
        origin_counts = package_origin_counts[order.id]
        order_metadata["packages_prebooked"] = origin_counts["prebooked"]
        order_metadata["packages_dock_created"] = origin_counts["dock_created"]
        order_metadata["packages_needing_action"] = (
            order_metadata["packages_open"] + order_metadata["packages_putaway_pending"]
        )
        mixed_package_origin = (
            order_metadata["packages_prebooked"] > 0
            and order_metadata["packages_dock_created"] > 0
        )
        order_metadata["supervisor_review_needed"] = mixed_package_origin and (
            order_metadata["packages_open"] > 0
            or order_metadata["packages_putaway_pending"] > 0
            or order_metadata["internal_labels_print_pending"] > 0
        )

        has_confirmed_activity = (
            order.id in orders_with_received_quantities
            or order.id in orders_with_internal_labels
            or order.id in orders_with_handling_units
            or order.id in orders_with_inventory_transactions
            or order.id in orders_with_tasks
        )
        order_metadata["can_delete"] = (
            order.status
            in {InboundStatus.DRAFT.value, InboundStatus.EXPECTED.value, InboundStatus.CANCELLED.value}
            and order.id not in orders_with_observed_codes
            and not has_confirmed_activity
        )
        order_metadata["can_void"] = (
            order.status
            in {
                InboundStatus.DRAFT.value,
                InboundStatus.EXPECTED.value,
                InboundStatus.ARRIVED.value,
                InboundStatus.RECEIVING.value,
            }
            and not has_confirmed_activity
        )
        latest = latest_activity.get(order.id)
        order_metadata["latest_activity_at"] = latest.isoformat() if latest else None

    return metadata


def _suggest_mapping(headers: list[str]) -> dict[str, str]:
    return suggest_mapping(headers, OUTBOUND_IMPORT_ALIASES)


def _parse_mapping(mapping_json: str | dict[str, str] | None, headers: list[str]) -> dict[str, str]:
    return parse_mapping(
        mapping_json,
        headers,
        aliases=OUTBOUND_IMPORT_ALIASES,
        required_fields=REQUIRED_OUTBOUND_FIELDS,
        optional_fields=OPTIONAL_OUTBOUND_FIELDS,
    )


async def _create_outbound_order(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    order_number: str,
    lines: list[dict],
    reference_number: str | None = None,
    carrier: str | None = None,
) -> OutboundOrder:
    if not lines:
        raise ValueError("At least one outbound line is required")

    client = await db.scalar(
        select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id)
    )
    if not client:
        raise ValueError("Client not found")

    warehouse = await db.scalar(
        select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.tenant_id == tenant_id)
    )
    if not warehouse:
        raise ValueError("Warehouse not found")

    existing = await db.scalar(
        select(OutboundOrder).where(
            OutboundOrder.tenant_id == tenant_id,
            OutboundOrder.warehouse_id == warehouse_id,
            OutboundOrder.order_number == order_number,
        )
    )
    if existing:
        raise ValueError(f"Outbound order '{order_number}' already exists")

    sku_ids = [line["sku_id"] for line in lines]
    sku_result = await db.execute(
        select(SKU).where(
            SKU.tenant_id == tenant_id,
            SKU.client_id == client_id,
            SKU.id.in_(sku_ids),
        )
    )
    valid_skus = {sku.id for sku in sku_result.scalars()}
    missing_skus = [line["sku_id"] for line in lines if line["sku_id"] not in valid_skus]
    if missing_skus:
        raise ValueError("One or more outbound line items reference invalid SKUs for this client")

    order = OutboundOrder(
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number=order_number,
        reference_number=reference_number,
        carrier=carrier,
        status=OutboundStatus.PENDING.value,
    )
    db.add(order)
    await db.flush()

    for line in lines:
        quantity = int(line.get("quantity") or 0)
        if quantity <= 0:
            raise ValueError("Outbound quantities must be greater than zero")
        db.add(
            OutboundOrderLine(
                tenant_id=tenant_id,
                order_id=order.id,
                sku_id=line["sku_id"],
                quantity_ordered=quantity,
            )
        )

    await db.flush()
    await refresh_outbound_readiness_projection(db, tenant_id, order)
    return order


@router.get("/inbound", response_model=list[InboundOrderResponse])
async def list_inbound_orders(
    response: Response,
    warehouse_id: str | None = Query(None),
    status: str | None = Query(None),
    statuses: Annotated[str | None, Query()] = None,
    lifecycle: Annotated[str | None, Query()] = None,
    operation: Annotated[str | None, Query()] = None,
    include_archived: bool = Query(False),
    sort_by: Annotated[str, Query()] = "created_at",
    sort_direction: Annotated[str, Query()] = "desc",
    recent_hours: Annotated[int, Query(ge=1, le=336)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=ORDER_LIST_MAX_LIMIT)] = ORDER_LIST_DEFAULT_LIMIT,
    current_user: TokenPayload = Depends(
        require_role(
            UserRole.PLATFORM_ADMIN,
            UserRole.TENANT_ADMIN,
            UserRole.OPERATOR,
            UserRole.CLIENT_VIEWER,
        )
    ),
    db: AsyncSession = Depends(get_db_session),
):
    sort_direction = sort_direction.lower()
    if sort_direction not in ORDER_LIST_SORT_DIRECTIONS:
        raise HTTPException(status_code=400, detail="sort_direction must be asc or desc")

    lifecycle = lifecycle.lower() if lifecycle else None
    if lifecycle and lifecycle not in INBOUND_LIST_LIFECYCLES:
        raise HTTPException(status_code=400, detail="Unsupported inbound lifecycle filter")

    operation = operation.lower() if operation else None
    if operation and operation not in INBOUND_LIST_OPERATIONS:
        raise HTTPException(status_code=400, detail="Unsupported inbound operation filter")

    query = select(InboundOrder).where(InboundOrder.tenant_id == current_user.tenant_id)
    scoped_client_id = client_scope_filter(current_user)
    if scoped_client_id:
        query = query.where(InboundOrder.client_id == scoped_client_id)
    if warehouse_id:
        query = query.where(InboundOrder.warehouse_id == warehouse_id)

    archived_expr = _inbound_extra_flag("archived")
    voided_expr = _inbound_extra_flag("voided")
    if lifecycle == "active":
        query = query.where(
            InboundOrder.status.in_(INBOUND_RECEIVING_STAGE_STATUSES),
            archived_expr.is_(False),
            voided_expr.is_(False),
        )
    elif lifecycle == "archived":
        query = query.where(archived_expr.is_(True))
    elif lifecycle == "voided":
        query = query.where(voided_expr.is_(True))
        if not include_archived:
            query = query.where(archived_expr.is_(False))
    elif lifecycle == "completed":
        query = query.where(
            InboundOrder.status == InboundStatus.COMPLETED.value,
            archived_expr.is_(False),
            voided_expr.is_(False),
        )
    elif not include_archived:
        query = query.where(archived_expr.is_(False))

    requested_statuses = [status.strip()] if status and status.strip() else []
    requested_statuses.extend(_split_csv_values(statuses))
    requested_statuses = list(dict.fromkeys(requested_statuses))
    if requested_statuses:
        query = query.where(InboundOrder.status.in_(requested_statuses))

    if operation:
        query = query.where(
            archived_expr.is_(False),
            voided_expr.is_(False),
            _inbound_operation_expression(current_user.tenant_id, operation, recent_hours),
        )

    sort_map = {
        "created_at": InboundOrder.created_at,
        "order_number": InboundOrder.order_number,
        "status": InboundOrder.status,
        "client_id": Client.name,
    }
    if sort_by not in sort_map:
        raise HTTPException(status_code=400, detail="Unsupported inbound order sort field")
    if sort_by == "client_id":
        query = query.join(Client, Client.id == InboundOrder.client_id)

    sort_column = sort_map[sort_by]
    sort_expression = (
        sort_column.asc() if sort_direction == "asc" else sort_column.desc()
    )
    secondary_sort = (
        InboundOrder.created_at.desc()
        if sort_by != "created_at"
        else InboundOrder.order_number.asc()
    )

    result = await db.execute(
        query.order_by(sort_expression, secondary_sort).offset(offset).limit(limit + 1)
    )
    orders_page = result.scalars().all()
    has_more = len(orders_page) > limit
    orders = orders_page[:limit]
    orders = _dedupe_inbound_orders(orders)
    metadata_by_order_id = await _build_inbound_order_list_metadata(
        db, current_user.tenant_id, orders
    )
    payload: list[InboundOrderResponse] = []
    for order in orders:
        metadata = metadata_by_order_id[order.id]
        if metadata["archived"] and not include_archived:
            continue
        payload.append(
            InboundOrderResponse(
                id=order.id,
                client_id=order.client_id,
                warehouse_id=order.warehouse_id,
                order_number=order.order_number,
                status=order.status,
                reference_number=order.reference_number,
                archived=metadata["archived"],
                voided=metadata["voided"],
                can_delete=metadata["can_delete"],
                can_void=metadata["can_void"],
                can_archive=metadata["can_archive"],
                total_packages=metadata["total_packages"],
                packages_open=metadata["packages_open"],
                packages_putaway_pending=metadata["packages_putaway_pending"],
                packages_stored=metadata["packages_stored"],
                packages_needing_action=metadata["packages_needing_action"],
                packages_prebooked=metadata["packages_prebooked"],
                packages_dock_created=metadata["packages_dock_created"],
                supervisor_review_needed=metadata["supervisor_review_needed"],
                internal_labels_total=metadata["internal_labels_total"],
                internal_labels_print_pending=metadata["internal_labels_print_pending"],
                latest_activity_at=metadata["latest_activity_at"],
            )
        )
    _set_order_list_pagination_headers(
        response,
        offset=offset,
        limit=limit,
        returned_count=len(payload),
        has_more=has_more,
    )
    return payload


@router.post("/inbound/{order_id}/archive")
async def archive_inbound_order(
    order_id: str,
    body: ArchiveInboundRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.INBOUND_ORDERS_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    order = await svc.set_inbound_order_archived(order_id, body.archived, current_user.sub)
    flags = await _inbound_lifecycle_flags(db, current_user.tenant_id, order)
    return {"id": order.id, "status": order.status, **flags}


@router.post("/inbound/{order_id}/void")
async def void_inbound_order(
    order_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.INBOUND_ORDERS_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    order = await svc.void_inbound_order(order_id, current_user.sub)
    flags = await _inbound_lifecycle_flags(db, current_user.tenant_id, order)
    return {"id": order.id, "status": order.status, **flags}


@router.delete("/inbound/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbound_order(
    order_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.INBOUND_ORDERS_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    await svc.delete_inbound_order(order_id)


@router.get("/outbound", response_model=list[OutboundOrderResponse])
async def list_outbound_orders(
    response: Response,
    warehouse_id: str | None = Query(None),
    status: str | None = Query(None),
    statuses: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_direction: Annotated[str, Query()] = "desc",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=ORDER_LIST_MAX_LIMIT)] = ORDER_LIST_DEFAULT_LIMIT,
    current_user: TokenPayload = Depends(
        require_role(
            UserRole.PLATFORM_ADMIN,
            UserRole.TENANT_ADMIN,
            UserRole.OPERATOR,
            UserRole.CLIENT_VIEWER,
        )
    ),
    db: AsyncSession = Depends(get_db_session),
):
    sort_key = sort_by.strip().lower()
    direction = sort_direction.strip().lower()
    if direction not in ORDER_LIST_SORT_DIRECTIONS:
        raise HTTPException(status_code=400, detail="sort_direction must be asc or desc")

    order_filters: list[Any] = [OutboundOrder.tenant_id == current_user.tenant_id]
    scoped_client_id = client_scope_filter(current_user)
    if scoped_client_id:
        order_filters.append(OutboundOrder.client_id == scoped_client_id)
    if warehouse_id:
        order_filters.append(OutboundOrder.warehouse_id == warehouse_id)

    requested_statuses = [status.strip()] if status and status.strip() else []
    requested_statuses.extend(_split_csv_values(statuses))
    requested_statuses = list(dict.fromkeys(requested_statuses))
    if requested_statuses:
        order_filters.append(OutboundOrder.status.in_(requested_statuses))

    query = select(OutboundOrder).where(*order_filters)

    sort_columns = {
        "created_at": OutboundOrder.created_at,
        "order_number": OutboundOrder.order_number,
        "status": OutboundOrder.status,
        "carrier": OutboundOrder.carrier,
        "tracking_number": OutboundOrder.tracking_number,
        "client_id": Client.name,
        "pick_readiness": OutboundOrder.pick_readiness_rank,
        "shipping_readiness": OutboundOrder.shipping_readiness_rank,
    }
    sort_column = sort_columns.get(sort_key)
    if sort_column is None:
        raise HTTPException(status_code=400, detail="Unsupported outbound order sort field")
    if sort_key == "client_id":
        query = query.join(Client, Client.id == OutboundOrder.client_id)
    sort_expression = sort_column.asc() if direction == "asc" else sort_column.desc()
    secondary_sort = (
        OutboundOrder.created_at.desc()
        if sort_key != "created_at"
        else OutboundOrder.order_number.asc()
    )

    result = await db.execute(
        query.order_by(sort_expression, secondary_sort).offset(offset).limit(limit + 1)
    )
    orders_page = result.scalars().all()
    has_more = len(orders_page) > limit
    orders = orders_page[:limit]
    if not orders:
        _set_order_list_pagination_headers(
            response,
            offset=offset,
            limit=limit,
            returned_count=0,
            has_more=has_more,
        )
        return []

    order_ids = [order.id for order in orders]
    warehouse_ids = {order.warehouse_id for order in orders}

    line_result = await db.execute(
        select(OutboundOrderLine).where(
            OutboundOrderLine.tenant_id == current_user.tenant_id,
            OutboundOrderLine.order_id.in_(order_ids),
        )
    )
    lines_by_order: dict[str, list[OutboundOrderLine]] = defaultdict(list)
    sku_ids: set[str] = set()
    for line in line_result.scalars().all():
        lines_by_order[line.order_id].append(line)
        sku_ids.add(line.sku_id)

    available_by_warehouse_sku: dict[tuple[str, str], int] = defaultdict(int)
    if sku_ids and warehouse_ids:
        inventory_result = await db.execute(
            select(Inventory).where(
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.warehouse_id.in_(warehouse_ids),
                Inventory.sku_id.in_(sku_ids),
            )
        )
        for item in inventory_result.scalars().all():
            available_by_warehouse_sku[(item.warehouse_id, item.sku_id)] += max(
                0,
                (item.quantity_on_hand or 0)
                - (item.quantity_allocated or 0)
                - (item.quantity_damaged or 0),
            )

    def _pick_summary(order: OutboundOrder) -> dict:
        lines = lines_by_order.get(order.id, [])
        total_items = sum(line.quantity_ordered or 0 for line in lines)
        total_allocated = sum(line.quantity_allocated or 0 for line in lines)
        total_picked = sum(line.quantity_picked or 0 for line in lines)
        remaining_by_sku: dict[str, int] = defaultdict(int)
        for line in lines:
            remaining_by_sku[line.sku_id] += max(
                0, (line.quantity_ordered or 0) - (line.quantity_allocated or 0)
            )
        shortage_units = sum(
            max(
                0,
                needed - available_by_warehouse_sku.get((order.warehouse_id, sku_id), 0),
            )
            for sku_id, needed in remaining_by_sku.items()
        )

        readiness = pick_readiness_from_summary(order.status, total_items, shortage_units)

        return {
            "total_items": total_items,
            "total_allocated": total_allocated,
            "total_picked": total_picked,
            "pick_shortage_units": shortage_units
            if order.status == OutboundStatus.PENDING.value
            else 0,
            "pick_readiness": readiness,
        }

    payload: list[OutboundOrderResponse] = []
    projection_changed = False
    for order in orders:
        summary = _pick_summary(order)
        next_pick_rank = pick_readiness_rank(summary["pick_readiness"])
        next_shipping_rank = shipping_readiness_rank_from_values(
            order.status,
            order.carrier,
            order.tracking_number,
        )
        if (
            order.pick_readiness_rank != next_pick_rank
            or order.shipping_readiness_rank != next_shipping_rank
        ):
            order.pick_readiness_rank = next_pick_rank
            order.shipping_readiness_rank = next_shipping_rank
            projection_changed = True
        payload.append(
            OutboundOrderResponse(
                id=order.id,
                client_id=order.client_id,
                warehouse_id=order.warehouse_id,
                order_number=order.order_number,
                status=order.status,
                reference_number=order.reference_number,
                carrier=order.carrier,
                tracking_number=order.tracking_number,
                **summary,
            )
        )
    if projection_changed:
        await db.flush()
    _set_order_list_pagination_headers(
        response,
        offset=offset,
        limit=limit,
        returned_count=len(payload),
        has_more=has_more,
    )
    return payload


@router.post("/outbound/readiness/refresh", response_model=OutboundReadinessRefreshResponse)
async def refresh_outbound_readiness(
    body: OutboundReadinessRefreshRequest,
    current_user: TokenPayload = Depends(require_permission(UserPermission.MASTER_DATA_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = body.tenant_id if current_user.role == UserRole.PLATFORM_ADMIN else current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="A tenant scope is required for outbound readiness refresh",
        )

    requested_statuses = [status.strip() for status in body.statuses or [] if status.strip()]
    valid_statuses = {status.value for status in OutboundStatus}
    invalid_statuses = sorted(set(requested_statuses) - valid_statuses)
    if invalid_statuses:
        raise HTTPException(
            status_code=400,
            detail={"message": "Unsupported outbound statuses", "statuses": invalid_statuses},
        )

    stats = await refresh_outbound_readiness_projection_batch(
        db,
        tenant_id=tenant_id,
        warehouse_id=body.warehouse_id,
        order_id=body.order_id,
        statuses=requested_statuses or None,
        dry_run=body.dry_run,
        limit=body.limit,
    )
    return OutboundReadinessRefreshResponse(
        tenant_id=stats.tenant_id,
        scanned_orders=stats.scanned_orders,
        updated_orders=stats.updated_orders,
        unchanged_orders=stats.unchanged_orders,
        dry_run=stats.dry_run,
        changes=[
            OutboundReadinessChangeResponse(
                order_id=change.order_id,
                order_number=change.order_number,
                status=change.status,
                pick_readiness=change.pick_readiness,
                old_pick_rank=change.old_pick_rank,
                new_pick_rank=change.new_pick_rank,
                old_shipping_rank=change.old_shipping_rank,
                new_shipping_rank=change.new_shipping_rank,
            )
            for change in stats.changes[:100]
        ],
    )


@router.post("/outbound/import-csv/preview")
async def preview_outbound_orders_csv(
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.OUTBOUND_ORDERS_MANAGE.value)
    ),
):
    content = await file.read()
    headers, rows = load_csv_rows(file.filename, content)
    suggested_mapping = _suggest_mapping(headers)
    sample_rows = rows[:5]

    mapped_preview: list[dict[str, str]] = []
    for row in sample_rows:
        mapped_preview.append(
            {
                field: (row.get(header_name) or "").strip()
                for field, header_name in suggested_mapping.items()
            }
        )

    return {
        "headers": headers,
        "required_fields": REQUIRED_OUTBOUND_FIELDS,
        "optional_fields": OPTIONAL_OUTBOUND_FIELDS,
        "suggested_mapping": suggested_mapping,
        "missing_required": [
            field for field in REQUIRED_OUTBOUND_FIELDS if field not in suggested_mapping
        ],
        "sample_rows": sample_rows,
        "mapped_preview": mapped_preview,
        "total_rows": len(rows),
    }


@router.post("/outbound", status_code=status.HTTP_201_CREATED)
async def create_outbound_order(
    body: CreateOutboundRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.OUTBOUND_ORDERS_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        order = await _create_outbound_order(
            db=db,
            tenant_id=current_user.tenant_id,
            client_id=body.client_id,
            warehouse_id=body.warehouse_id,
            order_number=body.order_number,
            lines=[line.model_dump() for line in body.lines],
            reference_number=body.reference_number,
            carrier=body.carrier,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": order.id, "order_number": order.order_number, "status": order.status}


@router.post("/outbound/import-csv")
async def import_outbound_orders_csv(
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.OUTBOUND_ORDERS_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    content = await file.read()
    headers, rows = load_csv_rows(file.filename, content)
    field_mapping = _parse_mapping(mapping, headers)

    clients = {
        client.code: client
        for client in (
            await db.execute(select(Client).where(Client.tenant_id == current_user.tenant_id))
        ).scalars()
    }
    warehouses = {
        warehouse.code: warehouse
        for warehouse in (
            await db.execute(select(Warehouse).where(Warehouse.tenant_id == current_user.tenant_id))
        ).scalars()
    }
    skus = {
        sku.sku_code: sku
        for sku in (
            await db.execute(select(SKU).where(SKU.tenant_id == current_user.tenant_id))
        ).scalars()
    }

    grouped_rows: dict[str, dict] = {}
    errors: list[dict] = []

    for row_number, row in enumerate(rows, start=2):
        order_number = (row.get(field_mapping["order_number"]) or "").strip()
        client_code = (row.get(field_mapping["client_code"]) or "").strip()
        warehouse_code = (row.get(field_mapping["warehouse_code"]) or "").strip()
        sku_code = (row.get(field_mapping["sku_code"]) or "").strip()
        reference_header = field_mapping.get("reference_number")
        carrier_header = field_mapping.get("carrier")
        reference_number = (
            (row.get(reference_header) or "").strip() or None if reference_header else None
        )
        carrier = (row.get(carrier_header) or "").strip() or None if carrier_header else None

        try:
            quantity = int((row.get(field_mapping["quantity"]) or "").strip())
        except ValueError:
            quantity = 0

        if (
            not order_number
            or not client_code
            or not warehouse_code
            or not sku_code
            or quantity <= 0
        ):
            errors.append({"row": row_number, "error": "Missing required outbound CSV fields"})
            continue
        if client_code not in clients:
            errors.append({"row": row_number, "error": f"Client '{client_code}' not found"})
            continue
        if warehouse_code not in warehouses:
            errors.append({"row": row_number, "error": f"Warehouse '{warehouse_code}' not found"})
            continue
        if sku_code not in skus:
            errors.append({"row": row_number, "error": f"SKU '{sku_code}' not found"})
            continue

        order_bucket = grouped_rows.setdefault(
            order_number,
            {
                "client_id": clients[client_code].id,
                "warehouse_id": warehouses[warehouse_code].id,
                "reference_number": reference_number,
                "carrier": carrier,
                "lines": [],
            },
        )
        order_bucket["lines"].append({"sku_id": skus[sku_code].id, "quantity": quantity})

    imported = 0
    for order_number, payload in grouped_rows.items():
        try:
            await _create_outbound_order(
                db=db,
                tenant_id=current_user.tenant_id,
                client_id=payload["client_id"],
                warehouse_id=payload["warehouse_id"],
                order_number=order_number,
                lines=payload["lines"],
                reference_number=payload["reference_number"],
                carrier=payload["carrier"],
            )
            imported += 1
        except ValueError as exc:
            errors.append({"row": order_number, "error": str(exc)})

    await db.flush()
    return {
        "imported": imported,
        "errors": errors,
        "total_rows": len(rows),
        "mapping_used": field_mapping,
    }
