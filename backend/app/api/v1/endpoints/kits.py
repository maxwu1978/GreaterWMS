"""Kit/Bundle API — create composite products, check availability."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_role
from app.core.security import TokenPayload, UserRole
from app.models.kit import Kit, KitComponent
from app.services.kit_service import KitService

router = APIRouter()


class KitComponentInput(BaseModel):
    sku_id: str
    quantity: int


class CreateKitRequest(BaseModel):
    client_id: str
    sku_id: str  # The kit's own SKU
    name: str
    components: list[KitComponentInput]


class KitResponse(BaseModel):
    id: str
    sku_id: str
    name: str
    client_id: str
    components: list[dict]


@router.get("/")
async def list_kits(
    client_id: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(Kit).where(Kit.is_active == True)  # noqa
    if current_user.role != UserRole.PLATFORM_ADMIN:
        query = query.where(Kit.tenant_id == current_user.tenant_id)
    if client_id:
        query = query.where(Kit.client_id == client_id)
    result = await db.execute(query.limit(500))
    kits = []
    for kit in result.scalars():
        comp_result = await db.execute(
            select(KitComponent).where(
                KitComponent.tenant_id == kit.tenant_id,
                KitComponent.kit_id == kit.id,
            )
        )
        kits.append(
            {
                "id": kit.id,
                "sku_id": kit.sku_id,
                "name": kit.name,
                "client_id": kit.client_id,
                "components": [
                    {"sku_id": c.component_sku_id, "quantity": c.quantity}
                    for c in comp_result.scalars()
                ],
            }
        )
    return kits


@router.post("/", status_code=201)
async def create_kit(
    body: CreateKitRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    svc = KitService(db, current_user.tenant_id)
    kit = await svc.create_kit(
        client_id=body.client_id,
        sku_id=body.sku_id,
        name=body.name,
        components=[c.model_dump() for c in body.components],
    )
    return {"id": kit.id, "name": kit.name, "sku_id": kit.sku_id}


@router.get("/availability/{sku_id}")
async def check_kit_availability(
    sku_id: str,
    quantity: int = 1,
    warehouse_id: str = "wh-dfw1",
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    svc = KitService(db, current_user.tenant_id)
    return await svc.check_availability(sku_id, quantity, warehouse_id)
