"""Picking & Shipping API — allocation, pick confirm, pack verify, ship confirm."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.idempotency_service import IdempotencyService
from app.services.picking_service import PickingService
from app.services.putaway_service import PutawayService
from app.services.shipping_service import ShippingService

router = APIRouter()


class AllocateRequest(BaseModel):
    order_id: str


class ConfirmPickRequest(BaseModel):
    task_id: str
    quantity_picked: int  # Must be > 0, validated in service layer


class ConfirmPickAgentRequest(ConfirmPickRequest):
    confirmation_token: str


class ShortPickRequest(BaseModel):
    task_id: str
    quantity_available: int
    reason: str


class ShortPickAgentRequest(ShortPickRequest):
    confirmation_token: str


class PutawayAllocationItem(BaseModel):
    location_id: str
    quantity: int


class ConfirmPutawayRequest(BaseModel):
    task_id: str
    destination_location_id: str
    allocations: list[PutawayAllocationItem] | None = None


class ConfirmPutawayAgentRequest(ConfirmPutawayRequest):
    confirmation_token: str


class SuggestLocationRequest(BaseModel):
    warehouse_id: str
    sku_id: str
    quantity: int
    source_location_id: str | None = None


class PackVerifyItem(BaseModel):
    sku_id: str
    quantity: int


class PackVerifyRequest(BaseModel):
    order_id: str
    scanned_items: list[PackVerifyItem]


class PackVerifyAgentRequest(PackVerifyRequest):
    confirmation_token: str


class ShipConfirmRequest(BaseModel):
    order_id: str
    carrier: str
    tracking_number: str
    service_level: str | None = None
    shipping_cost: float | None = None


class ShipConfirmAgentRequest(ShipConfirmRequest):
    confirmation_token: str


# --- Putaway ---


@router.post("/putaway/suggest-location")
async def suggest_putaway_location(
    body: SuggestLocationRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = PutawayService(db, current_user.tenant_id)
    return await svc.suggest_location(
        body.warehouse_id, body.sku_id, body.quantity, exclude_location_id=body.source_location_id
    )


@router.post("/putaway/confirm")
async def confirm_putaway(
    body: ConfirmPutawayRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = PutawayService(db, current_user.tenant_id)
        return await svc.confirm_putaway(
            body.task_id,
            body.destination_location_id,
            current_user.sub,
            allocations=[item.model_dump() for item in body.allocations]
            if body.allocations
            else None,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.putaway.confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/putaway/confirm/preview")
async def preview_putaway_confirmation(
    body: ConfirmPutawayRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = PutawayService(db, current_user.tenant_id)
    return await svc.preview_putaway_confirmation(
        task_id=body.task_id,
        destination_location_id=body.destination_location_id,
        allocations=[item.model_dump() for item in body.allocations] if body.allocations else None,
        user_id=current_user.sub,
    )


@router.post("/putaway/confirm/agent")
async def confirm_putaway_with_agent_token(
    body: ConfirmPutawayAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent putaway confirmation",
            },
        )

    async def execute():
        svc = PutawayService(db, current_user.tenant_id)
        return await svc.confirm_putaway_with_token(
            task_id=body.task_id,
            destination_location_id=body.destination_location_id,
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            allocations=[item.model_dump() for item in body.allocations]
            if body.allocations
            else None,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.putaway.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


# --- Picking ---


@router.post("/pick/allocate")
async def allocate_order(
    body: AllocateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = PickingService(db, current_user.tenant_id)
    return await svc.allocate_order(body.order_id)


@router.post("/pick/create-tasks")
async def create_pick_tasks(
    body: AllocateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = PickingService(db, current_user.tenant_id)
    task_ids = await svc.create_pick_tasks(body.order_id)
    return {"task_ids": task_ids}


@router.post("/pick/confirm")
async def confirm_pick(
    body: ConfirmPickRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = PickingService(db, current_user.tenant_id)
        return await svc.confirm_pick(body.task_id, body.quantity_picked, current_user.sub)

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.pick.confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/pick/confirm/preview")
async def preview_pick_confirmation(
    body: ConfirmPickRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = PickingService(db, current_user.tenant_id)
    return await svc.preview_pick_confirmation(
        task_id=body.task_id,
        quantity_picked=body.quantity_picked,
        user_id=current_user.sub,
    )


@router.post("/pick/confirm/agent")
async def confirm_pick_with_agent_token(
    body: ConfirmPickAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent pick confirmation",
            },
        )

    async def execute():
        svc = PickingService(db, current_user.tenant_id)
        return await svc.confirm_pick_with_token(
            task_id=body.task_id,
            quantity_picked=body.quantity_picked,
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.pick.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/pick/short/preview")
async def preview_pick_short(
    body: ShortPickRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = PickingService(db, current_user.tenant_id)
    return await svc.preview_pick_short(
        task_id=body.task_id,
        quantity_available=body.quantity_available,
        reason=body.reason,
        user_id=current_user.sub,
    )


@router.post("/pick/short/agent")
async def confirm_pick_short_with_agent_token(
    body: ShortPickAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent pick short confirmation",
            },
        )

    async def execute():
        svc = PickingService(db, current_user.tenant_id)
        return await svc.confirm_pick_short_with_token(
            task_id=body.task_id,
            quantity_available=body.quantity_available,
            reason=body.reason,
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.pick.short.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


# --- Packing & Shipping ---


@router.post("/pack/verify")
async def verify_pack(
    body: PackVerifyRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = ShippingService(db, current_user.tenant_id)
        return await svc.verify_pack(
            body.order_id,
            [item.model_dump() for item in body.scanned_items],
            current_user.sub,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.pack.verify",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/pack/verify/preview")
async def preview_pack_verification(
    body: PackVerifyRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ShippingService(db, current_user.tenant_id)
    return await svc.preview_pack_verification(
        order_id=body.order_id,
        scanned_items=[item.model_dump() for item in body.scanned_items],
        user_id=current_user.sub,
    )


@router.post("/pack/verify/agent")
async def confirm_pack_with_agent_token(
    body: PackVerifyAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent pack verification",
            },
        )

    async def execute():
        svc = ShippingService(db, current_user.tenant_id)
        return await svc.confirm_pack_with_token(
            order_id=body.order_id,
            scanned_items=[item.model_dump() for item in body.scanned_items],
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.pack.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/ship/confirm")
async def ship_confirm(
    body: ShipConfirmRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    async def execute():
        svc = ShippingService(db, current_user.tenant_id)
        return await svc.ship_confirm(
            order_id=body.order_id,
            carrier=body.carrier,
            tracking_number=body.tracking_number,
            service_level=body.service_level,
            shipping_cost=body.shipping_cost,
            user_id=current_user.sub,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.ship.confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/ship/confirm/preview")
async def preview_ship_confirmation(
    body: ShipConfirmRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ShippingService(db, current_user.tenant_id)
    return await svc.preview_ship_confirmation(
        order_id=body.order_id,
        carrier=body.carrier,
        tracking_number=body.tracking_number,
        service_level=body.service_level,
        shipping_cost=body.shipping_cost,
        user_id=current_user.sub,
    )


@router.post("/ship/confirm/agent")
async def confirm_ship_with_agent_token(
    body: ShipConfirmAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent ship confirmation",
            },
        )

    async def execute():
        svc = ShippingService(db, current_user.tenant_id)
        return await svc.confirm_ship_with_token(
            order_id=body.order_id,
            carrier=body.carrier,
            tracking_number=body.tracking_number,
            confirmation_token=body.confirmation_token,
            service_level=body.service_level,
            shipping_cost=body.shipping_cost,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="fulfillment.ship.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.get("/ship/{order_id}/summary")
async def shipment_summary(
    order_id: str,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR, UserRole.CLIENT_VIEWER)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ShippingService(db, current_user.tenant_id)
    return await svc.get_shipment_summary(order_id)
