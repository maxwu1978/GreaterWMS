"""Pack-list validation and persistence without receiving inventory."""

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.inventory import SKU
from app.models.order import InboundOrder, InboundOrderLine, InboundPackage
from app.models.pack_list import PackListDocument, PackListLine
from app.models.warehouse import Warehouse
from app.services.pack_list_import import (
    PACK_LIST_REQUIRED_FIELDS,
    parse_pack_list_source,
    parse_positive_quantity,
)
from app.services.receiving_service import ReceivingService


class PackListService:
    """Validate and persist customer Pack Lists as pre-arrival information."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def preview(self, args: dict[str, Any]) -> dict:
        parsed = parse_pack_list_source(
            file_name=str(args.get("file_name", "pack-list.csv") or "pack-list.csv"),
            source_text=str(args.get("source_text", "") or ""),
            mapping=args.get("mapping"),
            overrides={
                "order_number": args.get("order_number"),
                "client_code": args.get("client_code"),
                "warehouse_code": args.get("warehouse_code"),
            },
        )
        rows = parsed["rows"]
        errors: list[dict] = []
        warnings: list[dict] = []

        clients = list(
            (
                await self.db.execute(
                    select(Client).where(
                        Client.tenant_id == self.tenant_id,
                        Client.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        warehouses = list(
            (
                await self.db.execute(
                    select(Warehouse).where(
                        Warehouse.tenant_id == self.tenant_id,
                        Warehouse.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        skus = list(
            (
                await self.db.execute(select(SKU).where(SKU.tenant_id == self.tenant_id))
            ).scalars()
        )

        normalized_rows: list[dict] = []
        source_client_values: set[str] = set()
        source_warehouse_values: set[str] = set()
        source_order_values: set[str] = set()
        package_codes: set[str] = set()
        serial_numbers: set[str] = set()
        container_values: set[str] = set()

        for row_number, row in enumerate(rows, start=2):
            order_number = str(row.get("order_number") or "").strip()
            client_raw = str(row.get("client_code") or "").strip()
            warehouse_raw = str(row.get("warehouse_code") or "").strip()
            package_code = str(row.get("package_code") or "").strip()
            sku_code = str(row.get("sku_code") or "").strip()
            customer_sku = str(row.get("customer_sku") or "").strip() or None
            item_name = str(row.get("item_name") or "").strip() or None
            serial_number = str(row.get("serial_number") or "").strip() or None
            container_tracking = str(row.get("container_tracking") or "").strip() or None
            quantity_raw = str(row.get("quantity") or "").strip()
            quantity = parse_positive_quantity(quantity_raw, row_number)

            source_order_values.add(order_number)
            source_client_values.add(client_raw)
            source_warehouse_values.add(warehouse_raw)
            if container_tracking:
                container_values.add(container_tracking)

            missing = [
                field
                for field, value in (
                    ("order_number", order_number),
                    ("client_code", client_raw),
                    ("warehouse_code", warehouse_raw),
                    ("package_code", package_code),
                    ("sku_code", sku_code),
                    ("quantity", quantity_raw),
                )
                if not value
            ]
            if missing:
                errors.append({"row": row_number, "error": "Missing required Pack List fields", "fields": missing})
                continue
            if quantity is None:
                errors.append({"row": row_number, "error": "quantity must be a positive whole number"})
                continue
            if package_code in package_codes:
                errors.append({"row": row_number, "error": f"Duplicate package_code '{package_code}'"})
                continue
            package_codes.add(package_code)
            if serial_number:
                if serial_number in serial_numbers:
                    errors.append({"row": row_number, "error": f"Duplicate serial_number '{serial_number}'"})
                    continue
                serial_numbers.add(serial_number)

            client, client_match = self._resolve_client(client_raw, clients)
            if not client:
                errors.append({"row": row_number, "error": f"Client '{client_raw}' not found or ambiguous"})
                continue
            warehouse = self._resolve_warehouse(warehouse_raw, warehouses)
            if not warehouse:
                errors.append({"row": row_number, "error": f"Warehouse '{warehouse_raw}' not found"})
                continue
            sku, sku_match = self._resolve_sku(sku_code, customer_sku, client.id, skus)
            if not sku:
                errors.append({"row": row_number, "error": f"SKU '{sku_code}' not found for client '{client.code}'"})
                continue

            normalized_rows.append(
                {
                    "row_number": row_number,
                    "order_number": order_number,
                    "client_id": client.id,
                    "client_code": client.code,
                    "client_match": client_match,
                    "warehouse_id": warehouse.id,
                    "warehouse_code": warehouse.code,
                    "package_code": package_code,
                    "sku_id": sku.id,
                    "sku_code": sku.sku_code,
                    "sku_match": sku_match,
                    "quantity": quantity,
                    "customer_sku": customer_sku,
                    "item_name": item_name,
                    "serial_number": serial_number,
                    "container_tracking": container_tracking,
                    "line_number": self._positive_int(row.get("line_number")),
                    "raw_data": dict(row),
                }
            )

        if len(source_order_values) > 1:
            errors.append({"error": "All Pack List rows must use the same order_number"})
        if len(source_client_values) > 1:
            errors.append({"error": "All Pack List rows must use the same client"})
        if len(source_warehouse_values) > 1:
            errors.append({"error": "All Pack List rows must use the same warehouse"})
        if len(container_values) > 1:
            errors.append({"error": "All Pack List rows must use the same container_tracking"})

        order_number = next(iter(source_order_values), None)
        client_id = normalized_rows[0]["client_id"] if normalized_rows else None
        warehouse_id = normalized_rows[0]["warehouse_id"] if normalized_rows else None
        existing_order = None
        if order_number:
            existing_order = await self.db.scalar(
                select(InboundOrder).where(
                    InboundOrder.tenant_id == self.tenant_id,
                    InboundOrder.order_number == order_number,
                )
            )
            if not existing_order and not bool(args.get("create_inbound_if_missing")):
                errors.append(
                    {
                        "error": f"Inbound order '{order_number}' was not found",
                        "code": "inbound_order_not_found",
                        "next_action": "rerun with --create-inbound after reviewing the pre-arrival order plan",
                    }
                )
            if existing_order and normalized_rows and (
                existing_order.client_id != client_id or existing_order.warehouse_id != warehouse_id
            ):
                errors.append({"error": "Pack List client or warehouse does not match the inbound order"})

        if existing_order and normalized_rows:
            existing_package_codes = {
                value
                for value in (
                    await self.db.execute(
                        select(InboundPackage.external_carton_mark).where(
                            InboundPackage.tenant_id == self.tenant_id,
                            InboundPackage.order_id == existing_order.id,
                            InboundPackage.external_carton_mark.is_not(None),
                        )
                    )
                ).scalars()
                if value
            }
            for row in normalized_rows:
                if row["package_code"] in existing_package_codes:
                    errors.append(
                        {
                            "row": row["row_number"],
                            "error": f"Package code '{row['package_code']}' already exists on the inbound order",
                            "code": "duplicate_package_code",
                        }
                    )

            line_totals: dict[str, int] = defaultdict(int)
            for row in normalized_rows:
                line_totals[row["sku_id"]] += row["quantity"]
            order_lines = list(
                (
                    await self.db.execute(
                        select(InboundOrderLine).where(
                            InboundOrderLine.tenant_id == self.tenant_id,
                            InboundOrderLine.order_id == existing_order.id,
                        )
                    )
                ).scalars()
            )
            for sku_id, total in line_totals.items():
                matches = [line for line in order_lines if line.sku_id == sku_id]
                if not matches:
                    errors.append({"error": f"SKU '{sku_id}' is not present on the inbound order"})
                elif len(matches) == 1 and matches[0].quantity_expected != total:
                    warnings.append(
                        {
                            "code": "quantity_differs_from_inbound_order",
                            "sku_id": sku_id,
                            "inbound_quantity": matches[0].quantity_expected,
                            "pack_list_quantity": total,
                        }
                    )

        duplicate_document = await self.db.scalar(
            select(PackListDocument).where(
                PackListDocument.tenant_id == self.tenant_id,
                PackListDocument.source_checksum == parsed["source_checksum"],
            )
        )
        if duplicate_document:
            errors.append(
                {
                    "error": "This Pack List source has already been imported",
                    "code": "duplicate_pack_list_source",
                    "document_id": duplicate_document.id,
                }
            )

        if not serial_numbers:
            warnings.append(
                {
                    "code": "serial_numbers_not_provided",
                    "message": "No serial numbers were supplied; package codes remain package identifiers only.",
                }
            )
        if len(normalized_rows) < len(rows):
            warnings.append({"code": "rows_excluded_from_totals", "message": "Invalid rows are excluded until corrected."})

        total_quantity = sum(row["quantity"] for row in normalized_rows)
        container_tracking = next(iter(container_values), None)
        summary = {
            "rows": len(rows),
            "valid_rows": len(normalized_rows),
            "error": len(errors),
            "warning": len(warnings),
            "packages": len(normalized_rows),
            "quantity": total_quantity,
            "serial_numbers": len(serial_numbers),
        }
        return {
            "ok": not errors,
            "source_checksum": parsed["source_checksum"],
            "source_file_name": args.get("file_name") or "pack-list.csv",
            "source_type": args.get("source_type") or "customer_pack_list",
            "document": {
                "order_number": order_number,
                "client_id": client_id,
                "warehouse_id": warehouse_id,
                "container_tracking": container_tracking,
                "eta": None,
                "arrival_status": "pre_arrival",
                "create_inbound_if_missing": bool(args.get("create_inbound_if_missing")),
            },
            "existing_inbound_order": self._order_summary(existing_order),
            "rows": normalized_rows,
            "row_count": len(normalized_rows),
            "total_rows": len(rows),
            "summary": summary,
            "warnings": warnings,
            "errors": errors,
            "missing_required": [field for field in PACK_LIST_REQUIRED_FIELDS if not normalized_rows]
            if not rows
            else [],
            "next_action": "review_pack_list_preview_and_confirm" if not errors else "fix_pack_list_preview_errors",
        }

    async def import_after_preview(self, args: dict[str, Any], current_user_id: str | None) -> dict:
        preview = await self.preview(args)
        if not preview["ok"]:
            return preview
        rows = preview["rows"]
        order = await self.db.scalar(
            select(InboundOrder).where(
                InboundOrder.tenant_id == self.tenant_id,
                InboundOrder.order_number == preview["document"]["order_number"],
            )
        )
        created_inbound_order = False
        if not order:
            line_groups = self._line_groups(rows)
            order = await ReceivingService(self.db, self.tenant_id).create_inbound_order(
                client_id=preview["document"]["client_id"],
                warehouse_id=preview["document"]["warehouse_id"],
                order_number=preview["document"]["order_number"],
                lines=line_groups,
                expected_date=None,
                supplier_name=None,
            )
            created_inbound_order = True

        order_lines = list(
            (
                await self.db.execute(
                    select(InboundOrderLine).where(
                        InboundOrderLine.tenant_id == self.tenant_id,
                        InboundOrderLine.order_id == order.id,
                    )
                )
            ).scalars()
        )
        lines_by_sku = {line.sku_id: line for line in order_lines}
        document = PackListDocument(
            tenant_id=self.tenant_id,
            inbound_order_id=order.id,
            source_file_name=preview["source_file_name"],
            source_type=preview["source_type"],
            source_checksum=preview["source_checksum"],
            status="pending",
            container_tracking=preview["document"]["container_tracking"],
            package_count=preview["summary"]["packages"],
            total_quantity=preview["summary"]["quantity"],
            serial_count=preview["summary"]["serial_numbers"],
            note=args.get("note"),
            imported_by=current_user_id,
            extra_data={
                "eta": None,
                "arrival_status": "pre_arrival",
                "source_order_number": preview["document"]["order_number"],
            },
        )
        self.db.add(document)
        await self.db.flush()

        created_packages = preview["summary"]["packages"] if created_inbound_order else 0
        for row in rows:
            line = lines_by_sku.get(row["sku_id"])
            if not line:
                raise ValueError(f"SKU '{row['sku_code']}' is not present on the inbound order")
            package = await self.db.scalar(
                select(InboundPackage).where(
                    InboundPackage.tenant_id == self.tenant_id,
                    InboundPackage.order_id == order.id,
                    InboundPackage.external_carton_mark == row["package_code"],
                )
            )
            if not package:
                package = InboundPackage(
                    tenant_id=self.tenant_id,
                    order_id=order.id,
                    order_line_id=line.id,
                    package_number=await self._next_package_number(order.id, line.id),
                    package_type="carton",
                    status="expected",
                    expected_qty=row["quantity"],
                    external_carton_mark=row["package_code"],
                    external_customer_barcode=row["customer_sku"],
                )
                self.db.add(package)
                await self.db.flush()
                created_packages += 1
            self.db.add(
                PackListLine(
                    tenant_id=self.tenant_id,
                    document_id=document.id,
                    inbound_package_id=package.id,
                    sku_id=row["sku_id"],
                    row_number=row["row_number"],
                    package_code=row["package_code"],
                    quantity=row["quantity"],
                    customer_sku=row["customer_sku"],
                    item_name=row["item_name"],
                    serial_number=row["serial_number"],
                    raw_data=row["raw_data"],
                )
            )
        await self.db.flush()
        return {
            "ok": True,
            "document_id": document.id,
            "inbound_order_id": order.id,
            "order_number": order.order_number,
            "status": document.status,
            "packages_created": created_packages,
            "quantity": document.total_quantity,
            "serial_numbers": document.serial_count,
            "eta": None,
            "inventory_changed": False,
            "receiving_started": False,
        }

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def _resolve_client(self, raw_value: str, clients: list[Client]) -> tuple[Client | None, str]:
        raw = raw_value.strip()
        by_code = [client for client in clients if client.code.lower() == raw.lower()]
        if len(by_code) == 1:
            return by_code[0], "code"
        by_name = [client for client in clients if client.name.lower() == raw.lower()]
        if len(by_name) == 1:
            return by_name[0], "name"
        parenthetical = re.search(r"\(([^)]+)\)", raw)
        if parenthetical:
            by_code = [client for client in clients if client.code.lower() == parenthetical.group(1).lower()]
            if len(by_code) == 1:
                return by_code[0], "parenthetical_code"
        normalized = self._normalize(raw)
        matches = [client for client in clients if self._normalize(client.name) in normalized]
        if len(matches) == 1:
            return matches[0], "name_contains"
        return None, "unresolved"

    def _resolve_warehouse(self, raw_value: str, warehouses: list[Warehouse]) -> Warehouse | None:
        raw = raw_value.strip()
        matches = [warehouse for warehouse in warehouses if warehouse.code.lower() == raw.lower()]
        if len(matches) == 1:
            return matches[0]
        matches = [warehouse for warehouse in warehouses if warehouse.name.lower() == raw.lower()]
        return matches[0] if len(matches) == 1 else None

    def _resolve_sku(
        self,
        sku_code: str,
        customer_sku: str | None,
        client_id: str,
        skus: list[SKU],
    ) -> tuple[SKU | None, str]:
        exact = [sku for sku in skus if sku.client_id == client_id and sku.sku_code.lower() == sku_code.lower()]
        if len(exact) == 1:
            return exact[0], "internal_sku"
        if customer_sku:
            customer_matches = []
            for sku in skus:
                if sku.client_id != client_id:
                    continue
                attributes = sku.attributes or {}
                candidates = {
                    str(attributes.get(key) or "").strip().lower()
                    for key in ("customer_sku", "s_sku", "external_sku", "customer_code")
                }
                if customer_sku.lower() in candidates or sku.barcode == customer_sku:
                    customer_matches.append(sku)
            if len(customer_matches) == 1:
                return customer_matches[0], "customer_sku"
        return None, "unresolved"

    @staticmethod
    def _order_summary(order: InboundOrder | None) -> dict | None:
        if not order:
            return None
        return {
            "id": order.id,
            "order_number": order.order_number,
            "client_id": order.client_id,
            "warehouse_id": order.warehouse_id,
            "status": order.status,
            "expected_date": order.expected_date.isoformat() if order.expected_date else None,
        }

    @staticmethod
    def _line_groups(rows: list[dict]) -> list[dict]:
        groups: dict[str, dict] = {}
        for row in rows:
            group = groups.setdefault(
                row["sku_id"],
                {
                    "line_number": row.get("line_number"),
                    "sku_id": row["sku_id"],
                    "quantity": 0,
                    "packages": [],
                },
            )
            group["quantity"] += row["quantity"]
            group["packages"].append(
                {
                    "expected_qty": row["quantity"],
                    "package_type": "carton",
                    "external_carton_mark": row["package_code"],
                    "external_customer_barcode": row["customer_sku"],
                }
            )
        return list(groups.values())

    async def _next_package_number(self, order_id: str, line_id: str) -> int:
        packages = list(
            (
                await self.db.execute(
                    select(InboundPackage.package_number).where(
                        InboundPackage.tenant_id == self.tenant_id,
                        InboundPackage.order_id == order_id,
                        InboundPackage.order_line_id == line_id,
                    )
                )
            ).scalars()
        )
        return max([int(value) for value in packages if value is not None] or [0]) + 1


__all__ = ["PackListService"]
