"""Returns/RMA API — create, receive, disposition."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_role
from app.core.security import TokenPayload, UserRole
from app.models.returns import ReturnOrder
from app.services.returns_service import ReturnsService

router = APIRouter()


class ReturnLineInput(BaseModel):
    sku_id: str
    quantity: int
    reason: str | None = None


class CreateRMARequest(BaseModel):
    client_id: str
    warehouse_id: str
    rma_number: str
    lines: list[ReturnLineInput]
    original_order_id: str | None = None
    reason: str | None = None
    customer_name: str | None = None


class ReceiveReturnRequest(BaseModel):
    line_id: str
    quantity_received: int
    quantity_damaged: int = 0
    location_id: str | None = None


class DispositionRequest(BaseModel):
    line_id: str
    disposition: str  # restock | damaged | scrap | return_to_vendor
    restock_location_id: str | None = None


class RMAResponse(BaseModel):
    id: str
    rma_number: str
    status: str
    client_id: str
    reason: str | None
    customer_name: str | None


@router.get("/", response_model=list[RMAResponse])
async def list_returns(
    status: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(ReturnOrder)
    if current_user.role != UserRole.PLATFORM_ADMIN:
        query = query.where(ReturnOrder.tenant_id == current_user.tenant_id)
    if status:
        query = query.where(ReturnOrder.status == status)
    if current_user.role == UserRole.CLIENT_VIEWER and current_user.client_id:
        query = query.where(ReturnOrder.client_id == current_user.client_id)

    result = await db.execute(query.order_by(ReturnOrder.created_at.desc()).limit(100))
    return [
        RMAResponse(
            id=r.id,
            rma_number=r.rma_number,
            status=r.status,
            client_id=r.client_id,
            reason=r.reason,
            customer_name=r.customer_name,
        )
        for r in result.scalars()
    ]


@router.post("/", response_model=RMAResponse, status_code=201)
async def create_rma(
    body: CreateRMARequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReturnsService(db, current_user.tenant_id)
    rma = await svc.create_rma(
        client_id=body.client_id,
        warehouse_id=body.warehouse_id,
        rma_number=body.rma_number,
        lines=[line.model_dump() for line in body.lines],
        original_order_id=body.original_order_id,
        reason=body.reason,
        customer_name=body.customer_name,
    )
    return RMAResponse(
        id=rma.id,
        rma_number=rma.rma_number,
        status=rma.status,
        client_id=rma.client_id,
        reason=rma.reason,
        customer_name=rma.customer_name,
    )


@router.post("/{rma_id}/receive")
async def receive_return_items(
    rma_id: str,
    body: ReceiveReturnRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReturnsService(db, current_user.tenant_id)
    return await svc.receive_return(
        rma_id=rma_id,
        line_id=body.line_id,
        quantity_received=body.quantity_received,
        quantity_damaged=body.quantity_damaged,
        location_id=body.location_id,
        user_id=current_user.sub,
    )


@router.post("/{rma_id}/disposition")
async def process_disposition(
    rma_id: str,
    body: DispositionRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = ReturnsService(db, current_user.tenant_id)
    return await svc.process_disposition(
        rma_id=rma_id,
        line_id=body.line_id,
        disposition=body.disposition,
        restock_location_id=body.restock_location_id,
        user_id=current_user.sub,
    )
