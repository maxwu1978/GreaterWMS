"""Cycle Count API — generate tasks, record counts, variance report."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.cycle_count_service import CycleCountService
from app.services.idempotency_service import IdempotencyService

router = APIRouter()


class GenerateCountRequest(BaseModel):
    warehouse_id: str
    zone_id: str | None = None
    location_ids: list[str] | None = None


class CountItem(BaseModel):
    sku_id: str
    counted_quantity: int


class RecordCountRequest(BaseModel):
    location_id: str
    counts: list[CountItem]


class RecordCountAgentRequest(RecordCountRequest):
    confirmation_token: str


@router.post("/generate")
async def generate_count_tasks(
    body: GenerateCountRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Generate cycle count tasks for warehouse/zone/locations."""
    svc = CycleCountService(db, current_user.tenant_id)
    return await svc.generate_count_tasks(body.warehouse_id, body.zone_id, body.location_ids)


@router.post("/record")
async def record_count(
    body: RecordCountRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Record counted quantities at a location. Returns variance per SKU."""
    svc = CycleCountService(db, current_user.tenant_id)
    return await svc.record_count(
        body.location_id, [c.model_dump() for c in body.counts], current_user.sub
    )


@router.post("/record/preview")
async def preview_record_count(
    body: RecordCountRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = CycleCountService(db, current_user.tenant_id)
    return await svc.preview_record_count(
        location_id=body.location_id,
        counts=[c.model_dump() for c in body.counts],
        user_id=current_user.sub,
    )


@router.post("/record/agent")
async def confirm_record_count_with_agent_token(
    body: RecordCountAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent inventory count",
            },
        )

    async def execute():
        svc = CycleCountService(db, current_user.tenant_id)
        return await svc.confirm_record_count_with_token(
            location_id=body.location_id,
            counts=[c.model_dump() for c in body.counts],
            confirmation_token=body.confirmation_token,
            user_id=current_user.sub,
            idempotency_key=x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="inventory.count.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.get("/variance-report")
async def variance_report(
    reference_id: str | None = Query(None),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Get variance report from cycle counts."""
    svc = CycleCountService(db, current_user.tenant_id)
    return await svc.get_variance_report(reference_id)
