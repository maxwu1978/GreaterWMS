"""Data import/export — CSV inventory upload and download."""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.inventory import SKU, Inventory
from app.models.warehouse import Location
from app.services.csv_import import load_csv_rows
from app.services.outbound_readiness import (
    OutboundReadinessRefreshStats,
    refresh_pending_outbound_readiness_for_inventory_change,
)

router = APIRouter()


class ManualInventoryImportRequest(BaseModel):
    warehouse_id: str
    location_barcode: str
    sku_code: str
    client_id: str | None = None
    quantity: int
    lot_number: str | None = None


def _readiness_stats_payload(stats: OutboundReadinessRefreshStats) -> dict:
    return {
        "scanned_orders": stats.scanned_orders,
        "updated_orders": stats.updated_orders,
        "unchanged_orders": stats.unchanged_orders,
    }


@router.get("/inventory/csv")
async def export_inventory_csv(
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Export current inventory as CSV download."""
    result = await db.execute(
        select(Inventory, SKU, Location)
        .join(SKU, SKU.id == Inventory.sku_id)
        .join(Location, Location.id == Inventory.location_id)
        .where(Inventory.quantity_on_hand > 0)
        .order_by(SKU.sku_code)
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "sku_code",
            "sku_name",
            "barcode",
            "location",
            "client_id",
            "on_hand",
            "allocated",
            "available",
            "lot",
            "expiry",
        ]
    )

    for inv, sku, loc in result.all():
        writer.writerow(
            [
                sku.sku_code,
                sku.name,
                sku.barcode or "",
                loc.barcode,
                inv.client_id,
                inv.quantity_on_hand,
                inv.quantity_allocated,
                inv.quantity_available,
                inv.lot_number or "",
                inv.expiry_date.isoformat() if inv.expiry_date else "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="inventory-{datetime.now(UTC).strftime("%Y%m%d")}.csv"'
        },
    )


@router.post("/inventory/csv")
async def import_inventory_csv(
    file: UploadFile = File(...),
    warehouse_id: str | None = None,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Import inventory from CSV. Expected columns:
    sku_code, location_barcode, client_id, quantity, lot_number (optional), expiry_date (optional)
    Max file size: 5MB. Must be .csv file.
    """
    # Validate file type
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    # Check Content-Length header before reading (fast reject for huge uploads)
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")

    # Read with hard limit — stop reading after 5MB+1 byte
    max_size = 5 * 1024 * 1024
    chunks = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(status_code=413, detail="File too large (max 5MB)")
        chunks.append(chunk)
    content = b"".join(chunks)
    # Legacy behavior: plain utf-8 (no BOM stripping), decode errors propagate,
    # and a missing header row is tolerated.
    _, rows = load_csv_rows(file.filename, content, encoding="utf-8", strict=False)

    imported = 0
    errors = []
    touched_skus_by_warehouse: dict[str, set[str]] = {}

    for i, row in enumerate(rows, start=2):
        sku_code = row.get("sku_code", "").strip()
        loc_barcode = row.get("location_barcode", "").strip()
        client_id = row.get("client_id", "").strip()
        qty = int(row.get("quantity", 0))
        lot_number = row.get("lot_number", "").strip() or None

        if not sku_code or not loc_barcode or qty <= 0:
            errors.append({"row": i, "error": "Missing sku_code, location_barcode, or quantity"})
            continue

        # Find SKU
        sku_result = await db.execute(
            select(SKU).where(SKU.sku_code == sku_code, SKU.tenant_id == current_user.tenant_id)
        )
        sku = sku_result.scalar_one_or_none()
        if not sku:
            errors.append({"row": i, "error": f"SKU '{sku_code}' not found"})
            continue

        # Find location
        loc_result = await db.execute(
            select(Location).where(
                Location.barcode == loc_barcode, Location.tenant_id == current_user.tenant_id
            )
        )
        loc = loc_result.scalar_one_or_none()
        if not loc:
            errors.append({"row": i, "error": f"Location '{loc_barcode}' not found"})
            continue
        if warehouse_id and warehouse_id != loc.warehouse_id:
            errors.append(
                {
                    "row": i,
                    "error": f"Location '{loc_barcode}' does not belong to warehouse '{warehouse_id}'",
                }
            )
            continue

        resolved_warehouse_id = loc.warehouse_id

        # Upsert inventory
        inv_result = await db.execute(
            select(Inventory).where(
                Inventory.sku_id == sku.id,
                Inventory.location_id == loc.id,
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.warehouse_id == resolved_warehouse_id,
                Inventory.lot_number == lot_number,
            )
        )
        inv = inv_result.scalar_one_or_none()

        if inv:
            inv.quantity_on_hand = qty
        else:
            inv = Inventory(
                tenant_id=current_user.tenant_id,
                client_id=client_id or sku.client_id,
                warehouse_id=resolved_warehouse_id,
                location_id=loc.id,
                sku_id=sku.id,
                quantity_on_hand=qty,
                lot_number=lot_number,
                received_at=datetime.now(UTC),
            )
            db.add(inv)
        touched_skus_by_warehouse.setdefault(resolved_warehouse_id, set()).add(sku.id)
        imported += 1

    await db.flush()
    readiness_scanned = 0
    readiness_updated = 0
    readiness_unchanged = 0
    for touched_warehouse_id, touched_sku_ids in touched_skus_by_warehouse.items():
        stats = await refresh_pending_outbound_readiness_for_inventory_change(
            db,
            current_user.tenant_id,
            warehouse_id=touched_warehouse_id,
            sku_ids=touched_sku_ids,
        )
        readiness_scanned += stats.scanned_orders
        readiness_updated += stats.updated_orders
        readiness_unchanged += stats.unchanged_orders
    return {
        "imported": imported,
        "errors": errors,
        "total_rows": imported + len(errors),
        "readiness_refresh": {
            "scanned_orders": readiness_scanned,
            "updated_orders": readiness_updated,
            "unchanged_orders": readiness_unchanged,
        },
    }


@router.post("/inventory/manual", status_code=status.HTTP_201_CREATED)
async def import_single_inventory_row(
    body: ManualInventoryImportRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    sku = await db.scalar(
        select(SKU).where(SKU.sku_code == body.sku_code, SKU.tenant_id == current_user.tenant_id)
    )
    if not sku:
        raise HTTPException(status_code=404, detail=f"SKU '{body.sku_code}' not found")

    location = await db.scalar(
        select(Location).where(
            Location.barcode == body.location_barcode,
            Location.tenant_id == current_user.tenant_id,
            Location.warehouse_id == body.warehouse_id,
        )
    )
    if not location:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{body.location_barcode}' not found in this warehouse",
        )

    inventory = await db.scalar(
        select(Inventory).where(
            Inventory.tenant_id == current_user.tenant_id,
            Inventory.warehouse_id == body.warehouse_id,
            Inventory.location_id == location.id,
            Inventory.sku_id == sku.id,
            Inventory.lot_number == (body.lot_number or None),
        )
    )

    resolved_client_id = body.client_id or sku.client_id
    if inventory:
        inventory.quantity_on_hand = body.quantity
        if body.lot_number is not None:
            inventory.lot_number = body.lot_number or None
    else:
        inventory = Inventory(
            tenant_id=current_user.tenant_id,
            client_id=resolved_client_id,
            warehouse_id=body.warehouse_id,
            location_id=location.id,
            sku_id=sku.id,
            quantity_on_hand=body.quantity,
            lot_number=body.lot_number or None,
            received_at=datetime.now(UTC),
        )
        db.add(inventory)

    await db.flush()
    readiness_stats = await refresh_pending_outbound_readiness_for_inventory_change(
        db,
        current_user.tenant_id,
        warehouse_id=body.warehouse_id,
        sku_ids=[sku.id],
    )
    return {
        "id": inventory.id,
        "warehouse_id": body.warehouse_id,
        "location_barcode": body.location_barcode,
        "sku_code": body.sku_code,
        "quantity": inventory.quantity_on_hand,
        "readiness_refresh": _readiness_stats_payload(readiness_stats),
    }
