"""Reports & Analytics API — KPI dashboard, order reports, activity log."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_role
from app.core.security import TokenPayload, UserRole
from app.services.reporting_service import ReportingService

router = APIRouter()


@router.get("/dashboard")
async def kpi_dashboard(
    warehouse_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Real-time KPI dashboard — orders, inventory, tasks, inbound."""
    svc = ReportingService(db, current_user.tenant_id)
    return await svc.get_dashboard_kpis(warehouse_id)


@router.get("/orders")
async def order_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    client_id: str | None = Query(None),
    format: str = Query("json"),  # json | csv
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Order fulfillment report by date range."""
    svc = ReportingService(db, current_user.tenant_id)
    data = await svc.get_order_report(start_date, end_date, client_id)

    if format == "csv":
        csv_str = svc.generate_report_csv(data)
        return StreamingResponse(
            iter([csv_str]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="orders-{start_date}-{end_date}.csv"'
            },
        )
    return data


@router.get("/inventory-summary")
async def inventory_summary(
    client_id: str | None = Query(None),
    format: str = Query("json"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Inventory summary grouped by SKU."""
    svc = ReportingService(db, current_user.tenant_id)

    cid = client_id
    if current_user.role == UserRole.CLIENT_VIEWER:
        cid = current_user.client_id

    data = await svc.get_inventory_summary(cid)

    if format == "csv":
        csv_str = svc.generate_report_csv(data)
        return StreamingResponse(
            iter([csv_str]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="inventory-summary.csv"'},
        )
    return data


@router.get("/activity")
async def activity_log(
    days: int = Query(7, le=90),
    transaction_type: str | None = Query(None),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Recent inventory transaction activity log."""
    svc = ReportingService(db, current_user.tenant_id)
    return await svc.get_activity_log(days, transaction_type)
