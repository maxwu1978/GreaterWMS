"""
Reporting Service — KPI dashboard, analytics, and report generation.

Provides real-time and historical metrics for warehouse operations.
"""

import csv
import io
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.inventory import Inventory, InventoryTransaction
from app.models.order import InboundOrder, OutboundOrder
from app.models.task import Task, TaskStatus
from app.models.warehouse import Location


class ReportingService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def get_dashboard_kpis(self, warehouse_id: str | None = None) -> dict:
        """Real-time KPI dashboard for the warehouse."""

        today = datetime.now(UTC).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        active_outbound_statuses = ["pending", "allocated", "picking", "picked", "packing", "packed"]
        pending_inbound_statuses = ["expected", "arrived", "receiving"]
        last_7d_start = today_start - timedelta(days=7)

        outbound_filters = [OutboundOrder.tenant_id == self.tenant_id]
        inbound_filters = [InboundOrder.tenant_id == self.tenant_id]
        inventory_filters = [Inventory.tenant_id == self.tenant_id]
        task_filters = [Task.tenant_id == self.tenant_id]
        if warehouse_id:
            outbound_filters.append(OutboundOrder.warehouse_id == warehouse_id)
            inbound_filters.append(InboundOrder.warehouse_id == warehouse_id)
            inventory_filters.append(Inventory.warehouse_id == warehouse_id)
            task_filters.append(Task.warehouse_id == warehouse_id)

        # ─── Order Metrics ───
        order_row = (
            await self.db.execute(
                select(
                    func.sum(
                        case(
                            (OutboundOrder.status.in_(active_outbound_statuses), 1),
                            else_=0,
                        )
                    ).label("pending"),
                    func.sum(
                        case(
                            (
                                and_(
                                    OutboundOrder.status == "shipped",
                                    OutboundOrder.shipped_date >= today_start,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ).label("shipped_today"),
                    func.sum(
                        case(
                            (
                                and_(
                                    OutboundOrder.status == "shipped",
                                    OutboundOrder.shipped_date >= last_7d_start,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ).label("shipped_7d"),
                ).where(
                    *outbound_filters,
                    or_(
                        OutboundOrder.status.in_(active_outbound_statuses),
                        and_(
                            OutboundOrder.status == "shipped",
                            OutboundOrder.shipped_date >= last_7d_start,
                        ),
                    ),
                )
            )
        ).one()
        total_pending = int(order_row.pending or 0)
        shipped_today = int(order_row.shipped_today or 0)
        total_shipped_7d = int(order_row.shipped_7d or 0)

        # ─── Inventory Metrics ───
        inventory_row = (
            await self.db.execute(
                select(
                    func.count(func.distinct(Inventory.sku_id)).label("total_skus"),
                    func.sum(Inventory.quantity_on_hand).label("total_units"),
                    func.count(func.distinct(Inventory.location_id)).label("locations_used"),
                ).where(
                    *inventory_filters,
                    Inventory.quantity_on_hand > 0,
                )
            )
        ).one()
        total_skus = int(inventory_row.total_skus or 0)
        total_units = int(inventory_row.total_units or 0)
        locations_used = int(inventory_row.locations_used or 0)

        # ─── Task Metrics ───
        task_row = (
            await self.db.execute(
                select(
                    func.sum(
                        case((Task.status == TaskStatus.PENDING.value, 1), else_=0)
                    ).label("pending"),
                    func.sum(
                        case(
                            (
                                and_(
                                    Task.status == TaskStatus.COMPLETED.value,
                                    Task.completed_at >= today_start,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ).label("completed_today"),
                ).where(
                    *task_filters,
                    or_(
                        Task.status == TaskStatus.PENDING.value,
                        and_(
                            Task.status == TaskStatus.COMPLETED.value,
                            Task.completed_at >= today_start,
                        ),
                    ),
                )
            )
        ).one()
        pending_tasks = int(task_row.pending or 0)
        completed_today = int(task_row.completed_today or 0)

        # ─── Inbound Metrics ───
        inbound_row = (
            await self.db.execute(
                select(
                    func.sum(
                        case(
                            (InboundOrder.status.in_(pending_inbound_statuses), 1),
                            else_=0,
                        )
                    ).label("pending"),
                    func.sum(
                        case((InboundOrder.received_date >= today_start, 1), else_=0)
                    ).label("received_today"),
                ).where(
                    *inbound_filters,
                    or_(
                        InboundOrder.status.in_(pending_inbound_statuses),
                        InboundOrder.received_date >= today_start,
                    ),
                )
            )
        ).one()
        pending_inbound = int(inbound_row.pending or 0)
        received_today = int(inbound_row.received_today or 0)

        # ─── Accuracy (last 7 days) ───
        pick_transaction_query = select(func.count(InventoryTransaction.id)).where(
            InventoryTransaction.tenant_id == self.tenant_id,
            InventoryTransaction.transaction_type == "pick",
            InventoryTransaction.performed_at >= last_7d_start,
        )
        if warehouse_id:
            pick_transaction_query = pick_transaction_query.join(
                Location,
                Location.id == InventoryTransaction.location_id,
            ).where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse_id,
            )
        total_picks_7d = (
            await self.db.execute(pick_transaction_query)
        ).scalar() or 0

        # ─── Client count ───
        active_clients = (
            await self.db.execute(
                select(func.count(Client.id)).where(
                    Client.tenant_id == self.tenant_id,
                    Client.is_active == True,  # noqa
                )
            )
        ).scalar() or 0

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "orders": {
                "pending": total_pending,
                "shipped_today": shipped_today,
                "shipped_7d": total_shipped_7d,
                "avg_daily": round(total_shipped_7d / 7, 1),
            },
            "inventory": {
                "total_skus": total_skus,
                "total_units": total_units,
                "locations_used": locations_used,
            },
            "tasks": {
                "pending": pending_tasks,
                "completed_today": completed_today,
            },
            "inbound": {
                "pending": pending_inbound,
                "received_today": received_today,
            },
            "operations": {
                "picks_7d": total_picks_7d,
                "active_clients": active_clients,
            },
        }

    async def get_order_report(
        self,
        start_date: date,
        end_date: date,
        client_id: str | None = None,
    ) -> list[dict]:
        """Order fulfillment report — by date range and optional client."""
        query = select(OutboundOrder).where(
            OutboundOrder.tenant_id == self.tenant_id,
            OutboundOrder.created_at
            >= datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
            OutboundOrder.created_at <= datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
        )
        if client_id:
            query = query.where(OutboundOrder.client_id == client_id)

        result = await self.db.execute(query.order_by(OutboundOrder.created_at.desc()))
        return [
            {
                "order_number": o.order_number,
                "client_id": o.client_id,
                "status": o.status,
                "carrier": o.carrier,
                "tracking": o.tracking_number,
                "shipping_cost": float(o.shipping_cost) if o.shipping_cost else 0,
                "created": o.created_at.isoformat() if o.created_at else "",
                "shipped": o.shipped_date.isoformat() if o.shipped_date else "",
            }
            for o in result.scalars()
        ]

    async def get_inventory_summary(self, client_id: str | None = None) -> list[dict]:
        """Inventory summary grouped by SKU — total on hand, allocated, available."""
        from app.models.inventory import SKU

        query = (
            select(
                SKU.sku_code,
                SKU.name,
                Inventory.client_id,
                func.sum(Inventory.quantity_on_hand).label("on_hand"),
                func.sum(Inventory.quantity_allocated).label("allocated"),
                func.sum(Inventory.quantity_damaged).label("damaged"),
                func.count(Inventory.id).label("locations"),
            )
            .join(SKU, SKU.id == Inventory.sku_id)
            .where(
                Inventory.tenant_id == self.tenant_id,
                SKU.tenant_id == self.tenant_id,
                Inventory.quantity_on_hand > 0,
            )
            .group_by(SKU.sku_code, SKU.name, Inventory.client_id)
            .order_by(SKU.sku_code)
        )
        if client_id:
            query = query.where(Inventory.client_id == client_id)

        result = await self.db.execute(query)
        return [
            {
                "sku_code": row.sku_code,
                "name": row.name,
                "client_id": row.client_id,
                "on_hand": row.on_hand,
                "allocated": row.allocated,
                "damaged": row.damaged,
                "available": row.on_hand - row.allocated - row.damaged,
                "locations": row.locations,
            }
            for row in result.all()
        ]

    async def get_activity_log(
        self,
        days: int = 7,
        transaction_type: str | None = None,
    ) -> list[dict]:
        """Recent inventory transaction log."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        query = select(InventoryTransaction).where(
            InventoryTransaction.tenant_id == self.tenant_id,
            InventoryTransaction.performed_at >= cutoff,
        )
        if transaction_type:
            query = query.where(InventoryTransaction.transaction_type == transaction_type)

        result = await self.db.execute(
            query.order_by(InventoryTransaction.performed_at.desc()).limit(200)
        )
        return [
            {
                "type": t.transaction_type,
                "sku_id": t.sku_id,
                "location": t.location_id,
                "qty_change": t.quantity_change,
                "performed_by": t.performed_by,
                "performed_at": t.performed_at.isoformat() if t.performed_at else "",
                "reference": f"{t.reference_type}:{t.reference_id}" if t.reference_type else "",
                "notes": t.notes,
            }
            for t in result.scalars()
        ]

    def generate_report_csv(self, data: list[dict]) -> str:
        """Convert any report data to CSV string."""
        if not data:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()
