"""Wave management API — batch picking for multiple orders."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.wave_service import WaveService

router = APIRouter()


class CreateWaveRequest(BaseModel):
    warehouse_id: str
    order_ids: list[str] | None = None  # None = auto-select all pending
    group_by: str = "all"  # all | carrier | client
    max_orders: int = 50


@router.post("/create")
async def create_wave(
    body: CreateWaveRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create a picking wave from pending orders.
    Groups orders, allocates inventory, generates consolidated pick tasks.
    """
    svc = WaveService(db, current_user.tenant_id)
    return await svc.create_wave(
        warehouse_id=body.warehouse_id,
        order_ids=body.order_ids,
        group_by=body.group_by,
        max_orders=body.max_orders,
    )


@router.get("/progress/{wave_id}")
async def wave_progress(
    wave_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Get wave picking progress — completed vs total tasks."""
    svc = WaveService(db, current_user.tenant_id)
    return await svc.get_wave_progress(wave_id)
