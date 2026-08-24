"""Regression tests: tenant scoping and tenant settings (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.return_analytics import return_analytics
from app.api.v1.endpoints.shipping import _packing_slip_included_quantity, download_packing_slip
from app.api.v1.endpoints.tenants import (
    TenantSettingsUpdate,
    get_current_tenant,
    update_current_tenant_settings,
)
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction, TransactionType
from app.models.order import (
    InboundOrder,
    InboundStatus,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
)
from app.models.returns import ReturnOrder, ReturnOrderLine
from app.models.task import Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, Warehouse, Zone
from app.services.reporting_service import ReportingService


@pytest.mark.asyncio
async def test_reporting_service_scopes_dashboard_and_reports_to_current_tenant(
    db: AsyncSession,
):
    """Shared reporting queries must not count another tenant's operational data."""
    now = datetime.now(UTC)
    start_date = (now - timedelta(days=1)).date()
    end_date = (now + timedelta(days=1)).date()

    db.add(Tenant(id="tenant-report-a", name="Report A", code="RPA", contact_email="a@example.com"))
    db.add(Tenant(id="tenant-report-b", name="Report B", code="RPB", contact_email="b@example.com"))
    db.add(Client(id="client-report-a", tenant_id="tenant-report-a", name="Client A", code="CLA"))
    db.add(Client(id="client-report-b", tenant_id="tenant-report-b", name="Client B", code="CLB"))
    db.add(Warehouse(id="wh-report-a1", tenant_id="tenant-report-a", name="WH A1", code="WHA1"))
    db.add(Warehouse(id="wh-report-a2", tenant_id="tenant-report-a", name="WH A2", code="WHA2"))
    db.add(Warehouse(id="wh-report-b", tenant_id="tenant-report-b", name="WH B", code="WHB"))
    db.add(Zone(id="zone-report-a1", tenant_id="tenant-report-a", warehouse_id="wh-report-a1", name="A1", code="A1"))
    db.add(Zone(id="zone-report-a2", tenant_id="tenant-report-a", warehouse_id="wh-report-a2", name="A2", code="A2"))
    db.add(Zone(id="zone-report-b", tenant_id="tenant-report-b", warehouse_id="wh-report-b", name="B", code="B"))
    db.add(
        Location(
            id="loc-report-a1",
            tenant_id="tenant-report-a",
            warehouse_id="wh-report-a1",
            zone_id="zone-report-a1",
            barcode="A1-01",
            aisle="A1",
            rack="01",
            level="01",
            position="01",
        )
    )
    db.add(
        Location(
            id="loc-report-a2",
            tenant_id="tenant-report-a",
            warehouse_id="wh-report-a2",
            zone_id="zone-report-a2",
            barcode="A2-01",
            aisle="A2",
            rack="01",
            level="01",
            position="01",
        )
    )
    db.add(
        Location(
            id="loc-report-b",
            tenant_id="tenant-report-b",
            warehouse_id="wh-report-b",
            zone_id="zone-report-b",
            barcode="B-01",
            aisle="B",
            rack="01",
            level="01",
            position="01",
        )
    )
    db.add(
        SKU(
            id="sku-report-a",
            tenant_id="tenant-report-a",
            client_id="client-report-a",
            sku_code="REPORT-A",
            name="Report A SKU",
        )
    )
    db.add(
        SKU(
            id="sku-report-b",
            tenant_id="tenant-report-b",
            client_id="client-report-b",
            sku_code="REPORT-B",
            name="Report B SKU",
        )
    )
    db.add_all(
        [
            Inventory(
                id="inv-report-a1",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                warehouse_id="wh-report-a1",
                location_id="loc-report-a1",
                sku_id="sku-report-a",
                quantity_on_hand=10,
                quantity_allocated=2,
                quantity_damaged=1,
            ),
            Inventory(
                id="inv-report-a2",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                warehouse_id="wh-report-a2",
                location_id="loc-report-a2",
                sku_id="sku-report-a",
                quantity_on_hand=20,
            ),
            Inventory(
                id="inv-report-b",
                tenant_id="tenant-report-b",
                client_id="client-report-b",
                warehouse_id="wh-report-b",
                location_id="loc-report-b",
                sku_id="sku-report-b",
                quantity_on_hand=99,
            ),
            OutboundOrder(
                id="out-report-a1",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                warehouse_id="wh-report-a1",
                order_number="OUT-REPORT-A1",
                status=OutboundStatus.PENDING.value,
            ),
            OutboundOrder(
                id="out-report-a2",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                warehouse_id="wh-report-a1",
                order_number="OUT-REPORT-A2",
                status=OutboundStatus.SHIPPED.value,
                shipped_date=now,
            ),
            OutboundOrder(
                id="out-report-a3",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                warehouse_id="wh-report-a2",
                order_number="OUT-REPORT-A3",
                status=OutboundStatus.PENDING.value,
            ),
            OutboundOrder(
                id="out-report-b",
                tenant_id="tenant-report-b",
                client_id="client-report-b",
                warehouse_id="wh-report-b",
                order_number="OUT-REPORT-B",
                status=OutboundStatus.PENDING.value,
            ),
            InboundOrder(
                id="in-report-a1",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                warehouse_id="wh-report-a1",
                order_number="IN-REPORT-A1",
                status=InboundStatus.RECEIVING.value,
                received_date=now,
            ),
            InboundOrder(
                id="in-report-a2",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                warehouse_id="wh-report-a2",
                order_number="IN-REPORT-A2",
                status=InboundStatus.RECEIVING.value,
            ),
            InboundOrder(
                id="in-report-b",
                tenant_id="tenant-report-b",
                client_id="client-report-b",
                warehouse_id="wh-report-b",
                order_number="IN-REPORT-B",
                status=InboundStatus.RECEIVING.value,
            ),
            Task(
                id="task-report-a1",
                tenant_id="tenant-report-a",
                warehouse_id="wh-report-a1",
                task_type=TaskType.PICK.value,
                status=TaskStatus.PENDING.value,
                quantity=1,
            ),
            Task(
                id="task-report-a2",
                tenant_id="tenant-report-a",
                warehouse_id="wh-report-a1",
                task_type=TaskType.PICK.value,
                status=TaskStatus.COMPLETED.value,
                completed_at=now,
                quantity=1,
            ),
            Task(
                id="task-report-b",
                tenant_id="tenant-report-b",
                warehouse_id="wh-report-b",
                task_type=TaskType.PICK.value,
                status=TaskStatus.PENDING.value,
                quantity=1,
            ),
            InventoryTransaction(
                id="tx-report-a1",
                tenant_id="tenant-report-a",
                client_id="client-report-a",
                transaction_type=TransactionType.PICK.value,
                sku_id="sku-report-a",
                location_id="loc-report-a1",
                quantity_change=-1,
                performed_at=now,
            ),
            InventoryTransaction(
                id="tx-report-b",
                tenant_id="tenant-report-b",
                client_id="client-report-b",
                transaction_type=TransactionType.PICK.value,
                sku_id="sku-report-b",
                location_id="loc-report-b",
                quantity_change=-9,
                performed_at=now,
            ),
        ]
    )
    await db.flush()

    service = ReportingService(db, "tenant-report-a")
    dashboard_selects: list[str] = []

    def capture_dashboard_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            dashboard_selects.append(statement)

    sync_bind = db.sync_session.get_bind()
    event.listen(sync_bind, "before_cursor_execute", capture_dashboard_selects)
    try:
        dashboard = await service.get_dashboard_kpis("wh-report-a1")
    finally:
        event.remove(sync_bind, "before_cursor_execute", capture_dashboard_selects)

    assert len(dashboard_selects) <= 6
    assert dashboard["orders"]["pending"] == 1
    assert dashboard["orders"]["shipped_today"] == 1
    assert dashboard["inventory"]["total_skus"] == 1
    assert dashboard["inventory"]["total_units"] == 10
    assert dashboard["inventory"]["locations_used"] == 1
    assert dashboard["tasks"]["pending"] == 1
    assert dashboard["tasks"]["completed_today"] == 1
    assert dashboard["inbound"]["pending"] == 1
    assert dashboard["inbound"]["received_today"] == 1
    assert dashboard["operations"]["picks_7d"] == 1
    assert dashboard["operations"]["active_clients"] == 1

    order_numbers = {
        row["order_number"]
        for row in await service.get_order_report(start_date=start_date, end_date=end_date)
    }
    assert order_numbers == {"OUT-REPORT-A1", "OUT-REPORT-A2", "OUT-REPORT-A3"}

    inventory_summary = await service.get_inventory_summary()
    assert len(inventory_summary) == 1
    assert inventory_summary[0]["sku_code"] == "REPORT-A"
    assert inventory_summary[0]["on_hand"] == 30
    assert inventory_summary[0]["available"] == 27

    activity = await service.get_activity_log(days=7)
    assert [row["sku_id"] for row in activity] == ["sku-report-a"]


