"""
Client Portal API — read-only endpoints for cargo owners.

Cargo owners (client_viewer role) access these endpoints to:
- View their inventory levels
- Track their orders and shipments
- View and download invoices
- See activity summary / dashboard stats
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user
from app.core.security import TokenPayload, UserRole
from app.models.billing import Invoice
from app.models.client import Client
from app.models.inventory import SKU, Inventory
from app.models.order import InboundOrder, OutboundOrder
from app.models.tenant import Tenant

router = APIRouter()


class PortalInventoryItem(BaseModel):
    sku_code: str
    sku_name: str
    location_barcode: str | None = None
    quantity_on_hand: int
    quantity_allocated: int
    quantity_available: int
    lot_number: str | None
    expiry_date: str | None


class PortalOrderSummary(BaseModel):
    id: str
    order_number: str
    status: str
    reference_number: str | None
    carrier: str | None = None
    tracking_number: str | None = None


class PortalInvoiceSummary(BaseModel):
    id: str
    invoice_number: str
    status: str
    total_amount: float
    currency: str
    issued_date: str | None
    due_date: str | None


class PortalDashboard(BaseModel):
    client_name: str
    client_code: str
    client_contact_email: str | None = None
    client_contact_phone: str | None = None
    warehouse_operator_name: str | None = None
    total_skus: int
    total_units_on_hand: int
    pending_inbound: int
    pending_outbound: int
    recent_shipments: int
    outstanding_invoices: float


async def _resolve_portal_client_id(
    *,
    db: AsyncSession,
    current_user: TokenPayload,
    client_id: str | None,
) -> str:
    """Resolve the effective portal client and reject unknown client IDs.

    Deliberately NOT app.core.deps.client_scope_filter: portal semantics differ.
    A client viewer with no client_id claim is rejected (403) rather than left
    unscoped, tenant admins/operators must name a client via query param (which
    is validated against the tenant), and platform admins are rejected outright.
    """
    if current_user.role == UserRole.CLIENT_VIEWER:
        if not current_user.client_id:
            raise HTTPException(status_code=403, detail="Client ID missing from token")
        return current_user.client_id

    if current_user.role not in (UserRole.TENANT_ADMIN, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Not authorized for portal access")

    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")

    result = await db.execute(
        select(Client.id).where(
            Client.id == client_id,
            Client.tenant_id == current_user.tenant_id,
            Client.is_active.is_(True),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Client not found")

    return client_id


@router.get("/dashboard", response_model=PortalDashboard)
async def portal_dashboard(
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Client dashboard — key metrics at a glance."""
    cid = await _resolve_portal_client_id(db=db, current_user=current_user, client_id=client_id)

    client_result = await db.execute(
        select(Client).where(
            Client.id == cid,
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = client_result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    tenant_result = await db.execute(select(Tenant.name).where(Tenant.id == client.tenant_id))
    tenant_name = tenant_result.scalar_one_or_none()

    # Total SKUs
    sku_count = (
        await db.execute(
            select(func.count(func.distinct(Inventory.sku_id))).where(
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.client_id == cid,
                Inventory.quantity_on_hand > 0,
            )
        )
    ).scalar() or 0

    # Total units
    total_units = (
        await db.execute(
            select(func.sum(Inventory.quantity_on_hand)).where(
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.client_id == cid,
                Inventory.quantity_on_hand > 0,
            )
        )
    ).scalar() or 0

    # Pending inbound
    pending_in = (
        await db.execute(
            select(func.count(InboundOrder.id)).where(
                InboundOrder.tenant_id == current_user.tenant_id,
                InboundOrder.client_id == cid,
                InboundOrder.status.in_(["expected", "arrived", "receiving", "putaway"]),
            )
        )
    ).scalar() or 0

    # Pending outbound
    pending_out = (
        await db.execute(
            select(func.count(OutboundOrder.id)).where(
                OutboundOrder.tenant_id == current_user.tenant_id,
                OutboundOrder.client_id == cid,
                OutboundOrder.status.in_(
                    ["pending", "allocated", "picking", "picked", "packing", "packed"]
                ),
            )
        )
    ).scalar() or 0

    # Recent shipments (last 30 days-ish)
    recent_ship = (
        await db.execute(
            select(func.count(OutboundOrder.id)).where(
                OutboundOrder.tenant_id == current_user.tenant_id,
                OutboundOrder.client_id == cid,
                OutboundOrder.status == "shipped",
            )
        )
    ).scalar() or 0

    # Outstanding invoices
    outstanding = (
        await db.execute(
            select(func.sum(Invoice.total_amount)).where(
                Invoice.tenant_id == current_user.tenant_id,
                Invoice.client_id == cid,
                Invoice.status.in_(["sent", "overdue"]),
            )
        )
    ).scalar() or 0

    return PortalDashboard(
        client_name=client.name,
        client_code=client.code,
        client_contact_email=client.contact_email,
        client_contact_phone=client.contact_phone,
        warehouse_operator_name=tenant_name,
        total_skus=sku_count,
        total_units_on_hand=total_units,
        pending_inbound=pending_in,
        pending_outbound=pending_out,
        recent_shipments=recent_ship,
        outstanding_invoices=float(outstanding),
    )


@router.get("/inventory", response_model=list[PortalInventoryItem])
async def portal_inventory(
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Client inventory view — all SKUs with quantities."""
    cid = await _resolve_portal_client_id(db=db, current_user=current_user, client_id=client_id)

    result = await db.execute(
        select(Inventory, SKU)
        .join(SKU, SKU.id == Inventory.sku_id)
        .where(
            Inventory.tenant_id == current_user.tenant_id,
            SKU.tenant_id == current_user.tenant_id,
            Inventory.client_id == cid,
            Inventory.quantity_on_hand > 0,
        )
        .order_by(SKU.sku_code)
    )

    items = []
    for inv, sku in result.all():
        items.append(
            PortalInventoryItem(
                sku_code=sku.sku_code,
                sku_name=sku.name,
                quantity_on_hand=inv.quantity_on_hand,
                quantity_allocated=inv.quantity_allocated,
                quantity_available=inv.quantity_available,
                lot_number=inv.lot_number,
                expiry_date=inv.expiry_date.isoformat() if inv.expiry_date else None,
            )
        )

    return items


@router.get("/orders/inbound", response_model=list[PortalOrderSummary])
async def portal_inbound_orders(
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    cid = await _resolve_portal_client_id(db=db, current_user=current_user, client_id=client_id)

    result = await db.execute(
        select(InboundOrder)
        .where(
            InboundOrder.tenant_id == current_user.tenant_id,
            InboundOrder.client_id == cid,
        )
        .order_by(InboundOrder.created_at.desc())
        .limit(50)
    )
    return [
        PortalOrderSummary(
            id=o.id,
            order_number=o.order_number,
            status=o.status,
            reference_number=o.reference_number,
        )
        for o in result.scalars()
    ]


@router.get("/orders/outbound", response_model=list[PortalOrderSummary])
async def portal_outbound_orders(
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    cid = await _resolve_portal_client_id(db=db, current_user=current_user, client_id=client_id)

    result = await db.execute(
        select(OutboundOrder)
        .where(
            OutboundOrder.tenant_id == current_user.tenant_id,
            OutboundOrder.client_id == cid,
        )
        .order_by(OutboundOrder.created_at.desc())
        .limit(50)
    )
    return [
        PortalOrderSummary(
            id=o.id,
            order_number=o.order_number,
            status=o.status,
            reference_number=o.reference_number,
            carrier=o.carrier,
            tracking_number=o.tracking_number,
        )
        for o in result.scalars()
    ]


@router.get("/invoices", response_model=list[PortalInvoiceSummary])
async def portal_invoices(
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    cid = await _resolve_portal_client_id(db=db, current_user=current_user, client_id=client_id)

    result = await db.execute(
        select(Invoice)
        .where(
            Invoice.tenant_id == current_user.tenant_id,
            Invoice.client_id == cid,
        )
        .order_by(Invoice.created_at.desc())
        .limit(50)
    )
    return [
        PortalInvoiceSummary(
            id=inv.id,
            invoice_number=inv.invoice_number,
            status=inv.status,
            total_amount=float(inv.total_amount),
            currency=inv.currency,
            issued_date=inv.issued_date.isoformat() if inv.issued_date else None,
            due_date=inv.due_date.isoformat() if inv.due_date else None,
        )
        for inv in result.scalars()
    ]
