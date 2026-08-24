"""Inventory operations API — moves, adjustments, cycle counts."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.idempotency_service import IdempotencyService
from app.services.inventory_service import InventoryService

router = APIRouter()


class MoveRequest(BaseModel):
    inventory_id: str
    to_location_id: str
    quantity: int
    reason: str | None = None


class AdjustRequest(BaseModel):
    inventory_id: str
    new_quantity: int
    reason: str = Field(min_length=3)


class AdjustAgentRequest(AdjustRequest):
    confirmation_token: str


class CycleCountItem(BaseModel):
    sku_id: str
    counted_quantity: int


class CycleCountRequest(BaseModel):
    location_id: str
    counts: list[CycleCountItem]


@router.post("/move")
async def move_inventory(
    body: MoveRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = InventoryService(db, current_user.tenant_id)
    return await svc.move_inventory(
        inventory_id=body.inventory_id,
        to_location_id=body.to_location_id,
        quantity=body.quantity,
        user_id=current_user.sub,
        reason=body.reason,
    )


@router.post("/adjust")
async def adjust_inventory(
    body: AdjustRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = InventoryService(db, current_user.tenant_id)
    return await svc.adjust_inventory(
        inventory_id=body.inventory_id,
        new_quantity=body.new_quantity,
        user_id=current_user.sub,
        reason=body.reason,
    )


@router.post("/adjust/preview")
async def preview_adjust_inventory(
    body: AdjustRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = InventoryService(db, current_user.tenant_id)
    return await svc.preview_adjust_inventory(
        inventory_id=body.inventory_id,
        new_quantity=body.new_quantity,
        reason=body.reason,
        user_id=current_user.sub,
    )


@router.post("/adjust/agent")
async def confirm_adjust_inventory_with_agent_token(
    body: AdjustAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent inventory adjustment",
            },
        )

    async def execute():
        svc = InventoryService(db, current_user.tenant_id)
        return await svc.confirm_adjust_inventory_with_token(
            inventory_id=body.inventory_id,
            new_quantity=body.new_quantity,
            reason=body.reason,
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="inventory.adjust.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/cycle-count")
async def cycle_count(
    body: CycleCountRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = InventoryService(db, current_user.tenant_id)
    return await svc.cycle_count(
        location_id=body.location_id,
        counts=[c.model_dump() for c in body.counts],
        user_id=current_user.sub,
    )
