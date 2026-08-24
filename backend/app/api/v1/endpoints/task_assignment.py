"""Task assignment API — assign tasks to employees, auto-distribute, workload view."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_role
from app.core.security import TokenPayload, UserRole
from app.services.task_assignment_service import TaskAssignmentService

router = APIRouter()


class AssignRequest(BaseModel):
    task_id: str
    user_id: str


class AutoAssignRequest(BaseModel):
    warehouse_id: str
    user_ids: list[str] | None = None  # None = all active operators
    max_tasks_per_worker: int = 10


@router.post("/assign")
async def assign_task(
    body: AssignRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Assign a specific task to a specific employee."""
    svc = TaskAssignmentService(db, current_user.tenant_id)
    return await svc.assign_task(body.task_id, body.user_id)


@router.post("/auto-assign")
async def auto_assign_tasks(
    body: AutoAssignRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Auto-distribute all pending tasks evenly across workers."""
    svc = TaskAssignmentService(db, current_user.tenant_id)
    return await svc.auto_assign_tasks(
        warehouse_id=body.warehouse_id,
        user_ids=body.user_ids,
        max_tasks_per_worker=body.max_tasks_per_worker,
    )


@router.get("/my-tasks")
async def my_tasks(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get tasks assigned to the current logged-in user."""
    svc = TaskAssignmentService(db, current_user.tenant_id)
    return await svc.get_my_tasks(current_user.sub)


@router.get("/workload")
async def workload_summary(
    warehouse_id: str = Query("wh-dfw1"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """View task distribution across all workers (supervisor dashboard)."""
    svc = TaskAssignmentService(db, current_user.tenant_id)
    return await svc.get_workload_summary(warehouse_id)
