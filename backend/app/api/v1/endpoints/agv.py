"""
AGV API — endpoints consumed by AGV fleet management systems (WCS/RCS).

These endpoints follow a pull-based pattern:
1. AGV scheduler polls GET /agv/tasks/pending for available work
2. Claims a task via POST /agv/tasks/{id}/assign
3. Reports progress via POST /agv/tasks/{id}/start, /complete, /fail
4. Gets warehouse map via GET /agv/locations/{warehouse_id}

Authentication: AGV systems use a service account JWT with operator role.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.agv_service import AGVService

router = APIRouter()


class AssignTaskRequest(BaseModel):
    agv_unit_id: str


class CompleteTaskRequest(BaseModel):
    agv_unit_id: str
    actual_quantity: int | None = None


class FailTaskRequest(BaseModel):
    agv_unit_id: str
    reason: str


class AGVTaskLocation(BaseModel):
    location_id: str | None = None
    barcode: str | None = None
    coordinate_x: float | None = None
    coordinate_y: float | None = None
    coordinate_z: float | None = None


class AGVHandlingUnitSummary(BaseModel):
    unit_code: str | None = None
    unit_type: str | None = None
    status: str | None = None
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None
    measured_weight_kg: float | None = None
    package_count: int | None = None
    pallet_count: int | None = None
    rent_free_days: int | None = None


class PendingAGVTaskResponse(BaseModel):
    task_id: str
    task_type: str
    priority: int
    sku_id: str | None = None
    quantity: int
    lpn: str | None = None
    handling_unit_id: str | None = None
    handling_unit_code: str | None = None
    handling_unit_status: str | None = None
    package_count: int | None = None
    pallet_count: int | None = None
    rent_free_days: int | None = None
    measured_weight_kg: float | None = None
    external_tracking_number: str | None = None
    external_carton_mark: str | None = None
    external_customer_barcode: str | None = None
    execution_mode: str
    agv_eligible: bool = False
    execution_reason: str | None = None
    source_barcode: str | None = None
    destination_barcode: str | None = None
    handling_unit: AGVHandlingUnitSummary | None = None
    source: AGVTaskLocation | None = None
    destination: AGVTaskLocation | None = None
    reference_type: str | None = None
    reference_id: str | None = None
    created_at: str | None = None


@router.get("/tasks/pending", response_model=list[PendingAGVTaskResponse])
async def get_pending_agv_tasks(
    warehouse_id: str,
    task_types: str | None = Query(None, description="Comma-separated: pick,putaway,move"),
    limit: int = Query(20, le=100),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Poll for pending tasks that AGV can execute. Includes location coordinates."""
    svc = AGVService(db, current_user.tenant_id)
    types = task_types.split(",") if task_types else None
    return await svc.get_pending_tasks(warehouse_id, types, limit)


@router.post("/tasks/{task_id}/assign")
async def assign_task_to_agv(
    task_id: str,
    body: AssignTaskRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = AGVService(db, current_user.tenant_id)
    return await svc.assign_task(task_id, body.agv_unit_id)


@router.post("/tasks/{task_id}/start")
async def start_agv_task(
    task_id: str,
    body: AssignTaskRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = AGVService(db, current_user.tenant_id)
    return await svc.start_task(task_id, body.agv_unit_id)


@router.post("/tasks/{task_id}/complete")
async def complete_agv_task(
    task_id: str,
    body: CompleteTaskRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = AGVService(db, current_user.tenant_id)
    return await svc.complete_task(task_id, body.agv_unit_id, body.actual_quantity)


@router.post("/tasks/{task_id}/fail")
async def fail_agv_task(
    task_id: str,
    body: FailTaskRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = AGVService(db, current_user.tenant_id)
    return await svc.fail_task(task_id, body.agv_unit_id, body.reason)


# --- Warehouse Map ---


@router.get("/locations/{warehouse_id}")
async def get_agv_location_map(
    warehouse_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Get all AGV-accessible locations with coordinates for map/path planning."""
    svc = AGVService(db, current_user.tenant_id)
    return await svc.get_agv_accessible_locations(warehouse_id)


@router.get("/locations/{warehouse_id}/validate")
async def validate_agv_readiness(
    warehouse_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Validate that all AGV-accessible locations have proper coordinates."""
    svc = AGVService(db, current_user.tenant_id)
    return await svc.validate_coordinates(warehouse_id)
