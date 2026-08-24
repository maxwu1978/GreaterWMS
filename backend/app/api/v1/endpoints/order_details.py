"""Order detail API — view line items, allocation status, full order lifecycle."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user
from app.core.security import TokenPayload, UserRole
from app.models.inventory import SKU
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    OutboundOrder,
    OutboundOrderLine,
    ReceivingLabel,
    ReceivingObservedCode,
)
from app.models.task import Task, TaskType
from app.models.warehouse import Location

router = APIRouter()


def _scoped_order_query(
    model: type[InboundOrder] | type[OutboundOrder], order_id: str, current_user: TokenPayload
):
    query = select(model).where(model.id == order_id)
    if current_user.role != UserRole.PLATFORM_ADMIN:
        query = query.where(model.tenant_id == current_user.tenant_id)
    return query


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _append_timeline_event(
    events: list[dict],
    occurred_at: datetime | None,
    event_type: str,
    title: str,
    detail: str | None = None,
):
    if not occurred_at:
        return
    events.append(
        {
            "occurred_at": _iso(occurred_at),
            "event_type": event_type,
            "title": title,
            "detail": detail,
        }
    )


def _infer_package_origin(
    received_date: datetime | None, package_created_at: datetime | None
) -> str:
    if received_date and package_created_at:
        received_reference = (
            received_date if received_date.tzinfo else received_date.replace(tzinfo=UTC)
        )
        created_reference = (
            package_created_at
            if package_created_at.tzinfo
            else package_created_at.replace(tzinfo=UTC)
        )
        if created_reference > received_reference:
            return "dock_created"
    return "prebooked"


@router.get("/outbound/{order_id}")
async def get_outbound_detail(
    order_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(_scoped_order_query(OutboundOrder, order_id, current_user))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    lines_result = await db.execute(
        select(OutboundOrderLine, SKU)
        .join(SKU, SKU.id == OutboundOrderLine.sku_id)
        .where(
            OutboundOrderLine.tenant_id == order.tenant_id,
            SKU.tenant_id == order.tenant_id,
            OutboundOrderLine.order_id == order_id,
        )
    )
    outbound_line_rows = lines_result.all()
    pick_location_ids = {
        line.pick_location_id for line, _sku in outbound_line_rows if line.pick_location_id
    }
    pick_location_barcodes: dict[str, str | None] = {}
    if pick_location_ids:
        lr = await db.execute(
            select(Location.id, Location.barcode).where(
                Location.tenant_id == order.tenant_id,
                Location.id.in_(pick_location_ids),
            )
        )
        pick_location_barcodes = {row.id: row.barcode for row in lr.all()}

    lines = []
    for line, sku in outbound_line_rows:
        loc_barcode = (
            pick_location_barcodes.get(line.pick_location_id) if line.pick_location_id else None
        )
        lines.append(
            {
                "line_id": line.id,
                "sku_id": line.sku_id,
                "sku_code": sku.sku_code,
                "sku_name": sku.name,
                "quantity_ordered": line.quantity_ordered,
                "quantity_allocated": line.quantity_allocated,
                "quantity_picked": line.quantity_picked,
                "quantity_shipped": line.quantity_shipped,
                "pick_location": loc_barcode,
                "fully_allocated": line.quantity_allocated >= line.quantity_ordered,
            }
        )

    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "client_id": order.client_id,
        "reference_number": order.reference_number,
        "channel": order.channel,
        "priority": order.priority,
        "ship_to_name": order.ship_to_name,
        "ship_to_address": order.ship_to_address,
        "carrier": order.carrier,
        "service_level": order.service_level,
        "tracking_number": order.tracking_number,
        "shipping_cost": float(order.shipping_cost) if order.shipping_cost else None,
        "shipped_date": _iso(order.shipped_date),
        "created_at": _iso(order.created_at),
        "lines": lines,
        "total_items": sum(line["quantity_ordered"] for line in lines),
        "total_allocated": sum(line["quantity_allocated"] for line in lines),
        "total_picked": sum(line["quantity_picked"] for line in lines),
        "fully_allocated": all(line["fully_allocated"] for line in lines),
    }


@router.get("/inbound/{order_id}")
async def get_inbound_detail(
    order_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(_scoped_order_query(InboundOrder, order_id, current_user))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    lines_result = await db.execute(
        select(InboundOrderLine, SKU)
        .join(SKU, SKU.id == InboundOrderLine.sku_id)
        .where(
            InboundOrderLine.tenant_id == order.tenant_id,
            SKU.tenant_id == order.tenant_id,
            InboundOrderLine.order_id == order_id,
        )
    )
    order_extra = order.extra_data or {}
    line_rows = lines_result.all()

    package_result = await db.execute(
        select(InboundPackage).where(
            InboundPackage.tenant_id == order.tenant_id,
            InboundPackage.order_id == order.id,
        )
    )
    packages_by_line: dict[str, list[InboundPackage]] = {}
    packages_by_id: dict[str, InboundPackage] = {}
    packages_all = package_result.scalars().all()
    for package in packages_all:
        packages_by_line.setdefault(package.order_line_id, []).append(package)
        packages_by_id[package.id] = package

    label_result = await db.execute(
        select(ReceivingLabel).where(
            ReceivingLabel.tenant_id == order.tenant_id,
            ReceivingLabel.order_id == order.id,
        )
    )
    labels_by_line: dict[str, list[ReceivingLabel]] = {}
    labels_by_package: dict[str, list[ReceivingLabel]] = {}
    labels = label_result.scalars().all()
    for label in labels:
        labels_by_line.setdefault(label.order_line_id, []).append(label)
        if label.inbound_package_id:
            labels_by_package.setdefault(label.inbound_package_id, []).append(label)

    unit_result = await db.execute(
        select(HandlingUnit).where(
            HandlingUnit.tenant_id == order.tenant_id,
            HandlingUnit.order_id == order.id,
        )
    )
    units_by_line: dict[str, list[HandlingUnit]] = {}
    units_by_package: dict[str, list[HandlingUnit]] = {}
    units_by_id: dict[str, HandlingUnit] = {}
    handling_units_all = unit_result.scalars().all()
    for unit in handling_units_all:
        units_by_line.setdefault(unit.order_line_id, []).append(unit)
        if unit.inbound_package_id:
            units_by_package.setdefault(unit.inbound_package_id, []).append(unit)
        units_by_id[unit.id] = unit

    observed_result = await db.execute(
        select(ReceivingObservedCode).where(
            ReceivingObservedCode.tenant_id == order.tenant_id,
            ReceivingObservedCode.order_id == order.id,
        )
    )
    observed_by_line: dict[str, list[ReceivingObservedCode]] = {}
    observed_by_package: dict[str, list[ReceivingObservedCode]] = {}
    observed_codes_all = observed_result.scalars().all()
    for code in observed_codes_all:
        if code.order_line_id:
            observed_by_line.setdefault(code.order_line_id, []).append(code)
        if code.inbound_package_id:
            observed_by_package.setdefault(code.inbound_package_id, []).append(code)

    task_result = await db.execute(
        select(Task).where(
            Task.tenant_id == order.tenant_id,
            Task.reference_type == "inbound_order",
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )
    tasks = task_result.scalars().all()

    location_ids = {
        location_id
        for location_id in [
            *[line.staging_location_id for line, _sku in line_rows],
            *[package.staging_location_id for package in packages_all],
            *[task.source_location_id for task in tasks],
            *[task.destination_location_id for task in tasks],
        ]
        if location_id
    }
    location_map: dict[str, Location] = {}
    if location_ids:
        location_result = await db.execute(
            select(Location).where(
                Location.tenant_id == order.tenant_id,
                Location.id.in_(location_ids),
            )
        )
        location_map = {location.id: location for location in location_result.scalars().all()}

    tasks_by_line: dict[str, list[dict]] = {}
    tasks_by_package: dict[str, list[dict]] = {}
    task_status_counts = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "assigned": 0,
    }
    downstream_tasks: list[dict] = []
    for task in tasks:
        source_location = (
            location_map.get(task.source_location_id) if task.source_location_id else None
        )
        destination_location = (
            location_map.get(task.destination_location_id) if task.destination_location_id else None
        )
        handling_unit = units_by_id.get(task.handling_unit_id) if task.handling_unit_id else None
        task_payload = {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "execution_mode": task.execution_mode,
            "assigned_type": task.assigned_type,
            "assigned_to": task.assigned_to,
            "quantity": task.quantity,
            "handling_unit_id": task.handling_unit_id,
            "handling_unit_code": handling_unit.unit_code if handling_unit else None,
            "source_location_id": task.source_location_id,
            "source_location_barcode": source_location.barcode if source_location else None,
            "destination_location_id": task.destination_location_id,
            "destination_location_barcode": destination_location.barcode
            if destination_location
            else None,
            "created_at": _iso(task.created_at),
            "started_at": _iso(task.started_at),
            "completed_at": _iso(task.completed_at),
        }
        downstream_tasks.append(task_payload)
        task_status_counts[task.status] = task_status_counts.get(task.status, 0) + 1
        if handling_unit:
            tasks_by_line.setdefault(handling_unit.order_line_id, []).append(task_payload)
            if handling_unit.inbound_package_id:
                tasks_by_package.setdefault(handling_unit.inbound_package_id, []).append(
                    task_payload
                )

    latest_receipt_confirmation = max(
        (label.received_at for label in labels if label.received_at),
        default=None,
    )

    timeline: list[dict] = []
    _append_timeline_event(
        timeline,
        order.created_at,
        "order_created",
        "Inbound order created",
        f"Order {order.order_number} entered the warehouse workflow.",
    )
    _append_timeline_event(
        timeline,
        order.expected_date,
        "expected_arrival",
        "Expected arrival",
        "The inbound order was scheduled for dock arrival.",
    )
    _append_timeline_event(
        timeline,
        order.received_date,
        "receiving_started",
        "Receiving started",
        "The order entered active dock receiving.",
    )
    _append_timeline_event(
        timeline,
        latest_receipt_confirmation,
        "receiving_completed",
        "Receiving completed",
        "Dock checks were confirmed and the inbound order was ready for downstream work.",
    )
    for code in observed_codes_all:
        _append_timeline_event(
            timeline,
            code.created_at,
            "external_code_captured",
            "Freight code captured",
            f"{code.code_value} ({code.code_type}) was captured from {code.source}.",
        )
    for label in labels:
        _append_timeline_event(
            timeline,
            label.received_at,
            "internal_label_issued",
            "Internal label issued",
            f"{label.label_code} was confirmed and attached to received stock.",
        )
        _append_timeline_event(
            timeline,
            label.printed_at,
            "internal_label_printed",
            "Internal label printed",
            f"{label.label_code} was printed for warehouse handling.",
        )
    for task in tasks:
        handling_unit = units_by_id.get(task.handling_unit_id) if task.handling_unit_id else None
        unit_ref = handling_unit.unit_code if handling_unit else "the inbound unit"
        _append_timeline_event(
            timeline,
            task.created_at,
            "putaway_task_created",
            "Putaway task created",
            f"{unit_ref} was released into putaway work.",
        )
        _append_timeline_event(
            timeline,
            task.started_at,
            "putaway_task_started",
            "Putaway task started",
            f"{unit_ref} started moving toward final storage.",
        )
        _append_timeline_event(
            timeline,
            task.completed_at,
            "putaway_task_completed",
            "Putaway task completed",
            f"{unit_ref} reached its downstream storage destination.",
        )
    _append_timeline_event(
        timeline,
        datetime.fromisoformat(order_extra["archived_at"])
        if order_extra.get("archived_at")
        else None,
        "order_archived",
        "Inbound order archived",
        "The order was moved out of the default active queue but retained for audit.",
    )
    _append_timeline_event(
        timeline,
        datetime.fromisoformat(order_extra["voided_at"]) if order_extra.get("voided_at") else None,
        "order_voided",
        "Inbound order voided",
        "The order was stopped while preserving its audit trail.",
    )
    timeline_event_priority = {
        "order_created": 10,
        "expected_arrival": 20,
        "receiving_started": 30,
        "external_code_captured": 40,
        "internal_label_issued": 50,
        "receiving_completed": 60,
        "internal_label_printed": 70,
        "putaway_task_created": 80,
        "putaway_task_started": 90,
        "putaway_task_completed": 100,
        "order_archived": 110,
        "order_voided": 120,
    }
    timeline.sort(
        key=lambda item: (
            item["occurred_at"] or "",
            timeline_event_priority.get(item["event_type"], 999),
            item["title"],
        )
    )

    lines = []
    for line, sku in line_rows:
        receiving_labels = [
            {
                "id": label.id,
                "inbound_package_id": label.inbound_package_id,
                "package_number": packages_by_id.get(label.inbound_package_id).package_number
                if label.inbound_package_id and packages_by_id.get(label.inbound_package_id)
                else None,
                "label_code": label.label_code,
                "label_type": label.label_type,
                "status": label.status,
                "expected_qty": label.expected_qty,
                "received_qty": label.received_qty,
                "printed_at": _iso(label.printed_at),
                "received_at": _iso(label.received_at),
                "print_count": int((label.extra_data or {}).get("print_count", 0)),
                "external_tracking_number": label.external_tracking_number,
                "external_carton_mark": label.external_carton_mark,
                "external_customer_barcode": label.external_customer_barcode,
            }
            for label in labels_by_line.get(line.id, [])
        ]
        handling_units = [
            {
                "id": unit.id,
                "inbound_package_id": unit.inbound_package_id,
                "package_number": packages_by_id.get(unit.inbound_package_id).package_number
                if unit.inbound_package_id and packages_by_id.get(unit.inbound_package_id)
                else None,
                "unit_code": unit.unit_code,
                "unit_type": unit.unit_type,
                "status": unit.status,
                "expected_qty": unit.expected_qty,
                "received_qty": unit.received_qty,
                "damaged_qty": unit.damaged_qty,
                "external_tracking_number": unit.external_tracking_number,
                "external_carton_mark": unit.external_carton_mark,
                "external_customer_barcode": unit.external_customer_barcode,
                "staging_location_id": unit.staging_location_id,
                "pallet_count": unit.pallet_count,
                "rent_free_days": unit.rent_free_days,
                "package_count": unit.package_count,
                "measured_weight_kg": float(unit.measured_weight_kg)
                if unit.measured_weight_kg is not None
                else None,
                "measured_length_cm": float(unit.measured_length_cm)
                if unit.measured_length_cm is not None
                else None,
                "measured_width_cm": float(unit.measured_width_cm)
                if unit.measured_width_cm is not None
                else None,
                "measured_height_cm": float(unit.measured_height_cm)
                if unit.measured_height_cm is not None
                else None,
                "note": unit.note,
                "downstream_tasks": tasks_by_line.get(line.id, []),
            }
            for unit in units_by_line.get(line.id, [])
        ]
        observed_codes = [
            {
                "id": code.id,
                "inbound_package_id": code.inbound_package_id,
                "package_number": packages_by_id.get(code.inbound_package_id).package_number
                if code.inbound_package_id and packages_by_id.get(code.inbound_package_id)
                else None,
                "code_value": code.code_value,
                "code_type": code.code_type,
                "source": code.source,
                "is_primary": code.is_primary,
                "is_confirmed": code.is_confirmed,
                "created_at": _iso(code.created_at),
            }
            for code in observed_by_line.get(line.id, [])
        ]
        packages = [
            {
                "id": package.id,
                "package_number": package.package_number,
                "label_sequence": package.label_sequence,
                "package_type": package.package_type,
                "package_origin": _infer_package_origin(order.received_date, package.created_at),
                "status": package.status,
                "expected_qty": package.expected_qty,
                "received_qty": package.received_qty,
                "damaged_qty": package.damaged_qty,
                "staging_location_id": package.staging_location_id,
                "staging_location_barcode": location_map.get(package.staging_location_id).barcode
                if package.staging_location_id and location_map.get(package.staging_location_id)
                else None,
                "external_tracking_number": package.external_tracking_number,
                "external_carton_mark": package.external_carton_mark,
                "external_customer_barcode": package.external_customer_barcode,
                "package_count": package.package_count,
                "pallet_count": package.pallet_count,
                "rent_free_days": package.rent_free_days,
                "measured_weight_kg": float(package.measured_weight_kg)
                if package.measured_weight_kg is not None
                else None,
                "measured_length_cm": float(package.measured_length_cm)
                if package.measured_length_cm is not None
                else None,
                "measured_width_cm": float(package.measured_width_cm)
                if package.measured_width_cm is not None
                else None,
                "measured_height_cm": float(package.measured_height_cm)
                if package.measured_height_cm is not None
                else None,
                "receiving_note": package.note,
                "confirmed_at": _iso(package.confirmed_at),
                "observed_codes": [
                    {
                        "id": code.id,
                        "code_value": code.code_value,
                        "code_type": code.code_type,
                        "source": code.source,
                        "is_primary": code.is_primary,
                        "is_confirmed": code.is_confirmed,
                        "created_at": _iso(code.created_at),
                    }
                    for code in observed_by_package.get(package.id, [])
                ],
                "receiving_labels": [
                    {
                        "id": label.id,
                        "label_code": label.label_code,
                        "label_type": label.label_type,
                        "status": label.status,
                        "expected_qty": label.expected_qty,
                        "received_qty": label.received_qty,
                        "printed_at": _iso(label.printed_at),
                        "received_at": _iso(label.received_at),
                        "print_count": int((label.extra_data or {}).get("print_count", 0)),
                        "external_tracking_number": label.external_tracking_number,
                        "external_carton_mark": label.external_carton_mark,
                        "external_customer_barcode": label.external_customer_barcode,
                    }
                    for label in labels_by_package.get(package.id, [])
                ],
                "handling_units": [
                    {
                        "id": unit.id,
                        "unit_code": unit.unit_code,
                        "unit_type": unit.unit_type,
                        "status": unit.status,
                        "expected_qty": unit.expected_qty,
                        "received_qty": unit.received_qty,
                        "damaged_qty": unit.damaged_qty,
                        "external_tracking_number": unit.external_tracking_number,
                        "external_carton_mark": unit.external_carton_mark,
                        "external_customer_barcode": unit.external_customer_barcode,
                        "staging_location_id": unit.staging_location_id,
                        "staging_location_barcode": location_map.get(
                            unit.staging_location_id
                        ).barcode
                        if unit.staging_location_id and location_map.get(unit.staging_location_id)
                        else None,
                        "pallet_count": unit.pallet_count,
                        "rent_free_days": unit.rent_free_days,
                        "package_count": unit.package_count,
                        "measured_weight_kg": float(unit.measured_weight_kg)
                        if unit.measured_weight_kg is not None
                        else None,
                        "measured_length_cm": float(unit.measured_length_cm)
                        if unit.measured_length_cm is not None
                        else None,
                        "measured_width_cm": float(unit.measured_width_cm)
                        if unit.measured_width_cm is not None
                        else None,
                        "measured_height_cm": float(unit.measured_height_cm)
                        if unit.measured_height_cm is not None
                        else None,
                        "note": unit.note,
                    }
                    for unit in units_by_package.get(package.id, [])
                ],
                "downstream_tasks": tasks_by_package.get(package.id, []),
            }
            for package in packages_by_line.get(line.id, [])
        ]
        lines.append(
            {
                "line_id": line.id,
                "line_number": line.line_number,
                "sku_id": line.sku_id,
                "sku_code": sku.sku_code,
                "sku_name": sku.name,
                "sku_barcode": sku.barcode,
                "requires_lot": sku.requires_lot,
                "requires_expiry": sku.requires_expiry,
                "sku_weight_kg": float(sku.weight_kg)
                if sku.weight_kg is not None
                else None,
                "sku_length_cm": float(sku.length_cm)
                if sku.length_cm is not None
                else None,
                "sku_width_cm": float(sku.width_cm)
                if sku.width_cm is not None
                else None,
                "sku_height_cm": float(sku.height_cm)
                if sku.height_cm is not None
                else None,
                "quantity_expected": line.quantity_expected,
                "quantity_received": line.quantity_received,
                "quantity_damaged": line.quantity_damaged,
                "lot_number": line.lot_number,
                "expiry_date": _iso(line.expiry_date),
                "package_count": line.package_count,
                "pallet_count": line.pallet_count,
                "rent_free_days": line.rent_free_days,
                "measured_weight_kg": float(line.measured_weight_kg)
                if line.measured_weight_kg is not None
                else None,
                "measured_length_cm": float(line.measured_length_cm)
                if line.measured_length_cm is not None
                else None,
                "measured_width_cm": float(line.measured_width_cm)
                if line.measured_width_cm is not None
                else None,
                "measured_height_cm": float(line.measured_height_cm)
                if line.measured_height_cm is not None
                else None,
                "receiving_note": line.receiving_note,
                "discrepancy": line.quantity_received - line.quantity_expected
                if line.quantity_received
                else None,
                "external_tracking_number": line.external_tracking_number,
                "external_carton_mark": line.external_carton_mark,
                "external_customer_barcode": line.external_customer_barcode,
                "staging_location_id": line.staging_location_id,
                "staging_location_barcode": location_map.get(line.staging_location_id).barcode
                if line.staging_location_id and location_map.get(line.staging_location_id)
                else None,
                "receiving_labels": receiving_labels,
                "handling_units": handling_units,
                "observed_codes": observed_codes,
                "packages": packages,
                "downstream_tasks": tasks_by_line.get(line.id, []),
            }
        )

    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "archived": bool(order_extra.get("archived", False)),
        "archived_at": order_extra.get("archived_at"),
        "archived_by": order_extra.get("archived_by"),
        "voided": bool(order_extra.get("voided", False)),
        "voided_at": order_extra.get("voided_at"),
        "voided_by": order_extra.get("voided_by"),
        "client_id": order.client_id,
        "reference_number": order.reference_number,
        "supplier_name": order.supplier_name,
        "created_at": _iso(order.created_at),
        "expected_date": _iso(order.expected_date),
        "received_date": _iso(order.received_date),
        "lines": lines,
        "total_expected": sum(line["quantity_expected"] for line in lines),
        "total_received": sum(line["quantity_received"] or 0 for line in lines),
        "total_observed_codes": sum(len(line["observed_codes"]) for line in lines),
        "total_internal_labels": sum(len(line["receiving_labels"]) for line in lines),
        "printed_internal_labels": sum(
            1
            for line in lines
            for label in line["receiving_labels"]
            if (label["print_count"] or 0) > 0
        ),
        "package_summary": {
            "total_packages": len(packages_all),
            "packages_open": sum(
                1
                for package in packages_all
                if package.status in {"expected", "receiving", "received", "staged"}
            ),
            "packages_putaway_pending": sum(
                1 for package in packages_all if package.status == "putaway_pending"
            ),
            "packages_stored": sum(1 for package in packages_all if package.status == "stored"),
            "packages_needing_action": sum(
                1
                for package in packages_all
                if package.status
                in {"expected", "receiving", "received", "staged", "putaway_pending"}
            ),
            "packages_prebooked": sum(
                1
                for package in packages_all
                if _infer_package_origin(order.received_date, package.created_at) == "prebooked"
            ),
            "packages_dock_created": sum(
                1
                for package in packages_all
                if _infer_package_origin(order.received_date, package.created_at) == "dock_created"
            ),
            "supervisor_review_needed": (
                sum(
                    1
                    for package in packages_all
                    if _infer_package_origin(order.received_date, package.created_at)
                    == "dock_created"
                )
                > 0
                and (
                    sum(
                        1
                        for package in packages_all
                        if _infer_package_origin(order.received_date, package.created_at)
                        == "prebooked"
                    )
                    > 0
                    and (
                        sum(
                            1
                            for package in packages_all
                            if package.status in {"expected", "receiving", "received", "staged"}
                        )
                        > 0
                        or sum(1 for package in packages_all if package.status == "putaway_pending")
                        > 0
                        or sum(
                            1
                            for line in lines
                            for label in line["receiving_labels"]
                            if (label["print_count"] or 0) <= 0
                        )
                        > 0
                    )
                )
            ),
            "internal_labels_print_pending": sum(
                1
                for line in lines
                for label in line["receiving_labels"]
                if (label["print_count"] or 0) <= 0
            ),
        },
        "downstream_summary": {
            "putaway_tasks_total": len(downstream_tasks),
            "putaway_tasks_pending": task_status_counts.get("pending", 0)
            + task_status_counts.get("assigned", 0),
            "putaway_tasks_in_progress": task_status_counts.get("in_progress", 0),
            "putaway_tasks_completed": task_status_counts.get("completed", 0),
            "putaway_tasks_failed": task_status_counts.get("failed", 0),
            "putaway_tasks_cancelled": task_status_counts.get("cancelled", 0),
            "handling_units_putaway_pending": sum(
                1 for unit in handling_units_all if unit.status == "putaway_pending"
            ),
            "handling_units_in_final_storage": sum(
                1 for unit in handling_units_all if unit.status == "stored"
            ),
        },
        "downstream_tasks": downstream_tasks,
        "timeline": timeline,
    }