@pytest.mark.asyncio
async def test_return_analytics_scopes_results_to_current_tenant(db: AsyncSession):
    """Return analytics should aggregate only the tenant making the request."""
    db.add(Tenant(id="tenant-rma-a", name="RMA A", code="RMAA", contact_email="a@example.com"))
    db.add(Tenant(id="tenant-rma-b", name="RMA B", code="RMAB", contact_email="b@example.com"))
    db.add(Client(id="client-rma-a", tenant_id="tenant-rma-a", name="RMA Client A", code="RMAA"))
    db.add(Client(id="client-rma-b", tenant_id="tenant-rma-b", name="RMA Client B", code="RMAB"))
    db.add(Warehouse(id="wh-rma-a", tenant_id="tenant-rma-a", name="RMA WH A", code="RWHA"))
    db.add(Warehouse(id="wh-rma-b", tenant_id="tenant-rma-b", name="RMA WH B", code="RWHB"))
    db.add(
        SKU(
            id="sku-rma-a",
            tenant_id="tenant-rma-a",
            client_id="client-rma-a",
            sku_code="RMA-A",
            name="RMA SKU A",
        )
    )
    db.add(
        SKU(
            id="sku-rma-b",
            tenant_id="tenant-rma-b",
            client_id="client-rma-b",
            sku_code="RMA-B",
            name="RMA SKU B",
        )
    )
    db.add_all(
        [
            ReturnOrder(
                id="return-a1",
                tenant_id="tenant-rma-a",
                client_id="client-rma-a",
                warehouse_id="wh-rma-a",
                rma_number="RMA-A1",
                status="requested",
            ),
            ReturnOrder(
                id="return-a2",
                tenant_id="tenant-rma-a",
                client_id="client-rma-a",
                warehouse_id="wh-rma-a",
                rma_number="RMA-A2",
                status="completed",
            ),
            ReturnOrder(
                id="return-b",
                tenant_id="tenant-rma-b",
                client_id="client-rma-b",
                warehouse_id="wh-rma-b",
                rma_number="RMA-B",
                status="requested",
            ),
            ReturnOrderLine(
                id="return-line-a1",
                tenant_id="tenant-rma-a",
                return_order_id="return-a1",
                sku_id="sku-rma-a",
                quantity_expected=2,
                quantity_restocked=1,
                quantity_damaged=1,
                reason="damaged packaging",
            ),
            ReturnOrderLine(
                id="return-line-a2",
                tenant_id="tenant-rma-a",
                return_order_id="return-a2",
                sku_id="sku-rma-a",
                quantity_expected=3,
                quantity_scrapped=1,
                reason="customer return",
            ),
            ReturnOrderLine(
                id="return-line-b",
                tenant_id="tenant-rma-b",
                return_order_id="return-b",
                sku_id="sku-rma-b",
                quantity_expected=99,
                quantity_restocked=99,
                reason="foreign tenant reason",
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-rma-admin",
        tenant_id="tenant-rma-a",
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    result = await return_analytics(current_user=current_user, db=db)

    assert result["total_rmas"] == 2
    assert result["by_status"] == {"completed": 1, "requested": 1}
    assert {row["reason"] for row in result["by_reason"]} == {
        "customer return",
        "damaged packaging",
    }
    assert result["top_returned_skus"] == [
        {"sku_code": "RMA-A", "name": "RMA SKU A", "return_qty": 5}
    ]
    assert result["disposition"] == {"restocked": 1, "damaged": 1, "scrapped": 1}


@pytest.mark.asyncio
async def test_packing_slip_download_returns_pdf_and_respects_tenant_scope(
    db: AsyncSession,
):
    tenant = Tenant(
        id="tenant-pack-slip", name="Pack Slip Tenant", code="PST", contact_email="pst@example.com"
    )
    other_tenant = Tenant(
        id="tenant-pack-slip-other",
        name="Other Pack Tenant",
        code="PTO",
        contact_email="pto@example.com",
    )
    client = Client(id="client-pack-slip", tenant_id=tenant.id, name="Dispatch Client", code="DSP")
    warehouse = Warehouse(id="warehouse-pack-slip", tenant_id=tenant.id, name="Main", code="MAIN")
    sku = SKU(
        id="sku-pack-slip",
        tenant_id=tenant.id,
        client_id=client.id,
        sku_code="DSP&001",
        name="Dispatch <Widget>",
    )
    order = OutboundOrder(
        id="order-pack-slip",
        tenant_id=tenant.id,
        client_id=client.id,
        warehouse_id=warehouse.id,
        order_number="SO/PACK 1",
        status=OutboundStatus.PACKED.value,
        ship_to_name="A&B <Warehouse Customer>",
        ship_to_address={
            "street": "1 Dock & Way",
            "city": "Budapest",
            "state": "BU",
            "zip": "1000",
        },
    )
    line = OutboundOrderLine(
        id="line-pack-slip",
        tenant_id=tenant.id,
        order_id=order.id,
        sku_id=sku.id,
        quantity_ordered=2,
        quantity_picked=2,
        quantity_shipped=0,
    )
    db.add_all([tenant, other_tenant, client, warehouse, sku, order, line])
    await db.flush()

    current_user = TokenPayload(
        sub="shipper",
        tenant_id=tenant.id,
        client_id=None,
        role=UserRole.OPERATOR,
        permissions=["shipping.execute"],
        exp=datetime.now(UTC),
    )

    response = await download_packing_slip(order.id, current_user=current_user, db=db)

    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert _packing_slip_included_quantity(line) == 2
    assert 'filename="packing-slip-SO-PACK-1.pdf"' in response.headers["content-disposition"]

    other_user = TokenPayload(
        sub="other-shipper",
        tenant_id=other_tenant.id,
        client_id=None,
        role=UserRole.OPERATOR,
        permissions=["shipping.execute"],
        exp=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc:
        await download_packing_slip(order.id, current_user=other_user, db=db)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_current_tenant_returns_settings(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Billing Tenant",
            code="BILL",
            contact_email="billing@example.com",
            settings={"business_mode": "self_use"},
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await get_current_tenant(current_user=current_user, db=db)

    assert response.id == tenant_id
    assert response.settings["business_mode"] == "self_use"


@pytest.mark.asyncio
async def test_update_current_tenant_settings_persists_business_mode(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Billing Tenant",
            code="BILL",
            contact_email="billing@example.com",
            settings={"theme": "light"},
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await update_current_tenant_settings(
        TenantSettingsUpdate(business_mode="self_use"),
        current_user=current_user,
        db=db,
    )
    refreshed = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()

    assert response.settings["business_mode"] == "self_use"
    assert refreshed.settings["business_mode"] == "self_use"
    assert refreshed.settings["theme"] == "light"
