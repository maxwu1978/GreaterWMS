"""Return analytics — reason breakdown, cost analysis, trends."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.inventory import SKU
from app.models.returns import ReturnOrder, ReturnOrderLine

router = APIRouter()


@router.get("/analytics")
async def return_analytics(
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Return reason breakdown + volume statistics."""
    tenant_id = current_user.tenant_id

    # Total returns
    total = (
        await db.execute(
            select(func.count(ReturnOrder.id)).where(ReturnOrder.tenant_id == tenant_id)
        )
    ).scalar() or 0

    # By status
    status_result = await db.execute(
        select(ReturnOrder.status, func.count(ReturnOrder.id))
        .where(ReturnOrder.tenant_id == tenant_id)
        .group_by(ReturnOrder.status)
    )
    by_status = {row[0]: row[1] for row in status_result.all()}

    # By reason
    reason_result = await db.execute(
        select(
            ReturnOrderLine.reason,
            func.count(ReturnOrderLine.id),
            func.sum(ReturnOrderLine.quantity_expected),
        )
        .where(
            ReturnOrderLine.tenant_id == tenant_id,
            ReturnOrderLine.reason.is_not(None),
        )
        .group_by(ReturnOrderLine.reason)
        .order_by(func.count(ReturnOrderLine.id).desc())
    )
    by_reason = [
        {"reason": row[0], "count": row[1], "total_units": row[2] or 0}
        for row in reason_result.all()
    ]

    # Top returned SKUs
    sku_result = await db.execute(
        select(SKU.sku_code, SKU.name, func.sum(ReturnOrderLine.quantity_expected).label("qty"))
        .join(SKU, SKU.id == ReturnOrderLine.sku_id)
        .where(
            ReturnOrderLine.tenant_id == tenant_id,
            SKU.tenant_id == tenant_id,
        )
        .group_by(SKU.sku_code, SKU.name)
        .order_by(func.sum(ReturnOrderLine.quantity_expected).desc())
        .limit(10)
    )
    top_skus = [{"sku_code": r[0], "name": r[1], "return_qty": r[2] or 0} for r in sku_result.all()]

    # Disposition summary
    disp_result = await db.execute(
        select(
            func.sum(ReturnOrderLine.quantity_restocked),
            func.sum(ReturnOrderLine.quantity_damaged),
            func.sum(ReturnOrderLine.quantity_scrapped),
        )
        .where(ReturnOrderLine.tenant_id == tenant_id)
    )
    disp = disp_result.one()

    return {
        "total_rmas": total,
        "by_status": by_status,
        "by_reason": by_reason,
        "top_returned_skus": top_skus,
        "disposition": {
            "restocked": disp[0] or 0,
            "damaged": disp[1] or 0,
            "scrapped": disp[2] or 0,
        },
    }
