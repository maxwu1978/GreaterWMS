"""Inventory query and adjustment endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import client_scope_filter, require_role
from app.core.pagination import PaginationParams, paginate_window
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction
from app.models.task import Task, TaskStatus, TaskType
from app.models.warehouse import Location, LocationStatus, Warehouse
from app.services.inventory_service import InventoryService

router = APIRouter()


class InventoryResponse(BaseModel):
    id: str
    client_id: str
    warehouse_id: str
    location_id: str
    sku_id: str
    lpn: str | None
    lot_number: str | None
    expiry_date: str | None = None
    quantity_on_hand: int
    quantity_allocated: int
    quantity_available: int


class InventoryLotUpdateRequest(BaseModel):
    lot_number: str
    expiry_date: datetime | None = None
    reason: str | None = None


class InventoryLotUpdateResponse(BaseModel):
    success: bool
    inventory_id: str
    lot_number: str | None
    expiry_date: str | None


@router.get("/")
async def list_inventory(
    warehouse_id: str | None = Query(None),
    client_id: str | None = Query(None),
    sku_id: str | None = Query(None),
    search: str | None = Query(None),
    focus: str | None = Query(None),
    location_type: str | None = Query(None),
    issue: str | None = Query(None),
    sort_by: str = Query("warehouse"),
    sort_direction: str = Query("asc", pattern="^(asc|desc)$"),
    page: PaginationParams = Depends(),
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
    query = select(Inventory).where(Inventory.tenant_id == current_user.tenant_id)
    joined_sku = False
    joined_client = False
    joined_location = False
    joined_warehouse = False

    scoped_client_id = client_scope_filter(current_user)
    if scoped_client_id:
        query = query.where(Inventory.client_id == scoped_client_id)
    elif client_id:
        query = query.where(Inventory.client_id == client_id)

    if warehouse_id:
        query = query.where(Inventory.warehouse_id == warehouse_id)
    if sku_id:
        query = query.where(Inventory.sku_id == sku_id)
    if focus == "available":
        query = query.where(
            (Inventory.quantity_on_hand - Inventory.quantity_allocated - Inventory.quantity_damaged) > 0
        )
    elif focus == "allocated":
        query = query.where(Inventory.quantity_allocated > 0)
    elif focus == "staging":
        staging_location_ids = select(Task.source_location_id).where(
            Task.tenant_id == current_user.tenant_id,
            Task.task_type == TaskType.PUTAWAY.value,
            Task.status == TaskStatus.PENDING.value,
            Task.source_location_id.is_not(None),
        )
        query = query.where(Inventory.location_id.in_(staging_location_ids))
    elif focus not in (None, "", "all"):
        raise HTTPException(status_code=400, detail="Unsupported inventory focus")

    if location_type and location_type != "all":
        if not joined_location:
            query = query.join(Location, Location.id == Inventory.location_id)
            joined_location = True
        query = query.where(Location.location_type == location_type)

    if issue == "blocked":
        if not joined_location:
            query = query.join(Location, Location.id == Inventory.location_id)
            joined_location = True
        query = query.where(
            or_(
                Location.location_type == "quality",
                Location.current_status == LocationStatus.BLOCKED.value,
            )
        )
    elif issue not in (None, "", "all"):
        raise HTTPException(status_code=400, detail="Unsupported inventory issue filter")

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        if not joined_sku:
            query = query.join(SKU, SKU.id == Inventory.sku_id)
            joined_sku = True
        if not joined_client:
            query = query.join(Client, Client.id == Inventory.client_id)
            joined_client = True
        if not joined_location:
            query = query.join(Location, Location.id == Inventory.location_id)
            joined_location = True
        if not joined_warehouse:
            query = query.join(Warehouse, Warehouse.id == Inventory.warehouse_id)
            joined_warehouse = True
        query = query.where(
            or_(
                SKU.sku_code.ilike(term),
                SKU.name.ilike(term),
                Client.name.ilike(term),
                Client.code.ilike(term),
                Location.barcode.ilike(term),
                Warehouse.name.ilike(term),
                Warehouse.code.ilike(term),
                Inventory.lpn.ilike(term),
                Inventory.lot_number.ilike(term),
            )
        )

    query = query.where(Inventory.quantity_on_hand > 0)
    available_sort = (
        Inventory.quantity_on_hand - Inventory.quantity_allocated - Inventory.quantity_damaged
    )
    sort_columns = {
        "warehouse": Inventory.warehouse_id,
        "sku": Inventory.sku_id,
        "client": Inventory.client_id,
        "location": Inventory.location_id,
        "on_hand": Inventory.quantity_on_hand,
        "allocated": Inventory.quantity_allocated,
        "available": available_sort,
        "lot": Inventory.lot_number,
        "created_at": Inventory.created_at,
    }
    sort_column = sort_columns.get(sort_by)
    if sort_column is None:
        raise HTTPException(status_code=400, detail="Unsupported inventory sort field")
    direction = sort_direction.lower()
    query = query.order_by(
        sort_column.desc() if direction == "desc" else sort_column.asc(),
        Inventory.warehouse_id.asc(),
        Inventory.sku_id.asc(),
        Inventory.location_id.asc(),
        Inventory.lot_number.asc(),
        Inventory.id.asc(),
    )
    result = await paginate_window(db, query, page)

    result["items"] = [
        InventoryResponse(
            id=inv.id,
            client_id=inv.client_id,
            warehouse_id=inv.warehouse_id,
            location_id=inv.location_id,
            sku_id=inv.sku_id,
            lpn=inv.lpn,
            lot_number=inv.lot_number,
            expiry_date=inv.expiry_date.isoformat() if inv.expiry_date else None,
            quantity_on_hand=inv.quantity_on_hand,
            quantity_allocated=inv.quantity_allocated,
            quantity_available=inv.quantity_available,
        )
        for inv in result["items"]
    ]
    return result


@router.get("/transactions")
async def list_inventory_transactions(
    sku_id: str | None = Query(None),
    location_id: str | None = Query(None),
    transaction_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
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
    query = (
        select(InventoryTransaction)
        .where(InventoryTransaction.tenant_id == current_user.tenant_id)
        .order_by(InventoryTransaction.performed_at.desc(), InventoryTransaction.id.desc())
        .limit(limit)
    )
    scoped_client_id = client_scope_filter(current_user)
    if scoped_client_id:
        query = query.where(InventoryTransaction.client_id == scoped_client_id)
    if sku_id:
        query = query.where(InventoryTransaction.sku_id == sku_id)
    if location_id:
        query = query.where(InventoryTransaction.location_id == location_id)
    if transaction_type:
        query = query.where(InventoryTransaction.transaction_type == transaction_type)
    rows = (await db.execute(query)).scalars().all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": row.id,
                "transaction_type": row.transaction_type,
                "sku_id": row.sku_id,
                "location_id": row.location_id,
                "quantity_change": row.quantity_change,
                "from_location_id": row.from_location_id,
                "to_location_id": row.to_location_id,
                "reference_type": row.reference_type,
                "reference_id": row.reference_id,
                "performed_by": row.performed_by,
                "performed_at": row.performed_at.isoformat(),
                "lot_number": row.lot_number,
                "notes": row.notes,
            }
            for row in rows
        ],
    }


@router.patch("/{inventory_id}/lot", response_model=InventoryLotUpdateResponse)
async def update_inventory_lot(
    inventory_id: str,
    payload: InventoryLotUpdateRequest,
    current_user: TokenPayload = Depends(
        require_role(UserRole.PLATFORM_ADMIN, UserRole.TENANT_ADMIN, UserRole.OPERATOR)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context is required")
    if not payload.lot_number.strip():
        raise HTTPException(status_code=422, detail="Lot number is required")

    result = await db.execute(
        select(Inventory).where(
            Inventory.id == inventory_id,
            Inventory.tenant_id == current_user.tenant_id,
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory row not found")

    svc = InventoryService(db, current_user.tenant_id)
    try:
        updated = await svc.update_inventory_lot(
            inventory_id=inventory_id,
            lot_number=payload.lot_number,
            expiry_date=payload.expiry_date,
            reason=payload.reason,
            user_id=current_user.sub,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Commit is owned by get_db_session (unit-of-work); no mid-request commit here.
    return InventoryLotUpdateResponse(**updated)
