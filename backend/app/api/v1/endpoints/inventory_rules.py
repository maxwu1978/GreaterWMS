"""Inventory rules API — safety stock, putaway rules, freeze, aging."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.idempotency_service import IdempotencyService
from app.services.inventory_rules_service import InventoryRulesService

router = APIRouter()


# ─── Safety Stock ───


class SetSafetyStockRequest(BaseModel):
    sku_id: str
    safety_stock: int


@router.get("/reorder-alerts")
async def reorder_alerts(
    warehouse_id: str = Query("wh-dfw1"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Check SKUs below safety stock / reorder point."""
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.check_reorder_alerts(warehouse_id)


@router.post("/safety-stock")
async def set_safety_stock(
    body: SetSafetyStockRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.set_safety_stock(body.sku_id, body.safety_stock)


# ─── Smart Putaway ───


@router.get("/putaway-suggest")
async def smart_putaway_suggest(
    warehouse_id: str,
    sku_id: str,
    quantity: int = 1,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Smart putaway location suggestion with rules engine."""
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.suggest_putaway_location(warehouse_id, sku_id, quantity)


# ─── Freeze / Unfreeze ───


class FreezeRequest(BaseModel):
    inventory_id: str
    reason: str


class FreezeAgentRequest(FreezeRequest):
    confirmation_token: str


class UnfreezeRequest(BaseModel):
    inventory_id: str
    quantity: int
    reason: str = "Inventory hold release"


class UnfreezeAgentRequest(UnfreezeRequest):
    confirmation_token: str


@router.post("/freeze")
async def freeze_inventory(
    body: FreezeRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Freeze inventory — prevent allocation for quality hold."""
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.freeze_inventory(body.inventory_id, body.reason, current_user.sub)


@router.post("/freeze/preview")
async def preview_freeze_inventory(
    body: FreezeRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.preview_freeze_inventory(body.inventory_id, body.reason, current_user.sub)


@router.post("/freeze/agent")
async def confirm_freeze_inventory_with_agent_token(
    body: FreezeAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent inventory hold",
            },
        )

    async def execute():
        svc = InventoryRulesService(db, current_user.tenant_id)
        return await svc.confirm_freeze_inventory_with_token(
            inventory_id=body.inventory_id,
            reason=body.reason,
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="inventory.hold.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/unfreeze")
async def unfreeze_inventory(
    body: UnfreezeRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Release previously frozen inventory."""
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.unfreeze_inventory(
        body.inventory_id,
        body.quantity,
        body.reason,
        current_user.sub,
    )


@router.post("/unfreeze/preview")
async def preview_unfreeze_inventory(
    body: UnfreezeRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.preview_unfreeze_inventory(
        body.inventory_id,
        body.quantity,
        body.reason,
        current_user.sub,
    )


@router.post("/unfreeze/agent")
async def confirm_unfreeze_inventory_with_agent_token(
    body: UnfreezeAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent inventory release",
            },
        )

    async def execute():
        svc = InventoryRulesService(db, current_user.tenant_id)
        return await svc.confirm_unfreeze_inventory_with_token(
            inventory_id=body.inventory_id,
            quantity=body.quantity,
            reason=body.reason,
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="inventory.release.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


# ─── Aging Report ───


@router.get("/aging")
async def aging_report(
    warehouse_id: str = Query("wh-dfw1"),
    days: int = Query(90),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Inventory aging report — items older than N days."""
    svc = InventoryRulesService(db, current_user.tenant_id)
    return await svc.get_aging_report(warehouse_id, days)
