"""Receiving API — inbound order creation and dock operations."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_permission
from app.core.security import TokenPayload, UserPermission
from app.models.client import Client
from app.models.inventory import SKU
from app.models.order import HandlingUnit, InboundOrder, InboundOrderLine, InboundPackage
from app.models.warehouse import Warehouse
from app.services.csv_import import load_csv_rows, parse_mapping, suggest_mapping
from app.services.idempotency_service import IdempotencyService
from app.services.receiving_service import ReceivingService

router = APIRouter()

REQUIRED_INBOUND_FIELDS = [
    "order_number",
    "client_code",
    "warehouse_code",
    "sku_code",
    "quantity",
]
OPTIONAL_INBOUND_FIELDS = [
    "reference_number",
    "supplier_name",
    "line_number",
    "lot_number",
    "expiry_date",
    "external_tracking_number",
    "external_carton_mark",
    "external_customer_barcode",
    "package_number",
    "package_type",
    "package_tracking_number",
    "package_carton_mark",
    "package_customer_barcode",
]
INBOUND_IMPORT_ALIASES = {
    "order_number": [
        "order_number",
        "po_number",
        "po",
        "purchase_order",
        "asn",
        "inbound_order",
        "receipt_number",
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
    "quantity": ["quantity", "qty", "qty_expected", "expected_qty", "units", "pieces"],
    "reference_number": [
        "reference_number",
        "reference",
        "customer_reference",
        "customer_ref",
        "external_reference",
        "truck_ref",
    ],
    "supplier_name": ["supplier_name", "supplier", "vendor", "shipper", "carrier"],
    "line_number": ["line_number", "line_no", "line", "asn_line", "po_line"],
    "lot_number": ["lot_number", "lot", "batch", "batch_number"],
    "expiry_date": ["expiry_date", "expiration_date", "expires_at", "best_before"],
    "external_tracking_number": [
        "tracking_number",
        "tracking",
        "tracking_no",
        "external_tracking_number",
    ],
    "external_carton_mark": [
        "carton_mark",
        "carton",
        "carton_no",
        "external_carton_mark",
        "box_mark",
    ],
    "external_customer_barcode": [
        "customer_barcode",
        "customer_label",
        "customer_box_barcode",
        "external_customer_barcode",
    ],
    "package_number": [
        "package_number",
        "package_no",
        "package",
        "carton_number",
        "carton_no",
        "mu_number",
        "mu_no",
    ],
    "package_type": [
        "package_type",
        "carton_type",
        "mu_type",
        "handling_unit_type",
        "container_type",
    ],
    "package_tracking_number": [
        "package_tracking_number",
        "package_tracking",
        "carton_tracking",
        "mu_tracking",
    ],
    "package_carton_mark": [
        "package_carton_mark",
        "package_carton",
        "carton_mark_package",
        "package_box_mark",
    ],
    "package_customer_barcode": [
        "package_customer_barcode",
        "package_customer_code",
        "package_customer_label",
    ],
}


class OrderPackageInput(BaseModel):
    package_number: int | None = None
    expected_qty: int | None = None
    package_type: str = "carton"
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None


class OrderLineInput(BaseModel):
    line_number: int | None = None
    sku_id: str
    quantity: int
    lot_number: str | None = None
    expiry_date: datetime | None = None
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None
    packages: list[OrderPackageInput] | None = None


class CreateInboundRequest(BaseModel):
    client_id: str
    warehouse_id: str
    order_number: str
    reference_number: str | None = None
    expected_date: datetime | None = None
    supplier_name: str | None = None
    lines: list[OrderLineInput]


class ReceiveLineRequest(BaseModel):
    line_id: str
    quantity_received: int
    quantity_damaged: int = 0
    staging_location_id: str | None = None
    pallet_count: int | None = None
    rent_free_days: int | None = None
    measured_weight_kg: float | None = None
    measured_length_cm: float | None = None
    measured_width_cm: float | None = None
    measured_height_cm: float | None = None
    package_count: int | None = None
    receiving_note: str | None = None
    lot_number: str | None = None
    expiry_date: datetime | None = None


class ScanReceivingLabelRequest(BaseModel):
    label_code: str
    source: str = "scan"


class ReceiveLabelRequest(BaseModel):
    label_code: str
    quantity_received: int
    quantity_damaged: int = 0
    staging_location_id: str | None = None
    pallet_count: int | None = None
    rent_free_days: int | None = None
    measured_weight_kg: float | None = None
    measured_length_cm: float | None = None
    measured_width_cm: float | None = None
    measured_height_cm: float | None = None
    package_count: int | None = None
    receiving_note: str | None = None
    lot_number: str | None = None
    expiry_date: datetime | None = None


class CreateInboundPackageRequest(BaseModel):
    line_id: str
    expected_qty: int | None = None
    package_type: str = "carton"
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None


class UpdateInboundPackageRequest(BaseModel):
    expected_qty: int
    package_type: str = "carton"
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None


class ReceivePackageRequest(BaseModel):
    quantity_received: int
    quantity_damaged: int = 0
    staging_location_id: str | None = None
    pallet_count: int | None = None
    rent_free_days: int | None = None
    measured_weight_kg: float | None = None
    measured_length_cm: float | None = None
    measured_width_cm: float | None = None
    measured_height_cm: float | None = None
    package_count: int | None = None
    receiving_note: str | None = None
    lot_number: str | None = None
    expiry_date: datetime | None = None


class ConfirmPackageReceiptRequest(ReceivePackageRequest):
    confirmation_token: str


class ChooseDockPreviewRequest(BaseModel):
    staging_location_id: str


class RecoveryPreviewRequest(BaseModel):
    error_code: str


class CorrectPackageReceiptRequest(ReceivePackageRequest):
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None


class MarkPrintedLabelsRequest(BaseModel):
    label_codes: list[str] | None = None


class ObservedReceivingCodeRequest(BaseModel):
    label_code: str | None = None
    package_id: str | None = None
    code_value: str
    code_type: str | None = None
    source: str = "manual"
    is_primary: bool = False


class UpdateObservedReceivingCodeRequest(BaseModel):
    code_value: str
    code_type: str | None = None
    is_primary: bool = False


def _suggest_mapping(headers: list[str]) -> dict[str, str]:
    return suggest_mapping(headers, INBOUND_IMPORT_ALIASES)


def _parse_mapping(mapping_json: str | dict[str, str] | None, headers: list[str]) -> dict[str, str]:
    return parse_mapping(
        mapping_json,
        headers,
        aliases=INBOUND_IMPORT_ALIASES,
        required_fields=REQUIRED_INBOUND_FIELDS,
        optional_fields=OPTIONAL_INBOUND_FIELDS,
    )


def _row_cell(row: dict[str, str], mapping: dict[str, str], field: str) -> str:
    header_name = mapping.get(field)
    if not header_name:
        return ""
    return (row.get(header_name) or "").strip()


def _parse_optional_positive_int(raw_value: str, *, field_name: str, row_number: int) -> int | None:
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Row {row_number}: {field_name} must be a whole number"
        ) from exc
    if value <= 0:
        raise HTTPException(
            status_code=400, detail=f"Row {row_number}: {field_name} must be greater than zero"
        )
    return value


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


def _build_inbound_import_payloads(
    rows: list[dict[str, str]],
    field_mapping: dict[str, str],
    clients: dict[str, Client],
    warehouses: dict[str, Warehouse],
    skus: dict[str, SKU],
) -> tuple[dict[str, dict], list[dict]]:
    grouped_rows: dict[str, dict] = {}
    errors: list[dict] = []

    for row_number, row in enumerate(rows, start=2):
        order_number = _row_cell(row, field_mapping, "order_number")
        client_code = _row_cell(row, field_mapping, "client_code")
        warehouse_code = _row_cell(row, field_mapping, "warehouse_code")
        sku_code = _row_cell(row, field_mapping, "sku_code")
        reference_number = _row_cell(row, field_mapping, "reference_number") or None
        supplier_name = _row_cell(row, field_mapping, "supplier_name") or None
        lot_number = _row_cell(row, field_mapping, "lot_number") or None
        expiry_date_raw = _row_cell(row, field_mapping, "expiry_date") or None
        expiry_date = None
        if expiry_date_raw:
            try:
                expiry_date = datetime.fromisoformat(expiry_date_raw)
            except ValueError:
                errors.append({"row": row_number, "error": "expiry_date must be an ISO date"})
                continue
        external_tracking_number = _row_cell(row, field_mapping, "external_tracking_number") or None
        external_carton_mark = _row_cell(row, field_mapping, "external_carton_mark") or None
        external_customer_barcode = (
            _row_cell(row, field_mapping, "external_customer_barcode") or None
        )
        package_tracking_number = _row_cell(row, field_mapping, "package_tracking_number") or None
        package_carton_mark = _row_cell(row, field_mapping, "package_carton_mark") or None
        package_customer_barcode = _row_cell(row, field_mapping, "package_customer_barcode") or None
        package_type = _row_cell(row, field_mapping, "package_type") or "carton"
        package_number = _parse_optional_positive_int(
            _row_cell(row, field_mapping, "package_number"),
            field_name="package_number",
            row_number=row_number,
        )
        line_number = _parse_optional_positive_int(
            _row_cell(row, field_mapping, "line_number"),
            field_name="line_number",
            row_number=row_number,
        )

        try:
            quantity = int(_row_cell(row, field_mapping, "quantity"))
        except ValueError:
            quantity = 0

        if (
            not order_number
            or not client_code
            or not warehouse_code
            or not sku_code
            or quantity <= 0
        ):
            errors.append({"row": row_number, "error": "Missing required inbound CSV fields"})
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

        row_has_package_context = any(
            [
                package_number is not None,
                package_tracking_number,
                package_carton_mark,
                package_customer_barcode,
                _row_cell(row, field_mapping, "package_type"),
            ]
        )

        order_bucket = grouped_rows.setdefault(
            order_number,
            {
                "client_id": clients[client_code].id,
                "warehouse_id": warehouses[warehouse_code].id,
                "reference_number": reference_number,
                "supplier_name": supplier_name,
                "lines": [],
                "_line_groups": {},
            },
        )

        if (
            order_bucket["client_id"] != clients[client_code].id
            or order_bucket["warehouse_id"] != warehouses[warehouse_code].id
        ):
            errors.append(
                {
                    "row": row_number,
                    "error": "Inbound rows with the same order_number must use the same client and warehouse",
                }
            )
            continue

        if row_has_package_context:
            line_group_key = (
                f"line:{line_number}" if line_number is not None else f"sku:{skus[sku_code].id}"
            )
            line_bucket = order_bucket["_line_groups"].get(line_group_key)
            if line_bucket is None:
                line_bucket = {
                    "line_number": line_number,
                    "sku_id": skus[sku_code].id,
                    "quantity": 0,
                    "external_tracking_number": external_tracking_number,
                    "external_carton_mark": external_carton_mark,
                    "external_customer_barcode": external_customer_barcode,
                    "lot_number": lot_number,
                    "expiry_date": expiry_date,
                    "packages": [],
                }
                order_bucket["_line_groups"][line_group_key] = line_bucket
                order_bucket["lines"].append(line_bucket)
            elif line_bucket["sku_id"] != skus[sku_code].id:
                errors.append(
                    {
                        "row": row_number,
                        "error": "Inbound package rows that share the same line_number must point to the same SKU",
                    }
                )
                continue

            line_bucket["quantity"] += quantity
            if not line_bucket.get("external_tracking_number"):
                line_bucket["external_tracking_number"] = external_tracking_number
            if not line_bucket.get("external_carton_mark"):
                line_bucket["external_carton_mark"] = external_carton_mark
            if not line_bucket.get("external_customer_barcode"):
                line_bucket["external_customer_barcode"] = external_customer_barcode
            if not line_bucket.get("lot_number"):
                line_bucket["lot_number"] = lot_number
            if not line_bucket.get("expiry_date"):
                line_bucket["expiry_date"] = expiry_date

            line_bucket["packages"].append(
                {
                    "package_number": package_number,
                    "expected_qty": quantity,
                    "package_type": package_type,
                    "external_tracking_number": package_tracking_number or external_tracking_number,
                    "external_carton_mark": package_carton_mark or external_carton_mark,
                    "external_customer_barcode": package_customer_barcode
                    or external_customer_barcode,
                }
            )
            continue

        order_bucket["lines"].append(
            {
                "line_number": line_number,
                "sku_id": skus[sku_code].id,
                "quantity": quantity,
                "external_tracking_number": external_tracking_number,
                "external_carton_mark": external_carton_mark,
                "external_customer_barcode": external_customer_barcode,
                "lot_number": lot_number,
                "expiry_date": expiry_date,
            }
        )

    for payload in grouped_rows.values():
        payload.pop("_line_groups", None)

    return grouped_rows, errors


@router.post("/inbound/import-csv/preview")
async def preview_inbound_orders_csv(
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.INBOUND_ORDERS_IMPORT.value)
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
        "required_fields": REQUIRED_INBOUND_FIELDS,
        "optional_fields": OPTIONAL_INBOUND_FIELDS,
        "suggested_mapping": suggested_mapping,
        "missing_required": [
            field for field in REQUIRED_INBOUND_FIELDS if field not in suggested_mapping
        ],
        "sample_rows": sample_rows,
        "mapped_preview": mapped_preview,
        "total_rows": len(rows),
    }


@router.post("/inbound", status_code=status.HTTP_201_CREATED)
async def create_inbound_order(
    body: CreateInboundRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.INBOUND_ORDERS_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    try:
        order = await svc.create_inbound_order(
            client_id=body.client_id,
            warehouse_id=body.warehouse_id,
            order_number=body.order_number,
            lines=[line.model_dump() for line in body.lines],
            reference_number=body.reference_number,
            expected_date=body.expected_date,
            supplier_name=body.supplier_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": order.id, "order_number": order.order_number, "status": order.status}


@router.post("/inbound/import-csv")
async def import_inbound_orders_csv(
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.INBOUND_ORDERS_IMPORT.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    content = await file.read()
    headers, rows = load_csv_rows(file.filename, content)
    field_mapping = _parse_mapping(mapping, headers)
    svc = ReceivingService(db, current_user.tenant_id)

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

    grouped_rows, errors = _build_inbound_import_payloads(
        rows=rows,
        field_mapping=field_mapping,
        clients=clients,
        warehouses=warehouses,
        skus=skus,
    )

    imported = 0
    for order_number, payload in grouped_rows.items():
        try:
            await svc.create_inbound_order(
                client_id=payload["client_id"],
                warehouse_id=payload["warehouse_id"],
                order_number=order_number,
                lines=payload["lines"],
                reference_number=payload["reference_number"],
                supplier_name=payload["supplier_name"],
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


@router.post("/inbound/{order_id}/start-receiving")
async def start_receiving(
    order_id: str,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = ReceivingService(db, current_user.tenant_id)
        order = await svc.start_receiving(order_id)
        return {"id": order.id, "status": order.status}

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="receiving.inbound.start",
        request_payload={"path": {"order_id": order_id}},
        handler=execute,
    )


@router.post("/inbound/{order_id}/receive-line")
async def receive_line(
    order_id: str,
    body: ReceiveLineRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    return await svc.receive_line(
        order_id=order_id,
        line_id=body.line_id,
        quantity_received=body.quantity_received,
        quantity_damaged=body.quantity_damaged,
        staging_location_id=body.staging_location_id,
        pallet_count=body.pallet_count,
        rent_free_days=body.rent_free_days,
        measured_weight_kg=body.measured_weight_kg,
        measured_length_cm=body.measured_length_cm,
        measured_width_cm=body.measured_width_cm,
        measured_height_cm=body.measured_height_cm,
        package_count=body.package_count,
        receiving_note=body.receiving_note,
        lot_number=body.lot_number,
        expiry_date=body.expiry_date,
        user_id=current_user.sub,
    )


@router.post("/inbound/{order_id}/scan-label")
async def scan_receiving_label(
    order_id: str,
    body: ScanReceivingLabelRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    return await svc.scan_label(
        order_id=order_id, label_code=body.label_code.strip(), source=body.source
    )


@router.post("/inbound/{order_id}/scan-label/preview")
async def preview_scan_receiving_label(
    order_id: str,
    body: ScanReceivingLabelRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    return await svc.preview_scan_label(
        order_id=order_id, label_code=body.label_code.strip(), source=body.source
    )


@router.get("/inbound/{order_id}/captured-codes")
async def list_captured_receiving_codes(
    order_id: str,
    label_code: str | None = None,
    package_id: str | None = None,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    codes = await svc.list_observed_codes(
        order_id=order_id,
        label_code=label_code.strip() if label_code else None,
        package_id=package_id,
    )
    return [svc._serialize_observed_code(code) for code in codes]


@router.post("/inbound/{order_id}/captured-codes")
async def add_captured_receiving_code(
    order_id: str,
    body: ObservedReceivingCodeRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    code = await svc.add_observed_code(
        order_id=order_id,
        label_code=body.label_code.strip() if body.label_code else None,
        package_id=body.package_id,
        code_value=body.code_value,
        code_type=body.code_type,
        source=body.source,
        is_primary=body.is_primary,
    )
    return svc._serialize_observed_code(code)


@router.patch("/inbound/{order_id}/captured-codes/{code_id}")
async def update_captured_receiving_code(
    order_id: str,
    code_id: str,
    body: UpdateObservedReceivingCodeRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    code = await svc.update_observed_code(
        order_id=order_id,
        code_id=code_id,
        code_value=body.code_value,
        code_type=body.code_type,
        is_primary=body.is_primary,
    )
    return svc._serialize_observed_code(code)


@router.delete(
    "/inbound/{order_id}/captured-codes/{code_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_captured_receiving_code(
    order_id: str,
    code_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    await svc.delete_observed_code(order_id=order_id, code_id=code_id)


@router.get("/inbound/{order_id}/packages")
async def list_inbound_packages(
    order_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    order = await db.scalar(
        select(InboundOrder).where(
            InboundOrder.tenant_id == current_user.tenant_id,
            InboundOrder.id == order_id,
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="Inbound order not found")
    packages = await svc.list_packages(order_id=order_id)
    line_ids = {package.order_line_id for package in packages}
    sku_ids: set[str] = set()
    lines = (
        {
            line.id: line
            for line in (
                await db.execute(
                    select(InboundOrderLine).where(
                        InboundOrderLine.tenant_id == current_user.tenant_id,
                        InboundOrderLine.id.in_(line_ids),
                    )
                )
            ).scalars()
        }
        if line_ids
        else {}
    )
    sku_ids.update({line.sku_id for line in lines.values()})
    skus = (
        {
            sku.id: sku
            for sku in (await db.execute(select(SKU).where(SKU.id.in_(sku_ids)))).scalars()
        }
        if sku_ids
        else {}
    )

    return [
        {
            "id": package.id,
            "order_line_id": package.order_line_id,
            "line_number": lines.get(package.order_line_id).line_number
            if lines.get(package.order_line_id)
            else None,
            "sku_id": lines.get(package.order_line_id).sku_id
            if lines.get(package.order_line_id)
            else None,
            "sku_code": skus.get(lines.get(package.order_line_id).sku_id).sku_code
            if lines.get(package.order_line_id)
            and skus.get(lines.get(package.order_line_id).sku_id)
            else None,
            "sku_name": skus.get(lines.get(package.order_line_id).sku_id).name
            if lines.get(package.order_line_id)
            and skus.get(lines.get(package.order_line_id).sku_id)
            else None,
            "package_number": package.package_number,
            "label_sequence": package.label_sequence,
            "package_type": package.package_type,
            "package_origin": _infer_package_origin(order.received_date, package.created_at),
            "status": package.status,
            "expected_qty": package.expected_qty,
            "received_qty": package.received_qty,
            "damaged_qty": package.damaged_qty,
            "staging_location_id": package.staging_location_id,
            "lot_number": lines.get(package.order_line_id).lot_number
            if lines.get(package.order_line_id)
            else None,
            "expiry_date": lines.get(package.order_line_id).expiry_date.isoformat()
            if lines.get(package.order_line_id) and lines.get(package.order_line_id).expiry_date
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
            "confirmed_at": package.confirmed_at,
        }
        for package in packages
    ]


@router.post("/inbound/{order_id}/packages", status_code=status.HTTP_201_CREATED)
async def create_inbound_package(
    order_id: str,
    body: CreateInboundPackageRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    package = await svc.create_package(
        order_id=order_id,
        line_id=body.line_id,
        expected_qty=body.expected_qty,
        package_type=body.package_type,
        external_tracking_number=body.external_tracking_number,
        external_carton_mark=body.external_carton_mark,
        external_customer_barcode=body.external_customer_barcode,
    )
    return {
        "id": package.id,
        "order_line_id": package.order_line_id,
        "package_number": package.package_number,
        "package_type": package.package_type,
        "status": package.status,
        "expected_qty": package.expected_qty,
    }


@router.patch("/inbound/{order_id}/packages/{package_id}")
async def update_inbound_package(
    order_id: str,
    package_id: str,
    body: UpdateInboundPackageRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    package = await svc.update_package(
        order_id=order_id,
        package_id=package_id,
        expected_qty=body.expected_qty,
        package_type=body.package_type,
        external_tracking_number=body.external_tracking_number,
        external_carton_mark=body.external_carton_mark,
        external_customer_barcode=body.external_customer_barcode,
    )
    return {
        "id": package.id,
        "order_line_id": package.order_line_id,
        "package_number": package.package_number,
        "package_type": package.package_type,
        "status": package.status,
        "expected_qty": package.expected_qty,
        "external_tracking_number": package.external_tracking_number,
        "external_carton_mark": package.external_carton_mark,
        "external_customer_barcode": package.external_customer_barcode,
    }


@router.delete("/inbound/{order_id}/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbound_package(
    order_id: str,
    package_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    await svc.delete_package(order_id=order_id, package_id=package_id)


@router.post("/inbound/{order_id}/packages/{package_id}/open")
async def open_inbound_package(
    order_id: str,
    package_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    return await svc.open_package(order_id=order_id, package_id=package_id)


@router.post("/inbound/{order_id}/packages/{package_id}/receive/preview")
async def preview_inbound_package_receipt(
    order_id: str,
    package_id: str,
    body: ReceivePackageRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    return await svc.preview_package_receipt(
        order_id=order_id,
        package_id=package_id,
        quantity_received=body.quantity_received,
        quantity_damaged=body.quantity_damaged,
        staging_location_id=body.staging_location_id,
        pallet_count=body.pallet_count,
        rent_free_days=body.rent_free_days,
        measured_weight_kg=body.measured_weight_kg,
        measured_length_cm=body.measured_length_cm,
        measured_width_cm=body.measured_width_cm,
        measured_height_cm=body.measured_height_cm,
        package_count=body.package_count,
        receiving_note=body.receiving_note,
        lot_number=body.lot_number,
        expiry_date=body.expiry_date,
        user_id=current_user.sub,
    )


@router.post("/inbound/{order_id}/packages/{package_id}/receive/confirm")
async def confirm_inbound_package_receipt_with_agent_token(
    order_id: str,
    package_id: str,
    body: ConfirmPackageReceiptRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent receiving confirmation",
            },
        )

    async def execute():
        svc = ReceivingService(db, current_user.tenant_id)
        return await svc.confirm_package_receipt_with_token(
            order_id=order_id,
            package_id=package_id,
            confirmation_token=body.confirmation_token,
            quantity_received=body.quantity_received,
            quantity_damaged=body.quantity_damaged,
            staging_location_id=body.staging_location_id,
            pallet_count=body.pallet_count,
            rent_free_days=body.rent_free_days,
            measured_weight_kg=body.measured_weight_kg,
            measured_length_cm=body.measured_length_cm,
            measured_width_cm=body.measured_width_cm,
            measured_height_cm=body.measured_height_cm,
            package_count=body.package_count,
            receiving_note=body.receiving_note,
            lot_number=body.lot_number,
            expiry_date=body.expiry_date,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="receiving.inbound.package.agent_confirm",
        request_payload={
            "path": {"order_id": order_id, "package_id": package_id},
            "body": body.model_dump(mode="json"),
        },
        handler=execute,
    )


@router.post("/inbound/{order_id}/packages/{package_id}/choose-dock/preview")
async def preview_inbound_package_dock_choice(
    order_id: str,
    package_id: str,
    body: ChooseDockPreviewRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    return await svc.preview_choose_dock(
        order_id=order_id,
        package_id=package_id,
        staging_location_id=body.staging_location_id,
    )


@router.post("/recovery/preview")
async def preview_receiving_recovery(
    body: RecoveryPreviewRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
):
    return ReceivingService.preview_recovery(body.error_code)


@router.post("/inbound/{order_id}/packages/{package_id}/receive")
async def receive_inbound_package(
    order_id: str,
    package_id: str,
    body: ReceivePackageRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = ReceivingService(db, current_user.tenant_id)
        return await svc.receive_package(
            order_id=order_id,
            package_id=package_id,
            quantity_received=body.quantity_received,
            quantity_damaged=body.quantity_damaged,
            staging_location_id=body.staging_location_id,
            pallet_count=body.pallet_count,
            rent_free_days=body.rent_free_days,
            measured_weight_kg=body.measured_weight_kg,
            measured_length_cm=body.measured_length_cm,
            measured_width_cm=body.measured_width_cm,
            measured_height_cm=body.measured_height_cm,
            package_count=body.package_count,
            receiving_note=body.receiving_note,
            lot_number=body.lot_number,
            expiry_date=body.expiry_date,
            user_id=current_user.sub,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="receiving.inbound.package.receive",
        request_payload={
            "path": {"order_id": order_id, "package_id": package_id},
            "body": body.model_dump(mode="json"),
        },
        handler=execute,
    )


@router.post("/inbound/{order_id}/packages/{package_id}/correct")
async def correct_inbound_package_receipt(
    order_id: str,
    package_id: str,
    body: CorrectPackageReceiptRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    return await svc.correct_package_receipt(
        order_id=order_id,
        package_id=package_id,
        quantity_received=body.quantity_received,
        quantity_damaged=body.quantity_damaged,
        staging_location_id=body.staging_location_id,
        pallet_count=body.pallet_count,
        rent_free_days=body.rent_free_days,
        measured_weight_kg=body.measured_weight_kg,
        measured_length_cm=body.measured_length_cm,
        measured_width_cm=body.measured_width_cm,
        measured_height_cm=body.measured_height_cm,
        package_count=body.package_count,
        receiving_note=body.receiving_note,
        external_tracking_number=body.external_tracking_number,
        external_carton_mark=body.external_carton_mark,
        external_customer_barcode=body.external_customer_barcode,
        user_id=current_user.sub,
    )


@router.get("/inbound/{order_id}/labels")
async def list_receiving_labels(
    order_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    labels = await svc.list_labels(order_id=order_id)
    order = await db.scalar(
        select(InboundOrder).where(
            InboundOrder.tenant_id == current_user.tenant_id,
            InboundOrder.id == order_id,
        )
    )
    label_ids = {label.id for label in labels}
    sku_ids = {label.sku_id for label in labels}
    package_ids = {label.inbound_package_id for label in labels if label.inbound_package_id}

    handling_units = (
        {
            unit.receiving_label_id: unit
            for unit in (
                await db.execute(
                    select(HandlingUnit).where(
                        HandlingUnit.tenant_id == current_user.tenant_id,
                        HandlingUnit.receiving_label_id.in_(label_ids),
                    )
                )
            ).scalars()
        }
        if label_ids
        else {}
    )

    packages = (
        {
            package.id: package
            for package in (
                await db.execute(
                    select(InboundPackage).where(
                        InboundPackage.tenant_id == current_user.tenant_id,
                        InboundPackage.id.in_(package_ids),
                    )
                )
            ).scalars()
        }
        if package_ids
        else {}
    )

    skus = (
        {
            sku.id: sku
            for sku in (
                await db.execute(
                    select(SKU).where(
                        SKU.id.in_(sku_ids),
                    )
                )
            ).scalars()
        }
        if sku_ids
        else {}
    )

    return [
        {
            "id": label.id,
            "label_code": label.label_code,
            "label_type": label.label_type,
            "package_id": label.inbound_package_id,
            "package_number": packages.get(label.inbound_package_id).package_number
            if label.inbound_package_id and packages.get(label.inbound_package_id)
            else None,
            "package_type": packages.get(label.inbound_package_id).package_type
            if label.inbound_package_id and packages.get(label.inbound_package_id)
            else label.label_type,
            "external_tracking_number": label.external_tracking_number,
            "external_carton_mark": label.external_carton_mark,
            "external_customer_barcode": label.external_customer_barcode,
            "handling_unit_code": label.label_code,
            "expected_qty": label.expected_qty,
            "received_qty": label.received_qty,
            "status": label.status,
            "lot_number": label.lot_number,
            "printed_at": label.printed_at,
            "print_count": int((label.extra_data or {}).get("print_count", 0)),
            "sku_code": skus.get(label.sku_id).sku_code if skus.get(label.sku_id) else None,
            "sku_name": skus.get(label.sku_id).name if skus.get(label.sku_id) else None,
            "reference_number": order.reference_number if order else None,
            "package_count": handling_units.get(label.id).package_count
            if handling_units.get(label.id)
            else None,
            "pallet_count": handling_units.get(label.id).pallet_count
            if handling_units.get(label.id)
            else None,
            "rent_free_days": handling_units.get(label.id).rent_free_days
            if handling_units.get(label.id)
            else None,
            "measured_weight_kg": float(handling_units.get(label.id).measured_weight_kg)
            if handling_units.get(label.id)
            and handling_units.get(label.id).measured_weight_kg is not None
            else None,
            "measured_length_cm": float(handling_units.get(label.id).measured_length_cm)
            if handling_units.get(label.id)
            and handling_units.get(label.id).measured_length_cm is not None
            else None,
            "measured_width_cm": float(handling_units.get(label.id).measured_width_cm)
            if handling_units.get(label.id)
            and handling_units.get(label.id).measured_width_cm is not None
            else None,
            "measured_height_cm": float(handling_units.get(label.id).measured_height_cm)
            if handling_units.get(label.id)
            and handling_units.get(label.id).measured_height_cm is not None
            else None,
            "receiving_note": handling_units.get(label.id).note
            if handling_units.get(label.id)
            else None,
        }
        for label in labels
    ]


@router.post("/inbound/{order_id}/labels/mark-printed")
async def mark_receiving_labels_printed(
    order_id: str,
    body: MarkPrintedLabelsRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReceivingService(db, current_user.tenant_id)
    labels = await svc.mark_labels_printed(order_id=order_id, label_codes=body.label_codes)
    return {
        "updated": len(labels),
        "labels": [
            {
                "id": label.id,
                "label_code": label.label_code,
                "printed_at": label.printed_at,
                "print_count": int((label.extra_data or {}).get("print_count", 0)),
            }
            for label in labels
        ],
    }


@router.post("/inbound/{order_id}/receive-label")
async def receive_label(
    order_id: str,
    body: ReceiveLabelRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = ReceivingService(db, current_user.tenant_id)
        return await svc.receive_label(
            order_id=order_id,
            label_code=body.label_code.strip(),
            quantity_received=body.quantity_received,
            quantity_damaged=body.quantity_damaged,
            staging_location_id=body.staging_location_id,
            pallet_count=body.pallet_count,
            rent_free_days=body.rent_free_days,
            measured_weight_kg=body.measured_weight_kg,
            measured_length_cm=body.measured_length_cm,
            measured_width_cm=body.measured_width_cm,
            measured_height_cm=body.measured_height_cm,
            package_count=body.package_count,
            receiving_note=body.receiving_note,
            lot_number=body.lot_number,
            expiry_date=body.expiry_date,
            user_id=current_user.sub,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="receiving.inbound.label.receive",
        request_payload={
            "path": {"order_id": order_id},
            "body": body.model_dump(mode="json"),
        },
        handler=execute,
    )


@router.post("/inbound/{order_id}/complete")
async def complete_receiving(
    order_id: str,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.RECEIVING_EXECUTE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = ReceivingService(db, current_user.tenant_id)
        result = await svc.complete_receiving(order_id, user_id=current_user.sub)
        order = result["order"]
        return {
            "id": order.id,
            "status": order.status,
            "created_tasks": result["created_tasks"],
            "putaway_units": result["putaway_units"],
        }

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="receiving.inbound.complete",
        request_payload={"path": {"order_id": order_id}},
        handler=execute,
    )
