"""Client (cargo owner) management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user
from app.core.pagination import PaginationParams, paginate_window
from app.core.plan_limits import check_limit
from app.core.security import TokenPayload, UserRole
from app.models.client import Client

router = APIRouter()


class ClientCreate(BaseModel):
    name: str
    code: str
    contact_email: str | None = None
    contact_phone: str | None = None
    address: dict | None = None
    billing_enabled: bool = True
    portal_access: bool = True
    settings: dict | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: dict | None = None
    billing_enabled: bool | None = None
    portal_access: bool | None = None
    settings: dict | None = None
    is_active: bool | None = None


class ClientResponse(BaseModel):
    id: str
    tenant_id: str | None = None
    name: str
    code: str
    contact_email: str | None
    contact_phone: str | None = None
    address: dict | None = None
    billing_enabled: bool
    portal_access: bool
    is_active: bool
    settings: dict | None = None


@router.get("/")
async def list_clients(
    page: PaginationParams = Depends(),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(Client).where(Client.is_active == True)  # noqa: E712
    if current_user.role != UserRole.PLATFORM_ADMIN:
        if not current_user.tenant_id:
            raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")
        query = query.where(Client.tenant_id == current_user.tenant_id)
    if current_user.role == UserRole.CLIENT_VIEWER and current_user.client_id:
        query = query.where(Client.id == current_user.client_id)

    result = await paginate_window(db, query.order_by(Client.name, Client.code, Client.id), page)
    result["items"] = [
        ClientResponse(
            id=c.id,
            tenant_id=c.tenant_id,
            name=c.name,
            code=c.code,
            contact_email=c.contact_email,
            contact_phone=c.contact_phone,
            address=c.address,
            billing_enabled=c.billing_enabled,
            portal_access=c.portal_access,
            is_active=c.is_active,
            settings=c.settings,
        )
        for c in result["items"]
    ]
    return result


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    _limits=Depends(check_limit("clients")),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if current_user.role not in (UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN):
        raise HTTPException(status_code=403, detail="Only tenant admins can create clients")

    if not current_user.tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Platform admin must specify tenant context via tenant_id in token or use tenant-specific endpoint",
        )

    client = Client(
        tenant_id=current_user.tenant_id,
        name=body.name,
        code=body.code,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        address=body.address,
        billing_enabled=body.billing_enabled,
        portal_access=body.portal_access,
        settings=body.settings,
    )
    db.add(client)
    await db.flush()
    return ClientResponse(
        id=client.id,
        tenant_id=client.tenant_id,
        name=client.name,
        code=client.code,
        contact_email=client.contact_email,
        contact_phone=client.contact_phone,
        address=client.address,
        billing_enabled=client.billing_enabled,
        portal_access=client.portal_access,
        is_active=client.is_active,
        settings=client.settings,
    )


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    body: ClientUpdate,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if current_user.role not in (UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN):
        raise HTTPException(status_code=403, detail="Only tenant admins can update clients")

    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if body.name is not None:
        client.name = body.name
    if body.code is not None:
        client.code = body.code
    if body.contact_email is not None:
        client.contact_email = body.contact_email
    if body.contact_phone is not None:
        client.contact_phone = body.contact_phone
    if body.address is not None:
        client.address = body.address
    if body.billing_enabled is not None:
        client.billing_enabled = body.billing_enabled
    if body.portal_access is not None:
        client.portal_access = body.portal_access
    if body.settings is not None:
        client.settings = body.settings
    if body.is_active is not None:
        client.is_active = body.is_active

    await db.flush()

    return ClientResponse(
        id=client.id,
        tenant_id=client.tenant_id,
        name=client.name,
        code=client.code,
        contact_email=client.contact_email,
        contact_phone=client.contact_phone,
        address=client.address,
        billing_enabled=client.billing_enabled,
        portal_access=client.portal_access,
        is_active=client.is_active,
        settings=client.settings,
    )
