"""One-click fulfillment — process all pending orders in one call."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.order import OutboundOrder
from app.services.shipping_label_service import ShippingLabelService
from app.services.task_assignment_service import TaskAssignmentService
from app.services.wave_service import WaveService

router = APIRouter()


class OneClickRequest(BaseModel):
    warehouse_id: str = "wh-dfw1"
    auto_assign: bool = True
    auto_label: bool = True


@router.post("/process-all")
async def one_click_fulfill(
    body: OneClickRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    One-click: wave → allocate → assign tasks → print labels.
    Processes ALL pending outbound orders in the warehouse.
    """
    if not current_user.tenant_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="No tenant context.")
    results = {"steps": []}

    # 1. Create wave (allocate + generate pick tasks)
    wave_svc = WaveService(db, current_user.tenant_id)
    wave = await wave_svc.create_wave(warehouse_id=body.warehouse_id)

    if not wave.get("success") and wave.get("orders_count", 0) == 0:
        # Check if there are already allocated orders needing labels
        ready = await db.execute(
            select(OutboundOrder.id).where(
                OutboundOrder.warehouse_id == body.warehouse_id,
                OutboundOrder.status.in_(["allocated", "picking", "picked", "packed"]),
                OutboundOrder.tracking_number.is_(None),
            )
        )
        ready_ids = [r[0] for r in ready.all()]
        if not ready_ids:
            return {"success": True, "message": "No pending orders to process", "steps": []}
        results["steps"].append(
            {"step": "wave", "status": "skipped", "reason": "Orders already allocated"}
        )
    else:
        results["steps"].append(
            {
                "step": "wave",
                "status": "created",
                "wave_id": wave.get("wave_id"),
                "orders": wave.get("orders_count", 0),
                "tasks": wave.get("tasks_count", 0),
            }
        )

    # 2. Auto-assign tasks to workers
    if body.auto_assign:
        assign_svc = TaskAssignmentService(db, current_user.tenant_id)
        assign = await assign_svc.auto_assign_tasks(warehouse_id=body.warehouse_id)
        results["steps"].append(
            {
                "step": "auto_assign",
                "status": "done",
                "tasks_assigned": assign.get("total_assigned", 0),
                "workers_used": assign.get("workers_used", 0),
            }
        )

    # 3. Auto-print labels for all orders that need them
    if body.auto_label:
        ready = await db.execute(
            select(OutboundOrder.id).where(
                OutboundOrder.warehouse_id == body.warehouse_id,
                OutboundOrder.tracking_number.is_(None),
                OutboundOrder.status != "draft",
                OutboundOrder.status != "cancelled",
            )
        )
        order_ids = [r[0] for r in ready.all()]

        if order_ids:
            label_svc = ShippingLabelService(db, current_user.tenant_id)
            labels = []
            total_cost = 0
            for oid in order_ids:
                try:
                    label = await label_svc.buy_label(oid)
                    if label.get("success"):
                        labels.append(
                            {
                                "order_id": oid,
                                "tracking": label.get("tracking_number"),
                                "rate": label.get("rate"),
                            }
                        )
                        total_cost += label.get("rate", 0) or 0
                except Exception:
                    pass

            results["steps"].append(
                {
                    "step": "labels",
                    "status": "printed",
                    "count": len(labels),
                    "total_shipping_cost": round(total_cost, 2),
                    "labels": labels,
                }
            )

    results["success"] = True
    return results
