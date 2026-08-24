"""Task endpoints — AGV-ready task queue API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_permission
from app.core.security import TokenPayload, UserPermission, UserRole
from app.models.inventory import SKU
from app.models.order import HandlingUnit
from app.models.task import AssignedType, Task
from app.models.warehouse import Location
from app.services.putaway_execution_service import PutawayExecutionService
from app.services.putaway_task_repair_service import repair_missing_putaway_tasks

router = APIRouter()


class TaskResponse(BaseModel):
    id: str
    created_at: str | None = None
    warehouse_id: str
    task_type: str
    status: str
    priority: int
    sku_id: str | None
    quantity: int
    handling_unit_id: str | None = None
    execution_mode: str
    source_location_id: str | None
    destination_location_id: str | None
    assigned_type: str
    assigned_to: str | None
    reference_type: str | None = None
    reference_id: str | None = None
    sku_code: str | None = None
    sku_barcode: str | None = None
    source_location_barcode: str | None = None
    destination_location_barcode: str | None = None
    handling_unit_code: str | None = None
    handling_unit_status: str | None = None
    package_count: int | None = None
    pallet_count: int | None = None
    rent_free_days: int | None = None
    measured_weight_kg: float | None = None
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None
    lot_number: str | None = None
    expiry_date: str | None = None
    agv_eligible: bool = False
    execution_reason: str | None = None


class TaskAssign(BaseModel):
    assigned_type: str  # 'human' or 'agv'
    assigned_to: str  # user_id or 'agv:unit-003'


class PutawayTaskRepairRequest(BaseModel):
    tenant_id: str | None = Field(
        default=None,
        description="Platform admins may target a tenant; tenant users always use their own tenant.",
    )
    warehouse_id: str | None = None
    inbound_order_id: str | None = None
    dry_run: bool = False
    limit: int = Field(default=100, ge=1, le=1000)


class PutawayTaskRepairResponse(BaseModel):
    tenant_id: str
    scanned_orders: int
    created_tasks: int
    updated_tasks: int
    skipped_orders: int
    errors: list[str]


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    warehouse_id: str | None = Query(None),
    status: str | None = Query(None),
    assigned_type: str | None = Query(None),
    assigned_to: str | None = Query(None),
    task_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    List tasks. AGV scheduler uses this endpoint to poll for pending tasks:
    GET /api/v1/tasks?status=pending&assigned_type=unassigned&task_type=pick&warehouse_id=xxx
    """
    query = select(Task).where(Task.tenant_id == current_user.tenant_id)
    if warehouse_id:
        query = query.where(Task.warehouse_id == warehouse_id)
    if status:
        query = query.where(Task.status == status)
    if assigned_type:
        query = query.where(Task.assigned_type == assigned_type)
    if assigned_to:
        if current_user.role == UserRole.OPERATOR and assigned_to != current_user.sub:
            raise HTTPException(status_code=403, detail="Operators can only view their own assigned tasks")
        query = query.where(Task.assigned_to == assigned_to)
    elif current_user.role == UserRole.OPERATOR and assigned_type == AssignedType.HUMAN.value:
        query = query.where(Task.assigned_to == current_user.sub)
    if task_type:
        query = query.where(Task.task_type == task_type)

    result = await db.execute(query.order_by(Task.priority, Task.created_at).limit(limit))
    tasks = result.scalars().all()

    sku_ids = {task.sku_id for task in tasks if task.sku_id}
    location_ids = {
        location_id
        for task in tasks
        for location_id in (task.source_location_id, task.destination_location_id)
        if location_id
    }

    sku_map: dict[str, SKU] = {}
    if sku_ids:
        sku_result = await db.execute(
            select(SKU).where(SKU.id.in_(sku_ids), SKU.tenant_id == current_user.tenant_id)
        )
        sku_map = {sku.id: sku for sku in sku_result.scalars()}

    location_map: dict[str, Location] = {}
    if location_ids:
        location_result = await db.execute(
            select(Location).where(
                Location.id.in_(location_ids),
                Location.tenant_id == current_user.tenant_id,
            )
        )
        location_map = {location.id: location for location in location_result.scalars()}

    handling_unit_ids = {task.handling_unit_id for task in tasks if task.handling_unit_id}
    handling_unit_map: dict[str, HandlingUnit] = {}
    if handling_unit_ids:
        handling_unit_result = await db.execute(
            select(HandlingUnit).where(
                HandlingUnit.id.in_(handling_unit_ids),
                HandlingUnit.tenant_id == current_user.tenant_id,
            )
        )
        handling_unit_map = {unit.id: unit for unit in handling_unit_result.scalars()}

    execution_service = PutawayExecutionService(db, current_user.tenant_id)

    responses: list[TaskResponse] = []
    for t in tasks:
        execution = await execution_service.decide(
            warehouse_id=t.warehouse_id,
            source_location_id=t.source_location_id,
            handling_unit_id=t.handling_unit_id,
        )
        handling_unit = handling_unit_map.get(t.handling_unit_id) if t.handling_unit_id else None
        responses.append(
            TaskResponse(
                id=t.id,
                created_at=t.created_at.isoformat() if t.created_at else None,
                warehouse_id=t.warehouse_id,
                task_type=t.task_type,
                status=t.status,
                priority=t.priority,
                sku_id=t.sku_id,
                quantity=t.quantity,
                handling_unit_id=t.handling_unit_id,
                execution_mode=t.execution_mode or execution.mode,
                source_location_id=t.source_location_id,
                destination_location_id=t.destination_location_id,
                assigned_type=t.assigned_type,
                assigned_to=t.assigned_to,
                reference_type=t.reference_type,
                reference_id=t.reference_id,
                sku_code=sku_map[t.sku_id].sku_code if t.sku_id in sku_map else None,
                sku_barcode=sku_map[t.sku_id].barcode if t.sku_id in sku_map else None,
                source_location_barcode=location_map[t.source_location_id].barcode
                if t.source_location_id in location_map
                else None,
                destination_location_barcode=location_map[t.destination_location_id].barcode
                if t.destination_location_id in location_map
                else None,
                handling_unit_code=handling_unit.unit_code if handling_unit else None,
                handling_unit_status=handling_unit.status if handling_unit else None,
                package_count=handling_unit.package_count if handling_unit else None,
                pallet_count=handling_unit.pallet_count if handling_unit else None,
                rent_free_days=handling_unit.rent_free_days if handling_unit else None,
                measured_weight_kg=float(handling_unit.measured_weight_kg)
                if handling_unit and handling_unit.measured_weight_kg is not None
                else None,
                external_tracking_number=handling_unit.external_tracking_number
                if handling_unit
                else None,
                external_carton_mark=handling_unit.external_carton_mark if handling_unit else None,
                external_customer_barcode=handling_unit.external_customer_barcode
                if handling_unit
                else None,
                lot_number=handling_unit.lot_number if handling_unit else None,
                expiry_date=handling_unit.expiry_date.isoformat()
                if handling_unit and handling_unit.expiry_date
                else None,
                agv_eligible=execution.agv_eligible,
                execution_reason=execution.reason,
            )
        )
    return responses


@router.post("/repairs/putaway", response_model=PutawayTaskRepairResponse)
async def repair_putaway_task_records(
    body: PutawayTaskRepairRequest,
    current_user: TokenPayload = Depends(require_permission(UserPermission.MASTER_DATA_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = body.tenant_id if current_user.role == UserRole.PLATFORM_ADMIN else current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="A tenant scope is required for putaway repair")

    stats = await repair_missing_putaway_tasks(
        db,
        tenant_id=tenant_id,
        warehouse_id=body.warehouse_id,
        inbound_order_id=body.inbound_order_id,
        dry_run=body.dry_run,
        limit=body.limit,
    )
    return PutawayTaskRepairResponse(
        tenant_id=tenant_id,
        scanned_orders=stats.scanned_orders,
        created_tasks=stats.created_tasks,
        updated_tasks=stats.updated_tasks,
        skipped_orders=stats.skipped_orders,
        errors=stats.errors,
    )
