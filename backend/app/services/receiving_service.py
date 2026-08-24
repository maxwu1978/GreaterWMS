"""
Receiving Service — handles inbound goods flow.

Flow: ASN/PO created → System label generated → Truck arrives → Scan label → Record receipt → Generate putaway tasks

This is the entry point for all goods into the warehouse.
"""

import re
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory, InventoryTransaction, TransactionType
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    InboundPackageStatus,
    InboundStatus,
    ReceivingLabel,
    ReceivingObservedCode,
)
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location
from app.services import agent_preview
from app.services.agent_preview import AgentGateSpec
from app.services.inventory_ledger import ensure_inventory, post_movement
from app.services.putaway_execution_service import PutawayExecutionService

_RECEIVING_CONFIRM = AgentGateSpec(
    action="receiving.confirm",
    risk="medium",
    permission="receiving.execute",
    entity_type="inbound_package",
    token_prefix="rcv-confirm",
    # Receiving's HTTP error payloads use "code" (the ReceivingErrorCode wire
    # format shared by _receiving_error) rather than "error_code".
    error_code_key="code",
)


class ReceivingErrorCode:
    ORDER_NOT_RECEIVING = "order_not_receiving"
    LINE_ALREADY_RECEIVED = "line_already_received"
    INVALID_QUANTITY = "invalid_quantity"
    INVALID_DAMAGED_QTY = "invalid_damaged_qty"
    NOTHING_RECEIVED = "nothing_received"
    STAGING_LOCATION_REQUIRED = "staging_location_required"
    OPEN_PACKAGES_REMAIN = "open_packages_remain"
    LOT_REQUIRED = "lot_required"
    EXPIRY_REQUIRED = "expiry_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMATION_MISMATCH = "confirmation_mismatch"


class ReceivingService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _is_putaway_task_unique_violation(exc: IntegrityError) -> bool:
        message = str(getattr(exc, "orig", exc))
        return "uq_tasks_inbound_putaway_handling_unit" in message or (
            "tasks.tenant_id" in message
            and "tasks.task_type" in message
            and "tasks.reference_type" in message
            and "tasks.reference_id" in message
            and "tasks.handling_unit_id" in message
        )

    async def create_inbound_order(
        self,
        client_id: str,
        warehouse_id: str,
        order_number: str,
        lines: list[dict],
        reference_number: str | None = None,
        expected_date: datetime | None = None,
        supplier_name: str | None = None,
    ) -> InboundOrder:
        """Create an ASN/PO with line items."""
        duplicate = await self.db.scalar(
            select(InboundOrder.id).where(
                InboundOrder.tenant_id == self.tenant_id,
                InboundOrder.warehouse_id == warehouse_id,
                InboundOrder.order_number == order_number,
                InboundOrder.status != InboundStatus.CANCELLED.value,
            )
        )
        if duplicate:
            raise ValueError("Inbound order number already exists for this warehouse")

        order = InboundOrder(
            tenant_id=self.tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number=order_number,
            reference_number=reference_number,
            status=InboundStatus.EXPECTED.value,
            expected_date=expected_date,
            supplier_name=supplier_name,
        )
        self.db.add(order)
        await self.db.flush()
        used_line_numbers: set[int] = set()
        next_auto_line_number = 1
        for _index, line_data in enumerate(lines, start=1):
            requested_line_number = line_data.get("line_number")
            if requested_line_number is not None:
                if requested_line_number <= 0:
                    raise ValueError("Inbound line numbers must be greater than zero")
                if requested_line_number in used_line_numbers:
                    raise ValueError(f"Inbound line number {requested_line_number} is duplicated")
                line_number = requested_line_number
            else:
                while next_auto_line_number in used_line_numbers:
                    next_auto_line_number += 1
                line_number = next_auto_line_number
                next_auto_line_number += 1
            used_line_numbers.add(line_number)

            line = InboundOrderLine(
                tenant_id=self.tenant_id,
                order_id=order.id,
                sku_id=line_data["sku_id"],
                line_number=line_number,
                quantity_expected=line_data["quantity"],
                lot_number=line_data.get("lot_number"),
                expiry_date=line_data.get("expiry_date"),
                external_tracking_number=line_data.get("external_tracking_number"),
                external_carton_mark=line_data.get("external_carton_mark"),
                external_customer_barcode=line_data.get("external_customer_barcode"),
            )
            self.db.add(line)
            await self.db.flush()

            package_specs = self._normalize_upstream_package_specs(
                package_specs=line_data.get("packages") or [],
                line_quantity_expected=line.quantity_expected,
            )
            used_package_numbers: set[int] = set()
            next_auto_package_number = 1
            for package_data in package_specs:
                requested_package_number = package_data["package_number"]
                if requested_package_number is not None:
                    package_number = requested_package_number
                    used_package_numbers.add(package_number)
                else:
                    while next_auto_package_number in used_package_numbers:
                        next_auto_package_number += 1
                    package_number = next_auto_package_number
                    used_package_numbers.add(package_number)
                    next_auto_package_number += 1

                package = InboundPackage(
                    tenant_id=self.tenant_id,
                    order_id=order.id,
                    order_line_id=line.id,
                    package_number=package_number,
                    package_type=package_data["package_type"],
                    status=InboundPackageStatus.EXPECTED.value,
                    expected_qty=package_data["expected_qty"],
                    external_tracking_number=package_data.get("external_tracking_number"),
                    external_carton_mark=package_data.get("external_carton_mark"),
                    external_customer_barcode=package_data.get("external_customer_barcode"),
                )
                self.db.add(package)

        await self.db.flush()
        return order

    def _normalize_upstream_package_specs(
        self,
        package_specs: list[dict],
        line_quantity_expected: int,
    ) -> list[dict]:
        if not package_specs:
            return []

        normalized_specs: list[dict] = []
        used_package_numbers: set[int] = set()
        total_expected = 0
        for _index, package_data in enumerate(package_specs, start=1):
            expected_qty = package_data.get("expected_qty")
            if expected_qty is None:
                if len(package_specs) == 1:
                    expected_qty = line_quantity_expected
                else:
                    raise ValueError("Each inbound package must include expected_qty")
            if expected_qty <= 0:
                raise ValueError("Inbound package expected quantities must be greater than zero")

            package_number = package_data.get("package_number")
            if package_number is not None:
                if package_number <= 0:
                    raise ValueError("Inbound package numbers must be greater than zero")
                if package_number in used_package_numbers:
                    raise ValueError(f"Inbound package number {package_number} is duplicated")
                used_package_numbers.add(package_number)

            normalized_specs.append(
                {
                    "package_number": package_number,
                    "expected_qty": expected_qty,
                    "package_type": (package_data.get("package_type") or "carton").strip()
                    or "carton",
                    "external_tracking_number": (
                        package_data.get("external_tracking_number") or ""
                    ).strip()
                    or None,
                    "external_carton_mark": (package_data.get("external_carton_mark") or "").strip()
                    or None,
                    "external_customer_barcode": (
                        package_data.get("external_customer_barcode") or ""
                    ).strip()
                    or None,
                }
            )
            total_expected += expected_qty

        if total_expected != line_quantity_expected:
            raise ValueError("Inbound package quantities must add up to the line quantity")

        return normalized_specs

    async def start_receiving(self, order_id: str) -> InboundOrder:
        """Mark order as arrived and begin receiving process."""
        order = await self._get_order(order_id)
        if order.status == InboundStatus.RECEIVING.value:
            return order
        if order.status not in {InboundStatus.EXPECTED.value, InboundStatus.ARRIVED.value}:
            raise self._receiving_error(
                status_code=status.HTTP_409_CONFLICT,
                code=ReceivingErrorCode.ORDER_NOT_RECEIVING,
                message=(
                    "Only expected or arrived inbound orders can be opened for receiving. "
                    f"This inbound order is currently {order.status}."
                ),
            )
        order.status = InboundStatus.RECEIVING.value
        order.received_date = datetime.now(UTC)
        await self.db.flush()
        return order

    async def list_packages(self, order_id: str) -> list[InboundPackage]:
        await self._get_order(order_id)
        result = await self.db.execute(
            select(InboundPackage)
            .where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
            )
            .order_by(InboundPackage.order_line_id.asc(), InboundPackage.package_number.asc())
        )
        return list(result.scalars())

    async def create_package(
        self,
        order_id: str,
        line_id: str,
        expected_qty: int | None = None,
        package_type: str = "carton",
        external_tracking_number: str | None = None,
        external_carton_mark: str | None = None,
        external_customer_barcode: str | None = None,
    ) -> InboundPackage:
        order = await self._get_order(order_id)
        line = await self._get_order_line(order_id, line_id)
        next_number = await self._get_next_package_number(order_id, line.id)
        if expected_qty is None:
            assigned_total = (
                await self.db.scalar(
                    select(func.coalesce(func.sum(InboundPackage.expected_qty), 0)).where(
                        InboundPackage.tenant_id == self.tenant_id,
                        InboundPackage.order_id == order_id,
                        InboundPackage.order_line_id == line.id,
                    )
                )
            ) or 0
            remaining = max(0, (line.quantity_expected or 0) - int(assigned_total or 0))
            expected_qty = remaining or 1
        if expected_qty <= 0:
            raise HTTPException(
                status_code=400, detail="Package expected quantity must be greater than zero"
            )

        package = InboundPackage(
            tenant_id=self.tenant_id,
            order_id=order.id,
            order_line_id=line.id,
            package_number=next_number,
            package_type=(package_type or "carton").strip() or "carton",
            status=InboundPackageStatus.EXPECTED.value,
            expected_qty=expected_qty,
            external_tracking_number=(external_tracking_number or "").strip() or None,
            external_carton_mark=(external_carton_mark or "").strip() or None,
            external_customer_barcode=(external_customer_barcode or "").strip() or None,
        )
        self.db.add(package)
        await self.db.flush()
        return package

    async def update_package(
        self,
        order_id: str,
        package_id: str,
        expected_qty: int,
        package_type: str,
        external_tracking_number: str | None = None,
        external_carton_mark: str | None = None,
        external_customer_barcode: str | None = None,
    ) -> InboundPackage:
        package = await self._get_package(order_id, package_id)
        if package.status in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
            InboundPackageStatus.PUTAWAY_PENDING.value,
            InboundPackageStatus.STORED.value,
        }:
            raise HTTPException(
                status_code=409, detail="Confirmed packages can no longer be edited"
            )
        if expected_qty <= 0:
            raise HTTPException(
                status_code=400, detail="Package expected quantity must be greater than zero"
            )

        package.expected_qty = expected_qty
        package.package_type = (package_type or "carton").strip() or "carton"
        package.external_tracking_number = (external_tracking_number or "").strip() or None
        package.external_carton_mark = (external_carton_mark or "").strip() or None
        package.external_customer_barcode = (external_customer_barcode or "").strip() or None
        await self._sync_line_receipt_summary(package.order_line_id)
        await self.db.flush()
        return package

    async def delete_package(self, order_id: str, package_id: str) -> None:
        package = await self._get_package(order_id, package_id)
        if package.status in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
            InboundPackageStatus.PUTAWAY_PENDING.value,
            InboundPackageStatus.STORED.value,
        }:
            raise HTTPException(
                status_code=409, detail="Confirmed packages can no longer be deleted"
            )

        has_observed_codes = await self.db.scalar(
            select(ReceivingObservedCode.id).where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.inbound_package_id == package_id,
            )
        )
        if has_observed_codes:
            raise HTTPException(
                status_code=409,
                detail="Packages with captured external codes must be edited instead of deleted",
            )

        has_internal_objects = await self.db.scalar(
            select(ReceivingLabel.id).where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order_id,
                ReceivingLabel.inbound_package_id == package_id,
            )
        ) or await self.db.scalar(
            select(HandlingUnit.id).where(
                HandlingUnit.tenant_id == self.tenant_id,
                HandlingUnit.order_id == order_id,
                HandlingUnit.inbound_package_id == package_id,
            )
        )
        if has_internal_objects:
            raise HTTPException(
                status_code=409, detail="Packages with internal warehouse objects cannot be deleted"
            )

        order_line_id = package.order_line_id
        await self.db.delete(package)
        await self.db.flush()
        await self._sync_line_receipt_summary(order_line_id)
        await self.db.flush()

    async def open_package(self, order_id: str, package_id: str) -> dict:
        order = await self._get_order(order_id)
        package = await self._get_package(order_id, package_id)
        line = await self._get_order_line(order_id, package.order_line_id)
        label = await self.db.scalar(
            select(ReceivingLabel).where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order_id,
                ReceivingLabel.inbound_package_id == package.id,
            )
        )
        captured_codes = await self.list_observed_codes(order_id=order_id, package_id=package.id)
        received_good_qty = max(0, (package.received_qty or 0) - (package.damaged_qty or 0))
        resolved_label_code = (
            label.label_code
            if label
            else await self._predict_package_label_code(order, line, package)
        )
        return {
            "matched_by": None,
            "opened_directly": True,
            "scanned_code": None,
            "label_code": resolved_label_code,
            "label_type": label.label_type if label else package.package_type,
            "status": label.status if label else package.status,
            "expected_qty": package.expected_qty,
            "received_qty": label.received_qty if label else received_good_qty,
            "remaining_qty": max(0, package.expected_qty - received_good_qty),
            "sku_id": line.sku_id,
            "line_id": line.id,
            "package_id": package.id,
            "package_number": package.package_number,
            "package_status": package.status,
            "lot_number": line.lot_number,
            "expiry_date": line.expiry_date.isoformat() if line.expiry_date else None,
            "external_tracking_number": package.external_tracking_number
            or line.external_tracking_number,
            "external_carton_mark": package.external_carton_mark or line.external_carton_mark,
            "external_customer_barcode": package.external_customer_barcode
            or line.external_customer_barcode,
            "captured_codes": [self._serialize_observed_code(code) for code in captured_codes],
        }

    async def receive_line(
        self,
        order_id: str,
        line_id: str,
        quantity_received: int,
        quantity_damaged: int = 0,
        staging_location_id: str | None = None,
        pallet_count: int | None = None,
        rent_free_days: int | None = None,
        measured_weight_kg: float | None = None,
        measured_length_cm: float | None = None,
        measured_width_cm: float | None = None,
        measured_height_cm: float | None = None,
        package_count: int | None = None,
        receiving_note: str | None = None,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
        receiving_label_code: str | None = None,
    ) -> dict:
        """
        Receive a specific line item — called when operator scans items at the dock.

        Records inventory at staging location and creates an InventoryTransaction.
        Returns receipt summary with any discrepancies.
        """
        order = await self._get_order(order_id)
        if order.status != InboundStatus.RECEIVING.value:
            raise self._receiving_error(
                status_code=status.HTTP_409_CONFLICT,
                code=ReceivingErrorCode.ORDER_NOT_RECEIVING,
                message="This inbound order is not currently in receiving.",
            )

        line = await self._get_order_line(order_id, line_id)
        effective_lot, effective_expiry = await self._resolve_receipt_lot(
            line, lot_number, expiry_date
        )
        self._validate_package_receipt_input(
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
        )
        package = await self._get_or_create_default_package(order, line)
        if package.received_qty > 0 or package.damaged_qty > 0:
            raise self._receiving_error(
                status_code=status.HTTP_409_CONFLICT,
                code=ReceivingErrorCode.LINE_ALREADY_RECEIVED,
                message="This inbound line has already been received through its default package.",
            )

        label, handling_unit = await self._ensure_internal_receipt_objects(order, line, package)
        receipt = await self._record_package_receipt(
            order=order,
            line=line,
            package=package,
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
            pallet_count=pallet_count,
            rent_free_days=rent_free_days,
            measured_weight_kg=measured_weight_kg,
            measured_length_cm=measured_length_cm,
            measured_width_cm=measured_width_cm,
            measured_height_cm=measured_height_cm,
            package_count=package_count,
            receiving_note=receiving_note,
            lot_number=effective_lot,
            expiry_date=effective_expiry,
            user_id=user_id,
            receiving_label_code=receiving_label_code or label.label_code,
        )
        received_good_qty = max(0, quantity_received - quantity_damaged)
        label.received_qty = received_good_qty
        label.status = "received"
        label.received_at = datetime.now(UTC)
        label.expected_qty = package.expected_qty
        label.lot_number = effective_lot
        label.expiry_date = effective_expiry

        handling_unit.received_qty = received_good_qty
        handling_unit.damaged_qty = quantity_damaged
        handling_unit.expected_qty = package.expected_qty
        handling_unit.staging_location_id = staging_location_id
        handling_unit.pallet_count = pallet_count
        handling_unit.rent_free_days = rent_free_days
        handling_unit.measured_weight_kg = measured_weight_kg
        handling_unit.measured_length_cm = measured_length_cm
        handling_unit.measured_width_cm = measured_width_cm
        handling_unit.measured_height_cm = measured_height_cm
        handling_unit.package_count = package_count
        handling_unit.note = receiving_note
        handling_unit.lot_number = effective_lot
        handling_unit.expiry_date = effective_expiry
        handling_unit.status = (
            "staged" if staging_location_id and received_good_qty > 0 else "received"
        )

        await self.db.flush()
        return {
            **receipt,
            "label_code": label.label_code,
            "label_status": label.status,
            "handling_unit_code": handling_unit.unit_code,
            "handling_unit_status": handling_unit.status,
        }

    async def receive_package(
        self,
        order_id: str,
        package_id: str,
        quantity_received: int,
        quantity_damaged: int = 0,
        staging_location_id: str | None = None,
        pallet_count: int | None = None,
        rent_free_days: int | None = None,
        measured_weight_kg: float | None = None,
        measured_length_cm: float | None = None,
        measured_width_cm: float | None = None,
        measured_height_cm: float | None = None,
        package_count: int | None = None,
        receiving_note: str | None = None,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
    ) -> dict:
        order = await self._get_order(order_id)
        if order.status != InboundStatus.RECEIVING.value:
            raise HTTPException(
                status_code=409,
                detail="Start receiving for this inbound order before confirming packages",
            )

        package = await self._get_package(order_id, package_id)
        if package.received_qty > 0 or package.damaged_qty > 0:
            raise HTTPException(status_code=409, detail="This package has already been received")
        self._validate_package_receipt_input(
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
        )
        line = await self._get_order_line(order_id, package.order_line_id)
        effective_lot, effective_expiry = await self._resolve_receipt_lot(
            line, lot_number, expiry_date
        )
        label, handling_unit = await self._ensure_internal_receipt_objects(order, line, package)
        receipt = await self._record_package_receipt(
            order=order,
            line=line,
            package=package,
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
            pallet_count=pallet_count,
            rent_free_days=rent_free_days,
            measured_weight_kg=measured_weight_kg,
            measured_length_cm=measured_length_cm,
            measured_width_cm=measured_width_cm,
            measured_height_cm=measured_height_cm,
            package_count=package_count,
            receiving_note=receiving_note,
            lot_number=effective_lot,
            expiry_date=effective_expiry,
            user_id=user_id,
            receiving_label_code=label.label_code,
        )
        received_good_qty = max(0, quantity_received - quantity_damaged)
        label.received_qty = received_good_qty
        label.status = "received"
        label.received_at = datetime.now(UTC)
        label.expected_qty = package.expected_qty
        label.lot_number = effective_lot
        label.expiry_date = effective_expiry

        handling_unit.received_qty = received_good_qty
        handling_unit.damaged_qty = quantity_damaged
        handling_unit.expected_qty = package.expected_qty
        handling_unit.staging_location_id = staging_location_id
        handling_unit.pallet_count = pallet_count
        handling_unit.rent_free_days = rent_free_days
        handling_unit.measured_weight_kg = measured_weight_kg
        handling_unit.measured_length_cm = measured_length_cm
        handling_unit.measured_width_cm = measured_width_cm
        handling_unit.measured_height_cm = measured_height_cm
        handling_unit.package_count = package_count
        handling_unit.note = receiving_note
        handling_unit.lot_number = effective_lot
        handling_unit.expiry_date = effective_expiry
        handling_unit.status = (
            "staged" if staging_location_id and handling_unit.received_qty > 0 else "received"
        )

        observed_codes = await self._confirm_observed_codes(
            order_id=order_id,
            line_id=line.id,
            package_id=package.id,
            receiving_label_id=label.id,
            handling_unit_id=handling_unit.id,
            package=package,
            label=label,
            handling_unit=handling_unit,
        )
        await self.db.flush()
        return {
            **receipt,
            "label_code": label.label_code,
            "label_status": label.status,
            "handling_unit_code": handling_unit.unit_code,
            "handling_unit_status": handling_unit.status,
            "captured_codes": [self._serialize_observed_code(code) for code in observed_codes],
        }

    async def preview_package_receipt(
        self,
        order_id: str,
        package_id: str,
        quantity_received: int,
        quantity_damaged: int = 0,
        staging_location_id: str | None = None,
        pallet_count: int | None = None,
        rent_free_days: int | None = None,
        measured_weight_kg: float | None = None,
        measured_length_cm: float | None = None,
        measured_width_cm: float | None = None,
        measured_height_cm: float | None = None,
        package_count: int | None = None,
        receiving_note: str | None = None,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        order = await self._get_order(order_id)
        if order.status != InboundStatus.RECEIVING.value:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": ReceivingErrorCode.ORDER_NOT_RECEIVING,
                    "message": "Start receiving for this inbound order before confirming packages",
                },
            )

        package = await self._get_package(order_id, package_id)
        if package.received_qty > 0 or package.damaged_qty > 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "package_already_received",
                    "message": "This package has already been received",
                },
            )

        good_qty = self._validate_package_receipt_input(
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
        )
        line = await self._get_order_line(order_id, package.order_line_id)
        effective_lot = (lot_number or line.lot_number or "").strip() or None
        effective_expiry = expiry_date or line.expiry_date
        staging_location = None
        if staging_location_id:
            staging_location = await self.db.scalar(
                select(Location).where(
                    Location.tenant_id == self.tenant_id,
                    Location.warehouse_id == order.warehouse_id,
                    Location.id == staging_location_id,
                )
            )
            if not staging_location:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "staging_location_not_found",
                        "message": "Staging location not found for this inbound warehouse",
                    },
                )

        discrepancy = quantity_received - package.expected_qty
        next_package_status = (
            InboundPackageStatus.STAGED.value
            if staging_location_id and good_qty > 0
            else InboundPackageStatus.RECEIVED.value
        )
        endpoint = f"POST /api/v1/receiving/inbound/{order_id}/packages/{package_id}/receive"
        body = {
            "quantity_received": quantity_received,
            "quantity_damaged": quantity_damaged,
            "staging_location_id": staging_location_id,
            "pallet_count": pallet_count,
            "rent_free_days": rent_free_days,
            "measured_weight_kg": measured_weight_kg,
            "measured_length_cm": measured_length_cm,
            "measured_width_cm": measured_width_cm,
            "measured_height_cm": measured_height_cm,
            "package_count": package_count,
            "receiving_note": receiving_note,
            "lot_number": effective_lot,
            "expiry_date": effective_expiry.isoformat() if effective_expiry else None,
        }
        state_before = {
            "order_status": order.status,
            "package_status": package.status,
            "received_qty": package.received_qty,
            "damaged_qty": package.damaged_qty,
            "staging_location_id": package.staging_location_id,
        }
        state_after = {
            "order_status": order.status,
            "package_status": next_package_status,
            "received_qty": quantity_received,
            "damaged_qty": quantity_damaged,
            "staging_location_id": staging_location_id,
            "inventory_delta": good_qty,
        }
        # Unlike other domains, blocked receiving previews are reported through
        # the HTTP errors raised above (409/404 with a "code" payload) instead
        # of ok=False dry-run responses, so blocked_preview is not used here.
        # No savepoint dry run either: the projected state is computed directly.
        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _RECEIVING_CONFIRM,
            entity={
                "type": "inbound_package",
                "id": package.id,
                "order_id": order.id,
                "package_id": package.id,
            },
            entity_id=package.id,
            endpoint=endpoint,
            body=body,
            hash_scope={"order_id": order.id, "package_id": package.id},
            state_before=state_before,
            state_after=state_after,
            scope={
                "tenant_id": self.tenant_id,
                "warehouse_id": order.warehouse_id,
                "order_id": order.id,
                "package_id": package.id,
            },
            records=[
                {
                    "type": "inbound_package",
                    "id": package.id,
                    "order_number": order.order_number,
                    "package_number": package.package_number,
                    "expected_qty": package.expected_qty,
                    "received_qty": quantity_received,
                    "damaged_qty": quantity_damaged,
                    "discrepancy": discrepancy,
                }
            ],
            impact={
                "inventory_delta": good_qty,
                "staging_location": {
                    "id": staging_location.id,
                    "barcode": staging_location.barcode,
                }
                if staging_location
                else None,
                "putaway_tasks": "created by receive write path when receipt is confirmed",
            },
            result={
                "message": "No backend write was performed.",
                "status": "over" if discrepancy > 0 else "short" if discrepancy < 0 else "exact",
                "safe_commands": [
                    "wms receiving confirm --dry-run --live-preview",
                    "wms inbound list --limit 20",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_package_receipt_with_token(
        self,
        order_id: str,
        package_id: str,
        confirmation_token: str,
        quantity_received: int,
        quantity_damaged: int = 0,
        staging_location_id: str | None = None,
        pallet_count: int | None = None,
        rent_free_days: int | None = None,
        measured_weight_kg: float | None = None,
        measured_length_cm: float | None = None,
        measured_width_cm: float | None = None,
        measured_height_cm: float | None = None,
        package_count: int | None = None,
        receiving_note: str | None = None,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _RECEIVING_CONFIRM,
            confirmation_token,
            message="A receiving confirmation token is required before the agent can write.",
        )

        preview = await self.preview_package_receipt(
            order_id=order_id,
            package_id=package_id,
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
            pallet_count=pallet_count,
            rent_free_days=rent_free_days,
            measured_weight_kg=measured_weight_kg,
            measured_length_cm=measured_length_cm,
            measured_width_cm=measured_width_cm,
            measured_height_cm=measured_height_cm,
            package_count=package_count,
            receiving_note=receiving_note,
            lot_number=lot_number,
            expiry_date=expiry_date,
            user_id=user_id,
            persist_evidence=False,
        )
        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _RECEIVING_CONFIRM,
            entity_id=package_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The receiving confirmation token no longer matches the current preview.",
        )

        receipt = await self.receive_package(
            order_id=order_id,
            package_id=package_id,
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
            pallet_count=pallet_count,
            rent_free_days=rent_free_days,
            measured_weight_kg=measured_weight_kg,
            measured_length_cm=measured_length_cm,
            measured_width_cm=measured_width_cm,
            measured_height_cm=measured_height_cm,
            package_count=package_count,
            receiving_note=receiving_note,
            lot_number=lot_number,
            expiry_date=expiry_date,
            user_id=user_id,
        )
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _RECEIVING_CONFIRM,
            evidence=evidence,
            ok=True,
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after={**preview["state_after"], "receipt_status": receipt.get("status")},
            payload_hash=payload_hash,
            next_action="scan_next_package_or_putaway",
            result=receipt,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

    async def correct_package_receipt(
        self,
        order_id: str,
        package_id: str,
        quantity_received: int,
        quantity_damaged: int = 0,
        staging_location_id: str | None = None,
        pallet_count: int | None = None,
        rent_free_days: int | None = None,
        measured_weight_kg: float | None = None,
        measured_length_cm: float | None = None,
        measured_width_cm: float | None = None,
        measured_height_cm: float | None = None,
        package_count: int | None = None,
        receiving_note: str | None = None,
        external_tracking_number: str | None = None,
        external_carton_mark: str | None = None,
        external_customer_barcode: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Correct a confirmed package while preserving inventory audit history."""
        order = await self._get_order(order_id)
        package = await self._get_package(order_id, package_id)
        line = await self._get_order_line(order_id, package.order_line_id)
        label = await self.db.scalar(
            select(ReceivingLabel).where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order_id,
                ReceivingLabel.inbound_package_id == package.id,
            )
        )
        handling_unit = await self.db.scalar(
            select(HandlingUnit).where(
                HandlingUnit.tenant_id == self.tenant_id,
                HandlingUnit.order_id == order_id,
                HandlingUnit.inbound_package_id == package.id,
            )
        )

        if package.status not in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
            InboundPackageStatus.PUTAWAY_PENDING.value,
            InboundPackageStatus.STORED.value,
        }:
            raise HTTPException(
                status_code=409,
                detail="Only confirmed packages can be corrected",
            )

        old_received_qty = int(package.received_qty or 0)
        old_damaged_qty = int(package.damaged_qty or 0)
        old_good_qty = max(0, old_received_qty - old_damaged_qty)
        new_good_qty = max(0, quantity_received - quantity_damaged)
        old_staging_location_id = package.staging_location_id
        requested_staging_location_id = (
            staging_location_id if staging_location_id is not None else package.staging_location_id
        )
        new_staging_location_id = requested_staging_location_id if new_good_qty > 0 else None
        resolved_package_count = (
            package_count if package_count is not None else package.package_count
        )
        resolved_pallet_count = pallet_count if pallet_count is not None else package.pallet_count
        resolved_rent_free_days = (
            rent_free_days if rent_free_days is not None else package.rent_free_days
        )
        resolved_weight_kg = (
            measured_weight_kg if measured_weight_kg is not None else package.measured_weight_kg
        )
        resolved_length_cm = (
            measured_length_cm if measured_length_cm is not None else package.measured_length_cm
        )
        resolved_width_cm = (
            measured_width_cm if measured_width_cm is not None else package.measured_width_cm
        )
        resolved_height_cm = (
            measured_height_cm if measured_height_cm is not None else package.measured_height_cm
        )
        resolved_receiving_note = receiving_note if receiving_note is not None else package.note

        def resolve_optional_text(value: str | None, current: str | None) -> str | None:
            if value is None:
                return current
            return value.strip() or None

        resolved_tracking_number = resolve_optional_text(
            external_tracking_number, package.external_tracking_number
        )
        resolved_carton_mark = resolve_optional_text(
            external_carton_mark, package.external_carton_mark
        )
        resolved_customer_barcode = resolve_optional_text(
            external_customer_barcode, package.external_customer_barcode
        )

        operational_change_requested = (
            quantity_received != int(package.received_qty or 0)
            or quantity_damaged != int(package.damaged_qty or 0)
            or new_staging_location_id != (package.staging_location_id or None)
            or resolved_package_count != package.package_count
            or resolved_pallet_count != package.pallet_count
            or resolved_rent_free_days != package.rent_free_days
        )
        if (
            package.status
            in {
                InboundPackageStatus.PUTAWAY_PENDING.value,
                InboundPackageStatus.STORED.value,
            }
            and operational_change_requested
        ):
            raise HTTPException(
                status_code=409,
                detail="Packages already released to putaway can only update external codes, measurements, and notes",
            )

        self._validate_package_receipt_input(
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=new_staging_location_id,
        )

        if package.status in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
        }:
            if old_staging_location_id == new_staging_location_id:
                if new_staging_location_id:
                    delta = new_good_qty - old_good_qty
                    await self._apply_inventory_delta(
                        order_id=order.id,
                        client_id=order.client_id,
                        warehouse_id=order.warehouse_id,
                        location_id=new_staging_location_id,
                        sku_id=line.sku_id,
                        quantity_delta=delta,
                        lot_number=line.lot_number,
                        expiry_date=line.expiry_date,
                        user_id=user_id,
                        notes=f"Receipt correction for package {package.package_number}",
                    )
            else:
                if old_staging_location_id and old_good_qty > 0:
                    await self._apply_inventory_delta(
                        order_id=order.id,
                        client_id=order.client_id,
                        warehouse_id=order.warehouse_id,
                        location_id=old_staging_location_id,
                        sku_id=line.sku_id,
                        quantity_delta=-old_good_qty,
                        lot_number=line.lot_number,
                        expiry_date=line.expiry_date,
                        user_id=user_id,
                        notes=f"Receipt correction removed package {package.package_number} from original staging",
                    )
                if new_staging_location_id and new_good_qty > 0:
                    await self._apply_inventory_delta(
                        order_id=order.id,
                        client_id=order.client_id,
                        warehouse_id=order.warehouse_id,
                        location_id=new_staging_location_id,
                        sku_id=line.sku_id,
                        quantity_delta=new_good_qty,
                        lot_number=line.lot_number,
                        expiry_date=line.expiry_date,
                        user_id=user_id,
                        notes=f"Receipt correction restaged package {package.package_number}",
                    )

        package.received_qty = quantity_received
        package.damaged_qty = quantity_damaged
        package.staging_location_id = new_staging_location_id
        package.pallet_count = resolved_pallet_count
        package.rent_free_days = resolved_rent_free_days
        package.measured_weight_kg = resolved_weight_kg
        package.measured_length_cm = resolved_length_cm
        package.measured_width_cm = resolved_width_cm
        package.measured_height_cm = resolved_height_cm
        package.package_count = resolved_package_count
        package.note = resolved_receiving_note
        package.external_tracking_number = resolved_tracking_number
        package.external_carton_mark = resolved_carton_mark
        package.external_customer_barcode = resolved_customer_barcode
        if package.status in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
        }:
            package.status = (
                InboundPackageStatus.STAGED.value
                if new_staging_location_id and new_good_qty > 0
                else InboundPackageStatus.RECEIVED.value
            )

        if label:
            label.expected_qty = package.expected_qty
            label.received_qty = new_good_qty
            label.external_tracking_number = package.external_tracking_number
            label.external_carton_mark = package.external_carton_mark
            label.external_customer_barcode = package.external_customer_barcode
            label.lot_number = line.lot_number
            label.expiry_date = line.expiry_date
            label.status = "received"

        if handling_unit:
            handling_unit.expected_qty = package.expected_qty
            handling_unit.received_qty = new_good_qty
            handling_unit.damaged_qty = quantity_damaged
            handling_unit.staging_location_id = new_staging_location_id
            handling_unit.pallet_count = resolved_pallet_count
            handling_unit.rent_free_days = resolved_rent_free_days
            handling_unit.measured_weight_kg = resolved_weight_kg
            handling_unit.measured_length_cm = resolved_length_cm
            handling_unit.measured_width_cm = resolved_width_cm
            handling_unit.measured_height_cm = resolved_height_cm
            handling_unit.package_count = resolved_package_count
            handling_unit.note = resolved_receiving_note
            handling_unit.external_tracking_number = package.external_tracking_number
            handling_unit.external_carton_mark = package.external_carton_mark
            handling_unit.external_customer_barcode = package.external_customer_barcode
            if package.status in {
                InboundPackageStatus.RECEIVED.value,
                InboundPackageStatus.STAGED.value,
            }:
                handling_unit.status = (
                    "staged" if new_staging_location_id and new_good_qty > 0 else "received"
                )

        extra = dict(order.extra_data or {})
        corrections = list(extra.get("receipt_corrections") or [])
        corrections.append(
            {
                "package_id": package.id,
                "package_number": package.package_number,
                "old_received_qty": old_received_qty,
                "new_received_qty": quantity_received,
                "old_damaged_qty": old_damaged_qty,
                "new_damaged_qty": quantity_damaged,
                "corrected_at": datetime.now(UTC).isoformat(),
                "corrected_by": user_id,
            }
        )
        extra["receipt_corrections"] = corrections[-50:]
        order.extra_data = extra

        await self._sync_line_receipt_summary(line.id)
        await self.db.flush()
        return {
            "id": package.id,
            "order_line_id": package.order_line_id,
            "package_number": package.package_number,
            "package_type": package.package_type,
            "status": package.status,
            "expected_qty": package.expected_qty,
            "received_qty": package.received_qty,
            "damaged_qty": package.damaged_qty,
            "staging_location_id": package.staging_location_id,
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
        }

    async def scan_label(self, order_id: str, label_code: str, source: str = "scan") -> dict:
        """Resolve a scanned code into the matching internal receiving label."""
        label_code = self._normalize_scanned_code(label_code)
        order = await self._get_order(order_id)
        if order.status != InboundStatus.RECEIVING.value:
            raise HTTPException(
                status_code=409,
                detail="Start receiving for this inbound order before scanning labels",
            )

        order = await self._get_order(order_id)
        label, line, package, matched_by, resolved_label_code = await self._resolve_receipt_target(
            order_id=order_id, scanned_code=label_code
        )
        if (label and label.status == "received") or package.status in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
            InboundPackageStatus.PUTAWAY_PENDING.value,
            InboundPackageStatus.STORED.value,
        }:
            raise HTTPException(
                status_code=409, detail="This system label has already been received"
            )

        captured_codes = await self._capture_observed_code(
            order_id=order_id,
            line_id=line.id,
            package_id=package.id,
            receiving_label_id=label.id if label else None,
            scanned_code=label_code,
            matched_by=matched_by,
            source=source,
        )

        received_good_qty = max(0, (package.received_qty or 0) - (package.damaged_qty or 0))
        return {
            "matched_by": matched_by,
            "scanned_code": label_code,
            "label_code": resolved_label_code,
            "label_type": label.label_type if label else package.package_type,
            "status": label.status if label else package.status,
            "expected_qty": package.expected_qty,
            "received_qty": label.received_qty if label else received_good_qty,
            "remaining_qty": max(0, package.expected_qty - received_good_qty),
            "sku_id": line.sku_id,
            "line_id": line.id,
            "package_id": package.id,
            "package_number": package.package_number,
            "package_status": package.status,
            "lot_number": line.lot_number,
            "expiry_date": line.expiry_date.isoformat() if line.expiry_date else None,
            "external_tracking_number": package.external_tracking_number
            or line.external_tracking_number,
            "external_carton_mark": package.external_carton_mark or line.external_carton_mark,
            "external_customer_barcode": package.external_customer_barcode
            or line.external_customer_barcode,
            "captured_codes": [self._serialize_observed_code(code) for code in captured_codes],
        }

    async def preview_scan_label(
        self, order_id: str, label_code: str, source: str = "scan"
    ) -> dict:
        savepoint = await self.db.begin_nested()
        try:
            scan = await self.scan_label(order_id=order_id, label_code=label_code, source=source)
        finally:
            await savepoint.rollback()

        return {
            "ok": True,
            "dry_run": True,
            "action": "receiving.scan",
            "risk": "medium",
            "permission": "receiving.execute",
            "entity": {
                "type": "inbound_package",
                "id": scan.get("package_id"),
                "order_id": order_id,
                "package_id": scan.get("package_id"),
            },
            "state_before": "unchanged",
            "state_after": "unchanged",
            "planned_request": {
                "endpoint": f"POST /api/v1/receiving/inbound/{order_id}/scan-label",
                "body": {
                    "label_code": self._normalize_scanned_code(label_code),
                    "source": source,
                },
                "idempotency_key_required_for_write": False,
            },
            "confirmation_required_for_write": False,
            "next_action": "review_matched_package_then_choose_dock",
            "evidence_id": None,
            "result": {
                **scan,
                "message": "No backend write was performed.",
                "safe_commands": [
                    "wms receiving choose-dock --dry-run --live-preview",
                    "wms receiving confirm --dry-run --live-preview",
                ],
            },
        }

    async def preview_choose_dock(
        self,
        order_id: str,
        package_id: str,
        staging_location_id: str,
    ) -> dict:
        order = await self._get_order(order_id)
        if order.status != InboundStatus.RECEIVING.value:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": ReceivingErrorCode.ORDER_NOT_RECEIVING,
                    "message": "Start receiving for this inbound order before choosing a dock",
                },
            )
        package = await self._get_package(order_id, package_id)
        if package.status in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
            InboundPackageStatus.PUTAWAY_PENDING.value,
            InboundPackageStatus.STORED.value,
        }:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "package_already_received",
                    "message": "This package has already been received",
                },
            )
        staging_location = await self.db.scalar(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == order.warehouse_id,
                Location.id == staging_location_id,
            )
        )
        if not staging_location:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "staging_location_not_found",
                    "message": "Staging location not found for this inbound warehouse",
                },
            )

        return {
            "ok": True,
            "dry_run": True,
            "action": "receiving.choose_dock",
            "risk": "medium",
            "permission": "receiving.execute",
            "entity": {
                "type": "inbound_package",
                "id": package.id,
                "order_id": order.id,
                "package_id": package.id,
            },
            "state_before": {
                "order_status": order.status,
                "package_status": package.status,
                "staging_location_id": package.staging_location_id,
            },
            "state_after": {
                "order_status": order.status,
                "package_status": package.status,
                "staging_location_id": staging_location.id,
            },
            "planned_request": {
                "endpoint": f"POST /api/v1/receiving/inbound/{order_id}/packages/{package_id}/receive",
                "body": {
                    "staging_location_id": staging_location.id,
                    "staging_location_barcode": staging_location.barcode,
                },
                "idempotency_key_required_for_write": True,
            },
            "confirmation_required_for_write": True,
            "next_action": "confirm_receipt_with_quantity",
            "evidence_id": None,
            "result": {
                "message": "No backend write was performed.",
                "safe_commands": [
                    "wms receiving confirm --dry-run --live-preview",
                    "wms receiving recover --dry-run --live-preview",
                ],
            },
        }

    @staticmethod
    def preview_recovery(error_code: str) -> dict:
        code = (error_code or "unknown").strip().lower()
        plans = {
            "package_already_received": {
                "what_happened": "This package was already received.",
                "why_blocked": "Receiving it again would duplicate inventory.",
                "recommended_action": "Scan the next package or inspect the package before correcting.",
                "safe_commands": [
                    "wms inbound list --limit 20",
                    "wms receiving recover --dry-run --live-preview --error-code package_already_received",
                ],
                "next_action": "scan_next_package",
            },
            ReceivingErrorCode.ORDER_NOT_RECEIVING: {
                "what_happened": "The inbound order is not currently in Receiving state.",
                "why_blocked": "Packages can only be confirmed after receiving has started.",
                "recommended_action": "Start receiving for the inbound order or return to the inbound list.",
                "safe_commands": ["wms inbound list --limit 20"],
                "next_action": "start_receiving_or_return_to_list",
            },
            ReceivingErrorCode.STAGING_LOCATION_REQUIRED: {
                "what_happened": "A dock or staging location is required.",
                "why_blocked": "Good received units need a staging location before putaway.",
                "recommended_action": "Choose a dock before confirming receipt.",
                "safe_commands": [
                    "wms warehouse list",
                    "wms receiving choose-dock --dry-run --live-preview",
                ],
                "next_action": "choose_dock",
            },
            "staging_location_not_found": {
                "what_happened": "The selected dock or staging location was not found.",
                "why_blocked": "The package cannot be staged to an unknown location.",
                "recommended_action": "Choose another dock in the same warehouse.",
                "safe_commands": ["wms warehouse list", "wms receiving choose-dock --dry-run"],
                "next_action": "choose_dock",
            },
        }
        recovery = plans.get(
            code,
            {
                "what_happened": "Receiving needs recovery guidance.",
                "why_blocked": "No specific recovery plan exists for this error code yet.",
                "recommended_action": "Inspect receiving state and choose a safe read-only command.",
                "safe_commands": ["wms inbound list --limit 20", "wms workflow list --json"],
                "next_action": "inspect_receiving_state",
            },
        )
        return {
            "ok": True,
            "dry_run": True,
            "action": "receiving.recover",
            "risk": "low",
            "permission": "receiving.execute",
            "entity": {"type": "recovery_plan", "id": code},
            "state_before": "unchanged",
            "state_after": "unchanged",
            "planned_request": {
                "endpoint": "none",
                "body": {"error_code": code, **recovery},
                "idempotency_key_required_for_write": False,
            },
            "confirmation_required_for_write": False,
            "next_action": recovery["next_action"],
            "evidence_id": None,
            "result": {"message": "No backend write was performed.", **recovery},
        }

    async def receive_label(
        self,
        order_id: str,
        label_code: str,
        quantity_received: int,
        quantity_damaged: int = 0,
        staging_location_id: str | None = None,
        pallet_count: int | None = None,
        rent_free_days: int | None = None,
        measured_weight_kg: float | None = None,
        measured_length_cm: float | None = None,
        measured_width_cm: float | None = None,
        measured_height_cm: float | None = None,
        package_count: int | None = None,
        receiving_note: str | None = None,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Receive an inbound line through its system-generated receiving label."""
        label_code = self._normalize_scanned_code(label_code)
        order = await self._get_order(order_id)
        if order.status != InboundStatus.RECEIVING.value:
            raise HTTPException(
                status_code=409,
                detail="Start receiving for this inbound order before confirming labels",
            )
        self._validate_package_receipt_input(
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
        )
        label, line, package, matched_by, resolved_label_code = await self._resolve_receipt_target(
            order_id=order_id, scanned_code=label_code
        )
        effective_lot, effective_expiry = await self._resolve_receipt_lot(
            line, lot_number, expiry_date
        )
        if (label and label.status == "received") or package.status in {
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
            InboundPackageStatus.PUTAWAY_PENDING.value,
            InboundPackageStatus.STORED.value,
        }:
            raise HTTPException(
                status_code=409, detail="This system label has already been received"
            )
        label, handling_unit = await self._ensure_internal_receipt_objects(order, line, package)

        receipt = await self._record_package_receipt(
            order=order,
            line=line,
            package=package,
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
            pallet_count=pallet_count,
            rent_free_days=rent_free_days,
            measured_weight_kg=measured_weight_kg,
            measured_length_cm=measured_length_cm,
            measured_width_cm=measured_width_cm,
            measured_height_cm=measured_height_cm,
            package_count=package_count,
            receiving_note=receiving_note,
            lot_number=effective_lot,
            expiry_date=effective_expiry,
            user_id=user_id,
            receiving_label_code=label.label_code,
        )
        received_good_qty = max(0, quantity_received - quantity_damaged)
        label.received_qty = received_good_qty
        label.status = "received"
        label.received_at = datetime.now(UTC)
        label.expected_qty = package.expected_qty
        label.lot_number = effective_lot
        label.expiry_date = effective_expiry

        handling_unit.received_qty = received_good_qty
        handling_unit.damaged_qty = quantity_damaged
        handling_unit.expected_qty = package.expected_qty
        handling_unit.staging_location_id = staging_location_id
        handling_unit.pallet_count = pallet_count
        handling_unit.rent_free_days = rent_free_days
        handling_unit.measured_weight_kg = measured_weight_kg
        handling_unit.measured_length_cm = measured_length_cm
        handling_unit.measured_width_cm = measured_width_cm
        handling_unit.measured_height_cm = measured_height_cm
        handling_unit.package_count = package_count
        handling_unit.note = receiving_note
        handling_unit.lot_number = effective_lot
        handling_unit.expiry_date = effective_expiry
        handling_unit.status = (
            "staged" if staging_location_id and handling_unit.received_qty > 0 else "received"
        )

        observed_codes = await self._confirm_observed_codes(
            order_id=order_id,
            line_id=line.id,
            package_id=package.id,
            receiving_label_id=label.id,
            handling_unit_id=handling_unit.id if handling_unit else None,
            package=package,
            label=label,
            handling_unit=handling_unit,
        )

        await self.db.flush()
        discrepancy = quantity_received - package.expected_qty
        return {
            **receipt,
            "matched_by": matched_by,
            "label_code": label.label_code,
            "label_status": label.status,
            "expected_qty": label.expected_qty,
            "remaining_qty": max(0, label.expected_qty - label.received_qty),
            "discrepancy_qty": discrepancy,
            "discrepancy_status": "over"
            if discrepancy > 0
            else "short"
            if discrepancy < 0
            else "exact",
            "handling_unit_code": handling_unit.unit_code if handling_unit else label.label_code,
            "handling_unit_status": handling_unit.status if handling_unit else None,
            "package_id": package.id,
            "package_number": package.package_number,
            "captured_codes": [self._serialize_observed_code(code) for code in observed_codes],
        }

    async def list_labels(self, order_id: str) -> list[ReceivingLabel]:
        result = await self.db.execute(
            select(ReceivingLabel)
            .where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order_id,
            )
            .order_by(ReceivingLabel.created_at.asc())
        )
        return list(result.scalars())

    async def list_observed_codes(
        self,
        order_id: str,
        label_code: str | None = None,
        package_id: str | None = None,
    ) -> list[ReceivingObservedCode]:
        if package_id:
            package = await self._get_package(order_id, package_id)
            line = await self._get_order_line(order_id, package.order_line_id)
        elif label_code:
            _, line, package, _, _ = await self._resolve_receipt_target(
                order_id=order_id, scanned_code=label_code
            )
        else:
            raise HTTPException(
                status_code=400, detail="Either package_id or label_code is required"
            )
        result = await self.db.execute(
            select(ReceivingObservedCode)
            .where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.order_line_id == line.id,
                ReceivingObservedCode.inbound_package_id == package.id,
            )
            .order_by(ReceivingObservedCode.created_at.asc())
        )
        return list(result.scalars())

    async def add_observed_code(
        self,
        order_id: str,
        label_code: str | None,
        code_value: str,
        code_type: str | None = None,
        source: str = "manual",
        is_primary: bool = False,
        package_id: str | None = None,
    ) -> ReceivingObservedCode:
        code_value = self._normalize_scanned_code(code_value)
        if package_id:
            package = await self._get_package(order_id, package_id)
            line = await self._get_order_line(order_id, package.order_line_id)
            label = await self.db.scalar(
                select(ReceivingLabel).where(
                    ReceivingLabel.tenant_id == self.tenant_id,
                    ReceivingLabel.order_id == order_id,
                    ReceivingLabel.inbound_package_id == package.id,
                )
            )
        elif label_code:
            label, line, package, _, _ = await self._resolve_receipt_target(
                order_id=order_id, scanned_code=label_code
            )
        else:
            raise HTTPException(
                status_code=400, detail="Either package_id or label_code is required"
            )
        if label and label.status == "received":
            raise HTTPException(status_code=409, detail="This receiving label is already confirmed")

        normalized_code = code_value.strip()
        if not normalized_code:
            raise HTTPException(status_code=400, detail="Observed code cannot be empty")

        existing = await self.db.scalar(
            select(ReceivingObservedCode).where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.order_line_id == line.id,
                ReceivingObservedCode.inbound_package_id == package.id,
                ReceivingObservedCode.code_value == normalized_code,
            )
        )
        if existing:
            if code_type:
                existing.code_type = code_type
            existing.source = source or existing.source
            if is_primary:
                await self._clear_primary_observed_code(
                    order_id, line.id, package.id, label.id if label else None
                )
                existing.is_primary = True
            if code_type:
                self._apply_observed_code_to_package(package, normalized_code, code_type)
            await self.db.flush()
            return existing

        if is_primary:
            await self._clear_primary_observed_code(
                order_id, line.id, package.id, label.id if label else None
            )

        observed = ReceivingObservedCode(
            tenant_id=self.tenant_id,
            order_id=order_id,
            order_line_id=line.id,
            inbound_package_id=package.id,
            receiving_label_id=label.id if label else None,
            code_value=normalized_code,
            code_type=code_type or "other",
            source=source or "manual",
            is_primary=is_primary,
            is_confirmed=False,
        )
        self.db.add(observed)
        self._apply_observed_code_to_package(package, normalized_code, observed.code_type)
        await self.db.flush()
        return observed

    async def update_observed_code(
        self,
        order_id: str,
        code_id: str,
        code_value: str,
        code_type: str | None = None,
        is_primary: bool = False,
    ) -> ReceivingObservedCode:
        observed = await self._get_observed_code(order_id, code_id)
        if observed.is_confirmed:
            raise HTTPException(
                status_code=409, detail="Confirmed receiving codes can no longer be edited"
            )

        normalized_code = code_value.strip()
        if not normalized_code:
            raise HTTPException(status_code=400, detail="Observed code cannot be empty")

        observed.code_value = normalized_code
        observed.code_type = code_type or observed.code_type
        if is_primary:
            await self._clear_primary_observed_code(
                order_id,
                observed.order_line_id,
                observed.inbound_package_id,
                observed.receiving_label_id,
            )
        observed.is_primary = is_primary
        package = (
            await self._get_package(order_id, observed.inbound_package_id)
            if observed.inbound_package_id
            else None
        )
        if package:
            self._apply_observed_code_to_package(package, normalized_code, observed.code_type)
        await self.db.flush()
        return observed

    async def delete_observed_code(self, order_id: str, code_id: str) -> None:
        observed = await self._get_observed_code(order_id, code_id)
        if observed.is_confirmed:
            raise HTTPException(
                status_code=409, detail="Confirmed receiving codes can no longer be deleted"
            )
        package_id = observed.inbound_package_id
        await self.db.delete(observed)
        await self.db.flush()
        if package_id:
            await self._refresh_package_external_fields(order_id, package_id)

    async def mark_labels_printed(
        self,
        order_id: str,
        label_codes: list[str] | None = None,
    ) -> list[ReceivingLabel]:
        order = await self._get_order(order_id)
        result = await self.db.execute(
            select(ReceivingLabel)
            .where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order.id,
            )
            .order_by(ReceivingLabel.created_at.asc())
        )
        labels = list(result.scalars())
        if label_codes:
            requested = set(label_codes)
            labels = [label for label in labels if label.label_code in requested]
        now = datetime.now(UTC)
        for label in labels:
            extra = dict(label.extra_data or {})
            extra["print_count"] = int(extra.get("print_count", 0)) + 1
            label.extra_data = extra
            label.printed_at = now
        await self.db.flush()
        return labels

    async def complete_receiving(self, order_id: str, user_id: str | None = None) -> dict:
        """
        Complete receiving and generate putaway tasks for all received items.
        Transitions order to PUTAWAY status.
        """
        order = await self._get_order(order_id)
        if order.status != InboundStatus.RECEIVING.value:
            raise self._receiving_error(
                status_code=status.HTTP_409_CONFLICT,
                code=ReceivingErrorCode.ORDER_NOT_RECEIVING,
                message=(
                    "Only inbound orders in receiving can be completed and released to putaway. "
                    f"This inbound order is currently {order.status}."
                ),
            )
        created_tasks = 0
        putaway_units = 0
        execution_service = PutawayExecutionService(self.db, self.tenant_id)

        open_packages = (
            (
                await self.db.execute(
                    select(InboundPackage)
                    .where(
                        InboundPackage.tenant_id == self.tenant_id,
                        InboundPackage.order_id == order_id,
                        InboundPackage.status.in_(
                            [
                                InboundPackageStatus.EXPECTED.value,
                                InboundPackageStatus.RECEIVING.value,
                            ]
                        ),
                        InboundPackage.received_qty <= 0,
                        InboundPackage.damaged_qty <= 0,
                    )
                    .order_by(InboundPackage.package_number.asc())
                )
            )
            .scalars()
            .all()
        )
        if open_packages:
            package_names = ", ".join(
                f"package {package.package_number}" for package in open_packages[:3]
            )
            remaining = len(open_packages) - min(len(open_packages), 3)
            suffix = f" and {remaining} more" if remaining else ""
            raise self._receiving_error(
                status_code=status.HTTP_409_CONFLICT,
                code=ReceivingErrorCode.OPEN_PACKAGES_REMAIN,
                message=(
                    "Finish receiving every expected package before completing this inbound "
                    f"order. Still open: {package_names}{suffix}."
                ),
            )

        handling_units = (
            (
                await self.db.execute(
                    select(HandlingUnit).where(
                        HandlingUnit.tenant_id == self.tenant_id,
                        HandlingUnit.order_id == order_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        received_handling_units = [
            handling_unit
            for handling_unit in handling_units
            if int(handling_unit.received_qty or 0) > 0
        ]
        missing_source_units = [
            handling_unit
            for handling_unit in received_handling_units
            if not handling_unit.staging_location_id
        ]
        if missing_source_units:
            package_ids = [
                handling_unit.inbound_package_id
                for handling_unit in missing_source_units
                if handling_unit.inbound_package_id
            ]
            packages_by_id: dict[str, InboundPackage] = {}
            if package_ids:
                package_result = await self.db.execute(
                    select(InboundPackage).where(
                        InboundPackage.tenant_id == self.tenant_id,
                        InboundPackage.id.in_(package_ids),
                    )
                )
                packages_by_id = {package.id: package for package in package_result.scalars()}

            line_ids = [handling_unit.order_line_id for handling_unit in missing_source_units]
            lines_by_id: dict[str, InboundOrderLine] = {}
            if line_ids:
                line_result = await self.db.execute(
                    select(InboundOrderLine).where(
                        InboundOrderLine.tenant_id == self.tenant_id,
                        InboundOrderLine.id.in_(line_ids),
                    )
                )
                lines_by_id = {line.id: line for line in line_result.scalars()}

            unresolved_units: list[HandlingUnit] = []
            for handling_unit in missing_source_units:
                package = (
                    packages_by_id.get(handling_unit.inbound_package_id)
                    if handling_unit.inbound_package_id
                    else None
                )
                line = lines_by_id.get(handling_unit.order_line_id)
                recovered_source_id = (
                    package.staging_location_id
                    if package and package.staging_location_id
                    else line.staging_location_id
                    if line and line.staging_location_id
                    else None
                )
                if recovered_source_id:
                    handling_unit.staging_location_id = recovered_source_id
                else:
                    unresolved_units.append(handling_unit)

            if unresolved_units:
                unit_codes = ", ".join(
                    handling_unit.unit_code for handling_unit in unresolved_units[:3]
                )
                raise self._receiving_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code=ReceivingErrorCode.STAGING_LOCATION_REQUIRED,
                    message=(
                        "Confirm a staging location for every received package before completing "
                        f"receiving. Missing source for {unit_codes}."
                    ),
                )

        source_location_ids = {
            handling_unit.staging_location_id
            for handling_unit in received_handling_units
            if handling_unit.staging_location_id
        }
        if source_location_ids:
            location_result = await self.db.execute(
                select(Location.id).where(
                    Location.tenant_id == self.tenant_id,
                    Location.warehouse_id == order.warehouse_id,
                    Location.id.in_(source_location_ids),
                )
            )
            valid_location_ids = set(location_result.scalars())
            invalid_location_ids = source_location_ids - valid_location_ids
            if invalid_location_ids:
                raise self._receiving_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code=ReceivingErrorCode.STAGING_LOCATION_REQUIRED,
                    message=(
                        "One or more received packages point to a staging location that no longer "
                        "exists in this warehouse. Correct the receipt before completing receiving."
                    ),
                )

        order.status = InboundStatus.PUTAWAY.value
        for handling_unit in handling_units:
            good_qty = int(handling_unit.received_qty or 0)
            if good_qty <= 0:
                continue
            existing_task_id = await self.db.scalar(
                select(Task.id).where(
                    Task.tenant_id == self.tenant_id,
                    Task.task_type == TaskType.PUTAWAY.value,
                    Task.reference_type == "inbound_order",
                    Task.reference_id == order_id,
                    Task.handling_unit_id == handling_unit.id,
                )
            )
            if existing_task_id:
                continue
            execution = await execution_service.decide(
                warehouse_id=order.warehouse_id,
                source_location_id=handling_unit.staging_location_id,
                handling_unit_id=handling_unit.id,
            )
            task = Task(
                tenant_id=self.tenant_id,
                warehouse_id=order.warehouse_id,
                task_type=TaskType.PUTAWAY.value,
                status=TaskStatus.PENDING.value,
                priority=5,
                sku_id=handling_unit.sku_id,
                quantity=good_qty,
                handling_unit_id=handling_unit.id,
                execution_mode=execution.mode,
                source_location_id=handling_unit.staging_location_id,
                reference_type="inbound_order",
                reference_id=order_id,
                assigned_type=AssignedType.UNASSIGNED.value,
            )
            try:
                async with self.db.begin_nested():
                    self.db.add(task)
                    await self.db.flush()
            except IntegrityError as exc:
                if not self._is_putaway_task_unique_violation(exc):
                    raise
                continue
            created_tasks += 1
            putaway_units += good_qty

        for handling_unit in handling_units:
            if handling_unit.received_qty > 0:
                handling_unit.status = "putaway_pending"
                if handling_unit.inbound_package_id:
                    package = await self.db.get(InboundPackage, handling_unit.inbound_package_id)
                    if package and package.tenant_id == self.tenant_id:
                        package.status = InboundPackageStatus.PUTAWAY_PENDING.value

        await self.db.flush()
        return {
            "order": order,
            "created_tasks": created_tasks,
            "putaway_units": putaway_units,
        }

    async def void_inbound_order(self, order_id: str, user_id: str | None = None) -> InboundOrder:
        order = await self._get_order(order_id)
        if order.status in {InboundStatus.PUTAWAY.value, InboundStatus.COMPLETED.value}:
            raise HTTPException(
                status_code=409, detail="Completed or putaway inbound orders cannot be voided"
            )
        if await self._has_confirmed_receipt_artifacts(order_id):
            raise HTTPException(
                status_code=409,
                detail="Inbound orders with confirmed receipt, internal labels, or inventory movements must be archived instead of voided",
            )

        extra = dict(order.extra_data or {})
        extra["voided"] = True
        extra["voided_at"] = datetime.now(UTC).isoformat()
        extra["voided_by"] = user_id
        order.extra_data = extra
        order.status = InboundStatus.CANCELLED.value
        await self.db.flush()
        return order

    async def set_inbound_order_archived(
        self,
        order_id: str,
        archived: bool,
        user_id: str | None = None,
    ) -> InboundOrder:
        order = await self._get_order(order_id)
        if order.status == InboundStatus.RECEIVING.value and archived:
            raise HTTPException(
                status_code=409, detail="Inbound orders in live receiving cannot be archived"
            )

        extra = dict(order.extra_data or {})
        extra["archived"] = archived
        if archived:
            extra["archived_at"] = datetime.now(UTC).isoformat()
            extra["archived_by"] = user_id
        else:
            extra.pop("archived_at", None)
            extra.pop("archived_by", None)
        order.extra_data = extra
        await self.db.flush()
        return order

    async def delete_inbound_order(self, order_id: str) -> None:
        order = await self._get_order(order_id)
        if order.status not in {
            InboundStatus.DRAFT.value,
            InboundStatus.EXPECTED.value,
            InboundStatus.CANCELLED.value,
        }:
            raise HTTPException(
                status_code=409,
                detail="Only draft, expected, or voided inbound orders can be deleted permanently",
            )
        if await self._has_any_receiving_activity(order_id):
            raise HTTPException(
                status_code=409,
                detail="Inbound orders with scan, label, receipt, or inventory activity cannot be deleted permanently",
            )

        package_result = await self.db.execute(
            select(InboundPackage).where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
            )
        )
        for package in package_result.scalars().all():
            await self.db.delete(package)

        line_result = await self.db.execute(
            select(InboundOrderLine).where(
                InboundOrderLine.tenant_id == self.tenant_id,
                InboundOrderLine.order_id == order_id,
            )
        )
        for line in line_result.scalars().all():
            await self.db.delete(line)
        await self.db.delete(order)
        await self.db.flush()

    def _receiving_error(self, status_code: int, code: str, message: str) -> HTTPException:
        return HTTPException(
            status_code=status_code,
            detail={"code": code, "message": message},
        )

    async def _get_order_line(self, order_id: str, line_id: str) -> InboundOrderLine:
        result = await self.db.execute(
            select(InboundOrderLine)
            .join(InboundOrder, InboundOrder.id == InboundOrderLine.order_id)
            .where(
                InboundOrderLine.id == line_id,
                InboundOrderLine.order_id == order_id,
                InboundOrder.tenant_id == self.tenant_id,
            )
        )
        line = result.scalar_one_or_none()
        if not line:
            raise HTTPException(status_code=404, detail="Inbound order line not found")
        return line

    async def _resolve_receipt_lot(
        self,
        line: InboundOrderLine,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
    ) -> tuple[str | None, datetime | None]:
        effective_lot = (lot_number or line.lot_number or "").strip() or None
        effective_expiry = expiry_date or line.expiry_date

        if effective_lot and effective_lot != line.lot_number:
            line.lot_number = effective_lot
        if effective_expiry and effective_expiry != line.expiry_date:
            line.expiry_date = effective_expiry
        return effective_lot, effective_expiry

    async def _get_package(self, order_id: str, package_id: str) -> InboundPackage:
        package = await self.db.scalar(
            select(InboundPackage).where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
                InboundPackage.id == package_id,
            )
        )
        if not package:
            raise HTTPException(status_code=404, detail="Inbound package not found")
        return package

    async def _get_next_package_number(self, order_id: str, line_id: str) -> int:
        current = await self.db.scalar(
            select(func.coalesce(func.max(InboundPackage.package_number), 0)).where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
                InboundPackage.order_line_id == line_id,
            )
        )
        return int(current or 0) + 1

    async def _get_line_packages(self, order_id: str, line_id: str) -> list[InboundPackage]:
        result = await self.db.execute(
            select(InboundPackage)
            .where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
                InboundPackage.order_line_id == line_id,
            )
            .order_by(InboundPackage.package_number.asc())
        )
        return list(result.scalars())

    async def _get_or_create_default_package(
        self,
        order: InboundOrder,
        line: InboundOrderLine,
        create_if_missing: bool = True,
    ) -> InboundPackage:
        packages = await self._get_line_packages(order.id, line.id)
        if packages:
            open_packages = [
                package
                for package in packages
                if package.status
                not in {
                    InboundPackageStatus.RECEIVED.value,
                    InboundPackageStatus.STAGED.value,
                    InboundPackageStatus.PUTAWAY_PENDING.value,
                    InboundPackageStatus.STORED.value,
                }
            ]
            if len(open_packages) == 1:
                return open_packages[0]
            if len(open_packages) > 1:
                raise HTTPException(
                    status_code=409,
                    detail="This inbound line has multiple open packages. Use package-level receiving instead of the line shortcut.",
                )
            return packages[-1]

        if not create_if_missing:
            return InboundPackage(
                tenant_id=self.tenant_id,
                order_id=order.id,
                order_line_id=line.id,
                package_number=1,
                package_type="carton",
                status=InboundPackageStatus.EXPECTED.value,
                expected_qty=line.quantity_expected,
                external_tracking_number=line.external_tracking_number,
                external_carton_mark=line.external_carton_mark,
                external_customer_barcode=line.external_customer_barcode,
            )

        package = InboundPackage(
            tenant_id=self.tenant_id,
            order_id=order.id,
            order_line_id=line.id,
            package_number=1,
            package_type="carton",
            status=InboundPackageStatus.EXPECTED.value,
            expected_qty=line.quantity_expected,
            external_tracking_number=line.external_tracking_number,
            external_carton_mark=line.external_carton_mark,
            external_customer_barcode=line.external_customer_barcode,
        )
        self.db.add(package)
        await self.db.flush()
        return package

    async def _choose_label_sequence(
        self,
        order_id: str,
        preferred_sequence: int | None = None,
    ) -> int:
        used_rows = await self.db.execute(
            select(InboundPackage.label_sequence).where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
                InboundPackage.label_sequence.is_not(None),
            )
        )
        used = {int(value) for value in used_rows.scalars().all() if value is not None}
        reserved_rows = await self.db.execute(
            select(InboundOrderLine.line_number).where(
                InboundOrderLine.tenant_id == self.tenant_id,
                InboundOrderLine.order_id == order_id,
            )
        )
        reserved = {int(value) for value in reserved_rows.scalars().all() if value is not None}
        if preferred_sequence is not None and preferred_sequence not in used:
            return preferred_sequence

        blocked = used | reserved
        candidate = 1
        while candidate in blocked:
            candidate += 1
        return candidate

    async def _assign_package_label_sequence(
        self,
        order: InboundOrder,
        line: InboundOrderLine,
        package: InboundPackage,
    ) -> int:
        if package.label_sequence is not None:
            return int(package.label_sequence)
        preferred = line.line_number if package.package_number == 1 else None
        package.label_sequence = await self._choose_label_sequence(
            order.id, preferred_sequence=preferred
        )
        await self.db.flush()
        return int(package.label_sequence)

    async def _predict_package_label_code(
        self,
        order: InboundOrder,
        line: InboundOrderLine,
        package: InboundPackage,
    ) -> str:
        rules = await self._get_receiving_code_rules()
        sequence = package.label_sequence
        if sequence is None:
            preferred = line.line_number if package.package_number == 1 else None
            sequence = await self._choose_label_sequence(order.id, preferred_sequence=preferred)
        return self._build_label_code(order.order_number, int(sequence), rules)

    def _validate_package_receipt_input(
        self,
        quantity_received: int,
        quantity_damaged: int,
        staging_location_id: str | None,
    ) -> int:
        if quantity_received < 0 or quantity_damaged < 0:
            raise self._receiving_error(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code=ReceivingErrorCode.INVALID_QUANTITY,
                message="Received and damaged quantities cannot be negative.",
            )
        if quantity_damaged > quantity_received:
            raise self._receiving_error(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code=ReceivingErrorCode.INVALID_DAMAGED_QTY,
                message="Damaged quantity cannot exceed received quantity.",
            )
        if quantity_received == 0 and quantity_damaged == 0:
            raise self._receiving_error(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code=ReceivingErrorCode.NOTHING_RECEIVED,
                message="Enter at least one received or damaged unit.",
            )

        good_qty = quantity_received - quantity_damaged
        if good_qty > 0 and not staging_location_id:
            raise self._receiving_error(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code=ReceivingErrorCode.STAGING_LOCATION_REQUIRED,
                message="A staging location is required when receiving good units.",
            )
        return good_qty

    async def _record_package_receipt(
        self,
        order: InboundOrder,
        line: InboundOrderLine,
        package: InboundPackage,
        quantity_received: int,
        quantity_damaged: int = 0,
        staging_location_id: str | None = None,
        pallet_count: int | None = None,
        rent_free_days: int | None = None,
        measured_weight_kg: float | None = None,
        measured_length_cm: float | None = None,
        measured_width_cm: float | None = None,
        measured_height_cm: float | None = None,
        package_count: int | None = None,
        receiving_note: str | None = None,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
        receiving_label_code: str | None = None,
    ) -> dict:
        good_qty = self._validate_package_receipt_input(
            quantity_received=quantity_received,
            quantity_damaged=quantity_damaged,
            staging_location_id=staging_location_id,
        )

        package.status = InboundPackageStatus.RECEIVING.value
        package.received_qty = quantity_received
        package.damaged_qty = quantity_damaged
        package.staging_location_id = staging_location_id or package.staging_location_id
        package.measured_weight_kg = measured_weight_kg
        package.pallet_count = pallet_count
        package.rent_free_days = rent_free_days
        package.measured_length_cm = measured_length_cm
        package.measured_width_cm = measured_width_cm
        package.measured_height_cm = measured_height_cm
        package.package_count = package_count
        package.note = receiving_note
        package.confirmed_at = datetime.now(UTC)

        effective_staging_location_id = staging_location_id or package.staging_location_id
        if effective_staging_location_id and good_qty > 0:
            await self._add_inventory(
                order_id=order.id,
                client_id=order.client_id,
                warehouse_id=order.warehouse_id,
                location_id=effective_staging_location_id,
                sku_id=line.sku_id,
                quantity=good_qty,
                lot_number=lot_number,
                expiry_date=expiry_date,
                user_id=user_id,
                receiving_label_code=receiving_label_code,
            )

        package.status = (
            InboundPackageStatus.STAGED.value
            if effective_staging_location_id and good_qty > 0
            else InboundPackageStatus.RECEIVED.value
        )
        await self._sync_line_receipt_summary(line.id)
        await self.db.flush()

        discrepancy = quantity_received - package.expected_qty
        return {
            "line_id": line.id,
            "package_id": package.id,
            "package_number": package.package_number,
            "expected": package.expected_qty,
            "received": quantity_received,
            "damaged": quantity_damaged,
            "discrepancy": discrepancy,
            "status": "over" if discrepancy > 0 else "short" if discrepancy < 0 else "exact",
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
        }

    async def _sync_line_receipt_summary(self, line_id: str) -> None:
        line = await self.db.scalar(
            select(InboundOrderLine).where(
                InboundOrderLine.tenant_id == self.tenant_id,
                InboundOrderLine.id == line_id,
            )
        )
        if not line:
            return
        packages = await self._get_line_packages(line.order_id, line.id)
        line.quantity_received = sum(int(package.received_qty or 0) for package in packages)
        line.quantity_damaged = sum(int(package.damaged_qty or 0) for package in packages)
        line.staging_location_id = next(
            (
                package.staging_location_id
                for package in reversed(packages)
                if package.staging_location_id
            ),
            None,
        )
        line.package_count = sum(int(package.package_count or 0) for package in packages) or None
        line.pallet_count = sum(int(package.pallet_count or 0) for package in packages) or None
        line.rent_free_days = next(
            (
                package.rent_free_days
                for package in reversed(packages)
                if package.rent_free_days is not None
            ),
            None,
        )
        line.measured_weight_kg = (
            sum(float(package.measured_weight_kg or 0) for package in packages) or None
        )
        line.measured_length_cm = next(
            (
                package.measured_length_cm
                for package in reversed(packages)
                if package.measured_length_cm is not None
            ),
            None,
        )
        line.measured_width_cm = next(
            (
                package.measured_width_cm
                for package in reversed(packages)
                if package.measured_width_cm is not None
            ),
            None,
        )
        line.measured_height_cm = next(
            (
                package.measured_height_cm
                for package in reversed(packages)
                if package.measured_height_cm is not None
            ),
            None,
        )
        line.receiving_note = next(
            (package.note for package in reversed(packages) if package.note), None
        )

    def _apply_observed_code_to_package(
        self, package: InboundPackage, code_value: str, code_type: str
    ) -> None:
        if code_type == "tracking_number":
            package.external_tracking_number = code_value
        elif code_type == "carton_mark":
            package.external_carton_mark = code_value
        elif code_type == "customer_barcode":
            package.external_customer_barcode = code_value

    async def _refresh_package_external_fields(self, order_id: str, package_id: str) -> None:
        package = await self._get_package(order_id, package_id)
        result = await self.db.execute(
            select(ReceivingObservedCode)
            .where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.inbound_package_id == package_id,
            )
            .order_by(
                ReceivingObservedCode.is_primary.desc(), ReceivingObservedCode.created_at.asc()
            )
        )
        observed_codes = list(result.scalars())
        package.external_tracking_number = next(
            (code.code_value for code in observed_codes if code.code_type == "tracking_number"),
            None,
        )
        package.external_carton_mark = next(
            (code.code_value for code in observed_codes if code.code_type == "carton_mark"), None
        )
        package.external_customer_barcode = next(
            (code.code_value for code in observed_codes if code.code_type == "customer_barcode"),
            None,
        )

    async def _get_order(self, order_id: str) -> InboundOrder:
        result = await self.db.execute(
            select(InboundOrder).where(
                InboundOrder.id == order_id,
                InboundOrder.tenant_id == self.tenant_id,
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Inbound order not found")
        return order

    async def _has_confirmed_receipt_artifacts(self, order_id: str) -> bool:
        line_result = await self.db.execute(
            select(InboundOrderLine).where(
                InboundOrderLine.tenant_id == self.tenant_id,
                InboundOrderLine.order_id == order_id,
            )
        )
        for line in line_result.scalars().all():
            if (line.quantity_received or 0) > 0 or (line.quantity_damaged or 0) > 0:
                return True

        package_existing = await self.db.scalar(
            select(InboundPackage.id).where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
                ((InboundPackage.received_qty > 0) | (InboundPackage.damaged_qty > 0)),
            )
        )
        if package_existing:
            return True

        for model in (ReceivingLabel, HandlingUnit):
            existing = await self.db.scalar(
                select(model.id).where(
                    model.tenant_id == self.tenant_id,
                    model.order_id == order_id,
                )
            )
            if existing:
                return True

        for model, field in (
            (InventoryTransaction, InventoryTransaction.reference_id),
            (Task, Task.reference_id),
        ):
            existing = await self.db.scalar(
                select(model.id).where(
                    model.tenant_id == self.tenant_id,
                    field == order_id,
                    model.reference_type == "inbound_order",
                )
            )
            if existing:
                return True
        return False

    async def _has_any_receiving_activity(self, order_id: str) -> bool:
        if await self._has_confirmed_receipt_artifacts(order_id):
            return True

        observed = await self.db.scalar(
            select(ReceivingObservedCode.id).where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
            )
        )
        if observed:
            return True

        package = await self.db.scalar(
            select(InboundPackage.id).where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
            )
        )
        return bool(package)

    async def _add_inventory(
        self,
        order_id: str,
        client_id: str,
        warehouse_id: str,
        location_id: str,
        sku_id: str,
        quantity: int,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
        receiving_label_code: str | None = None,
    ) -> Inventory:
        """Add inventory at a location and record the transaction."""
        query = select(Inventory).where(
            Inventory.tenant_id == self.tenant_id,
            Inventory.location_id == location_id,
            Inventory.sku_id == sku_id,
        )
        if lot_number:
            query = query.where(Inventory.lot_number == lot_number)

        result = await self.db.execute(query)
        inv = ensure_inventory(
            self.db,
            result.scalar_one_or_none(),
            tenant_id=self.tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            sku_id=sku_id,
            lot_number=lot_number,
            expiry_date=expiry_date,
            received_at=datetime.now(UTC),
        )

        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=client_id,
            transaction_type=TransactionType.RECEIVE.value,
            sku_id=sku_id,
            location_id=location_id,
            quantity_change=quantity,
            inventory=inv,
            delta_on_hand=quantity,
            to_location_id=location_id,
            reference_type="inbound_order",
            reference_id=order_id,
            performed_by=user_id,
            lot_number=lot_number,
            notes=f"Receiving label {receiving_label_code}" if receiving_label_code else None,
        )
        return inv

    async def _apply_inventory_delta(
        self,
        *,
        order_id: str,
        client_id: str,
        warehouse_id: str,
        location_id: str,
        sku_id: str,
        quantity_delta: int,
        lot_number: str | None = None,
        expiry_date: datetime | None = None,
        user_id: str | None = None,
        notes: str | None = None,
    ) -> Inventory | None:
        """Apply a signed inventory adjustment and append an immutable transaction."""
        if quantity_delta == 0:
            return None

        query = select(Inventory).where(
            Inventory.tenant_id == self.tenant_id,
            Inventory.location_id == location_id,
            Inventory.sku_id == sku_id,
        )
        if lot_number:
            query = query.where(Inventory.lot_number == lot_number)

        inv = (await self.db.execute(query)).scalar_one_or_none()
        if inv:
            if quantity_delta < 0 and inv.quantity_on_hand < abs(quantity_delta):
                raise HTTPException(
                    status_code=409,
                    detail="Receipt correction would make staging inventory negative",
                )
        else:
            if quantity_delta < 0:
                raise HTTPException(
                    status_code=409,
                    detail="Receipt correction inventory was not found at the original staging location",
                )
            inv = ensure_inventory(
                self.db,
                None,
                tenant_id=self.tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id=location_id,
                sku_id=sku_id,
                lot_number=lot_number,
                expiry_date=expiry_date,
                received_at=datetime.now(UTC),
            )

        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=client_id,
            transaction_type=TransactionType.ADJUST.value,
            sku_id=sku_id,
            location_id=location_id,
            quantity_change=quantity_delta,
            inventory=inv,
            delta_on_hand=quantity_delta,
            to_location_id=location_id if quantity_delta > 0 else None,
            from_location_id=location_id if quantity_delta < 0 else None,
            reference_type="inbound_order",
            reference_id=order_id,
            performed_by=user_id,
            lot_number=lot_number,
            notes=notes,
        )
        return inv

    async def _resolve_receipt_target(
        self,
        order_id: str,
        scanned_code: str,
    ) -> tuple[ReceivingLabel | None, InboundOrderLine, InboundPackage, str, str]:
        scanned_code = self._normalize_scanned_code(scanned_code)
        result = await self.db.execute(
            select(ReceivingLabel, InboundOrderLine, InboundPackage)
            .join(InboundOrderLine, InboundOrderLine.id == ReceivingLabel.order_line_id)
            .outerjoin(InboundPackage, InboundPackage.id == ReceivingLabel.inbound_package_id)
            .where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order_id,
                ReceivingLabel.label_code == scanned_code,
            )
        )
        row = result.one_or_none()
        if row:
            label, line, package = row
            if not package:
                package = await self._get_or_create_default_package(
                    await self._get_order(order_id), line
                )
            return label, line, package, "label_code", label.label_code

        order = await self._get_order(order_id)

        observed_codes = (
            (
                await self.db.execute(
                    select(ReceivingObservedCode)
                    .where(
                        ReceivingObservedCode.tenant_id == self.tenant_id,
                        ReceivingObservedCode.order_id == order_id,
                        ReceivingObservedCode.code_value == scanned_code,
                    )
                    .order_by(ReceivingObservedCode.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        if observed_codes:
            package_ids = {
                code.inbound_package_id for code in observed_codes if code.inbound_package_id
            }
            line_ids = {code.order_line_id for code in observed_codes if code.order_line_id}
            if len(package_ids) > 1 or len(line_ids) > 1:
                raise HTTPException(
                    status_code=409,
                    detail="Scanned code matches multiple inbound packages. Open the package directly or use the generated internal label.",
                )
            observed = observed_codes[0]
            line = await self._get_order_line(order_id, observed.order_line_id)
            package = (
                await self._get_package(order_id, observed.inbound_package_id)
                if observed.inbound_package_id
                else await self._get_or_create_default_package(order, line)
            )
            label = await self.db.scalar(
                select(ReceivingLabel).where(
                    ReceivingLabel.tenant_id == self.tenant_id,
                    ReceivingLabel.order_id == order_id,
                    ReceivingLabel.inbound_package_id == package.id,
                )
            )
            matched_by = self._map_code_type_to_match(observed.code_type)
            resolved_label_code = (
                label.label_code
                if label
                else await self._predict_package_label_code(order, line, package)
            )
            return label, line, package, matched_by, resolved_label_code

        package_result = await self.db.execute(
            select(InboundPackage, InboundOrderLine)
            .join(InboundOrderLine, InboundOrderLine.id == InboundPackage.order_line_id)
            .where(
                InboundPackage.tenant_id == self.tenant_id,
                InboundPackage.order_id == order_id,
                (InboundPackage.external_tracking_number == scanned_code)
                | (InboundPackage.external_carton_mark == scanned_code)
                | (InboundPackage.external_customer_barcode == scanned_code),
            )
        )
        package_rows = list(package_result.all())
        if len(package_rows) == 1:
            package, line = package_rows[0]
            label = await self.db.scalar(
                select(ReceivingLabel).where(
                    ReceivingLabel.tenant_id == self.tenant_id,
                    ReceivingLabel.order_id == order_id,
                    ReceivingLabel.inbound_package_id == package.id,
                )
            )
            if package.external_tracking_number == scanned_code:
                matched_by = "external_tracking_number"
            elif package.external_carton_mark == scanned_code:
                matched_by = "external_carton_mark"
            else:
                matched_by = "external_customer_barcode"
            resolved_label_code = (
                label.label_code
                if label
                else await self._predict_package_label_code(order, line, package)
            )
            return label, line, package, matched_by, resolved_label_code
        if len(package_rows) > 1:
            raise HTTPException(
                status_code=409,
                detail="Scanned code matches multiple inbound packages. Use a package-specific or internal label instead.",
            )

        line_result = await self.db.execute(
            select(InboundOrderLine).where(
                InboundOrderLine.order_id == order_id,
                InboundOrderLine.tenant_id == self.tenant_id,
            )
        )
        lines = list(line_result.scalars())
        for line in lines:
            preview_package = await self._get_or_create_default_package(
                order, line, create_if_missing=False
            )
            predicted_code = await self._predict_package_label_code(order, line, preview_package)
            if scanned_code == predicted_code:
                package = await self._get_or_create_default_package(order, line)
                return None, line, package, "label_code", predicted_code

        result = await self.db.execute(
            select(InboundOrderLine).where(
                InboundOrderLine.tenant_id == self.tenant_id,
                InboundOrderLine.order_id == order_id,
                (InboundOrderLine.external_tracking_number == scanned_code)
                | (InboundOrderLine.external_carton_mark == scanned_code)
                | (InboundOrderLine.external_customer_barcode == scanned_code),
            )
        )
        lines = list(result.scalars())
        if not lines:
            raise HTTPException(
                status_code=404, detail="Receiving label not found for this inbound order"
            )
        if len(lines) > 1:
            raise HTTPException(
                status_code=409,
                detail="Scanned code matches multiple receiving labels. Use the system label or narrow the carton reference.",
            )

        line = lines[0]
        package = await self._get_or_create_default_package(order, line)
        existing_label = await self.db.scalar(
            select(ReceivingLabel).where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order_id,
                ReceivingLabel.inbound_package_id == package.id,
            )
        )
        if line.external_tracking_number == scanned_code:
            matched_by = "external_tracking_number"
        elif line.external_carton_mark == scanned_code:
            matched_by = "external_carton_mark"
        else:
            matched_by = "external_customer_barcode"
        return (
            existing_label,
            line,
            package,
            matched_by,
            (
                existing_label.label_code
                if existing_label
                else await self._predict_package_label_code(order, line, package)
            ),
        )

    def _normalize_scanned_code(self, scanned_code: str) -> str:
        value = scanned_code.strip()
        if not value:
            return value
        prefix, separator, rest = value.partition(":")
        if not separator:
            prefix, separator, rest = value.partition("：")
        if not separator:
            return value
        known_prefixes = {
            "tracking",
            "track",
            "carton",
            "customer",
            "internal",
            "label",
            "barcode",
            "code",
            "ref",
            "reference",
            "追踪",
            "跟踪",
            "箱号",
            "箱唛",
            "客户",
            "内部",
            "条码",
            "代码",
        }
        return rest.strip() if prefix.strip().lower() in known_prefixes else value

    async def _ensure_internal_receipt_objects(
        self,
        order: InboundOrder,
        line: InboundOrderLine,
        package: InboundPackage,
    ) -> tuple[ReceivingLabel, HandlingUnit]:
        label = await self.db.scalar(
            select(ReceivingLabel).where(
                ReceivingLabel.tenant_id == self.tenant_id,
                ReceivingLabel.order_id == order.id,
                ReceivingLabel.inbound_package_id == package.id,
            )
        )
        if not label:
            code_rules = await self._get_receiving_code_rules()
            sequence = await self._assign_package_label_sequence(order, line, package)
            label = ReceivingLabel(
                tenant_id=self.tenant_id,
                order_id=order.id,
                order_line_id=line.id,
                inbound_package_id=package.id,
                sku_id=line.sku_id,
                label_code=self._build_label_code(order.order_number, sequence, code_rules),
                external_tracking_number=package.external_tracking_number
                or line.external_tracking_number,
                external_carton_mark=package.external_carton_mark or line.external_carton_mark,
                external_customer_barcode=package.external_customer_barcode
                or line.external_customer_barcode,
                label_type=package.package_type,
                expected_qty=package.expected_qty,
                received_qty=0,
                status="pending",
                lot_number=line.lot_number,
                expiry_date=line.expiry_date,
            )
            self.db.add(label)
            await self.db.flush()

        handling_unit = await self.db.scalar(
            select(HandlingUnit).where(
                HandlingUnit.tenant_id == self.tenant_id,
                HandlingUnit.order_id == order.id,
                HandlingUnit.inbound_package_id == package.id,
            )
        )
        if not handling_unit:
            handling_unit = HandlingUnit(
                tenant_id=self.tenant_id,
                order_id=order.id,
                order_line_id=line.id,
                inbound_package_id=package.id,
                receiving_label_id=label.id,
                sku_id=line.sku_id,
                unit_code=label.label_code,
                unit_type=package.package_type,
                expected_qty=package.expected_qty,
                received_qty=0,
                damaged_qty=0,
                status="expected",
                staging_location_id=package.staging_location_id or line.staging_location_id,
                lot_number=line.lot_number,
                expiry_date=line.expiry_date,
                external_tracking_number=package.external_tracking_number
                or line.external_tracking_number,
                external_carton_mark=package.external_carton_mark or line.external_carton_mark,
                external_customer_barcode=package.external_customer_barcode
                or line.external_customer_barcode,
            )
            self.db.add(handling_unit)
            await self.db.flush()
        elif handling_unit.receiving_label_id != label.id:
            handling_unit.receiving_label_id = label.id

        return label, handling_unit

    async def _capture_observed_code(
        self,
        order_id: str,
        line_id: str,
        package_id: str,
        receiving_label_id: str | None,
        scanned_code: str,
        matched_by: str,
        source: str,
    ) -> list[ReceivingObservedCode]:
        normalized_code = scanned_code.strip()
        if not normalized_code:
            return []

        code_type = self._map_matched_by_to_code_type(matched_by)
        if code_type != "receiving_label":
            existing = await self.db.scalar(
                select(ReceivingObservedCode).where(
                    ReceivingObservedCode.tenant_id == self.tenant_id,
                    ReceivingObservedCode.order_id == order_id,
                    ReceivingObservedCode.order_line_id == line_id,
                    ReceivingObservedCode.inbound_package_id == package_id,
                    ReceivingObservedCode.receiving_label_id == receiving_label_id,
                    ReceivingObservedCode.code_value == normalized_code,
                )
            )
            if not existing:
                is_primary = not bool(
                    await self.db.scalar(
                        select(ReceivingObservedCode.id).where(
                            ReceivingObservedCode.tenant_id == self.tenant_id,
                            ReceivingObservedCode.order_id == order_id,
                            ReceivingObservedCode.order_line_id == line_id,
                            ReceivingObservedCode.inbound_package_id == package_id,
                            ReceivingObservedCode.receiving_label_id == receiving_label_id,
                            ReceivingObservedCode.is_primary == True,  # noqa: E712
                        )
                    )
                )
                self.db.add(
                    ReceivingObservedCode(
                        tenant_id=self.tenant_id,
                        order_id=order_id,
                        order_line_id=line_id,
                        inbound_package_id=package_id,
                        receiving_label_id=receiving_label_id,
                        code_value=normalized_code,
                        code_type=code_type,
                        source=source,
                        is_primary=is_primary,
                        is_confirmed=False,
                    )
                )
                await self.db.flush()

        result = await self.db.execute(
            select(ReceivingObservedCode)
            .where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.order_line_id == line_id,
                ReceivingObservedCode.inbound_package_id == package_id,
            )
            .order_by(ReceivingObservedCode.created_at.asc())
        )
        return list(result.scalars())

    async def _confirm_observed_codes(
        self,
        order_id: str,
        line_id: str,
        package_id: str,
        receiving_label_id: str,
        handling_unit_id: str | None,
        package: InboundPackage,
        label: ReceivingLabel,
        handling_unit: HandlingUnit | None,
    ) -> list[ReceivingObservedCode]:
        result = await self.db.execute(
            select(ReceivingObservedCode)
            .where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.order_line_id == line_id,
                ReceivingObservedCode.inbound_package_id == package_id,
            )
            .order_by(ReceivingObservedCode.created_at.asc())
        )
        observed_codes = list(result.scalars())
        for observed in observed_codes:
            observed.inbound_package_id = package_id
            observed.receiving_label_id = receiving_label_id
            observed.handling_unit_id = handling_unit_id
            observed.is_confirmed = True

        self._sync_legacy_external_fields(package, label, handling_unit, observed_codes)
        return observed_codes

    def _sync_legacy_external_fields(
        self,
        package: InboundPackage,
        label: ReceivingLabel,
        handling_unit: HandlingUnit | None,
        observed_codes: list[ReceivingObservedCode],
    ) -> None:
        tracking = next(
            (code.code_value for code in observed_codes if code.code_type == "tracking_number"),
            None,
        )
        carton = next(
            (code.code_value for code in observed_codes if code.code_type == "carton_mark"), None
        )
        customer = next(
            (code.code_value for code in observed_codes if code.code_type == "customer_barcode"),
            None,
        )
        if tracking:
            package.external_tracking_number = tracking
            label.external_tracking_number = tracking
            if handling_unit:
                handling_unit.external_tracking_number = tracking
        if carton:
            package.external_carton_mark = carton
            label.external_carton_mark = carton
            if handling_unit:
                handling_unit.external_carton_mark = carton
        if customer:
            package.external_customer_barcode = customer
            label.external_customer_barcode = customer
            if handling_unit:
                handling_unit.external_customer_barcode = customer

    async def _get_observed_code(self, order_id: str, code_id: str) -> ReceivingObservedCode:
        observed = await self.db.scalar(
            select(ReceivingObservedCode).where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.id == code_id,
            )
        )
        if not observed:
            raise HTTPException(status_code=404, detail="Observed receiving code not found")
        return observed

    async def _clear_primary_observed_code(
        self,
        order_id: str,
        line_id: str | None,
        package_id: str | None,
        receiving_label_id: str | None,
    ) -> None:
        result = await self.db.execute(
            select(ReceivingObservedCode).where(
                ReceivingObservedCode.tenant_id == self.tenant_id,
                ReceivingObservedCode.order_id == order_id,
                ReceivingObservedCode.order_line_id == line_id,
                ReceivingObservedCode.inbound_package_id == package_id,
                ReceivingObservedCode.receiving_label_id == receiving_label_id,
                ReceivingObservedCode.is_confirmed == False,  # noqa: E712
                ReceivingObservedCode.is_primary == True,  # noqa: E712
            )
        )
        for code in result.scalars():
            code.is_primary = False

    def _map_matched_by_to_code_type(self, matched_by: str) -> str:
        if matched_by == "external_tracking_number":
            return "tracking_number"
        if matched_by == "external_carton_mark":
            return "carton_mark"
        if matched_by == "external_customer_barcode":
            return "customer_barcode"
        return "receiving_label"

    def _map_code_type_to_match(self, code_type: str) -> str:
        if code_type == "tracking_number":
            return "external_tracking_number"
        if code_type == "carton_mark":
            return "external_carton_mark"
        if code_type == "customer_barcode":
            return "external_customer_barcode"
        return "label_code"

    def _serialize_observed_code(self, code: ReceivingObservedCode) -> dict:
        return {
            "id": code.id,
            "package_id": code.inbound_package_id,
            "code_value": code.code_value,
            "code_type": code.code_type,
            "source": code.source,
            "is_primary": code.is_primary,
            "is_confirmed": code.is_confirmed,
        }

    async def _get_receiving_code_rules(self) -> dict:
        tenant = await self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id))
        settings = dict((tenant.settings or {}).get("receiving_code_rules") or {}) if tenant else {}
        return {
            "prefix": str(settings.get("prefix") if settings.get("prefix") is not None else "RCV"),
            "separator": str(settings.get("separator"))
            if settings.get("separator") is not None
            else "-",
            "include_order_number": bool(settings.get("include_order_number", True)),
            "sequence_padding": max(1, min(int(settings.get("sequence_padding", 3)), 8)),
            "uppercase": bool(settings.get("uppercase", True)),
        }

    def _build_label_code(
        self, order_number: str, line_index: int, rules: dict | None = None
    ) -> str:
        payload = {
            "prefix": "RCV",
            "separator": "-",
            "include_order_number": True,
            "sequence_padding": 3,
            "uppercase": True,
        }
        if rules:
            payload.update(rules)

        uppercase = bool(payload.get("uppercase", True))
        raw_order = order_number.upper() if uppercase else order_number
        normalized_order = re.sub(r"[^A-Za-z0-9]+", "-", raw_order).strip("-")
        normalized_order = re.sub(r"-{2,}", "-", normalized_order) or "INBOUND"
        prefix_value = payload.get("prefix")
        prefix = str(prefix_value if prefix_value is not None else "RCV").strip() or "RCV"
        prefix = prefix.upper() if uppercase else prefix
        separator_value = payload.get("separator")
        separator = str(separator_value) if separator_value is not None else "-"
        sequence_padding_value = payload.get("sequence_padding", 3)
        if isinstance(sequence_padding_value, int):
            requested_padding = sequence_padding_value
        elif isinstance(sequence_padding_value, str):
            try:
                requested_padding = int(sequence_padding_value)
            except ValueError:
                requested_padding = 3
        else:
            requested_padding = 3
        sequence_padding = max(1, min(requested_padding, 8))

        parts = [prefix]
        if bool(payload.get("include_order_number", True)):
            parts.append(normalized_order)
        parts.append(f"{line_index:0{sequence_padding}d}")
        return separator.join(part for part in parts if part)
