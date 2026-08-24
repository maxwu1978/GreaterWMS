"""Regression tests: order lists and details (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.order_details import get_inbound_detail
from app.api.v1.endpoints.orders import list_inbound_orders, list_outbound_orders
from app.api.v1.endpoints.receiving import list_inbound_packages
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.inventory import SKU, Inventory
from app.models.order import (
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    InboundPackageStatus,
    InboundStatus,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
    ReceivingLabel,
)
from app.models.task import TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.outbound_readiness import refresh_outbound_readiness_projection
from app.services.receiving_service import ReceivingService


@pytest.mark.asyncio
async def test_delete_inbound_order_only_allows_clean_unstarted_orders(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        SKU(
            id="sku-del-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-DEL-1",
            name="Delete Test",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    clean_order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-DEL-CLEAN",
        lines=[{"sku_id": "sku-del-1", "quantity": 2}],
    )

    await service.delete_inbound_order(clean_order.id)
    assert await db.scalar(select(InboundOrder.id).where(InboundOrder.id == clean_order.id)) is None

    active_order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-DEL-SCANNED",
        lines=[{"sku_id": "sku-del-1", "quantity": 2, "external_tracking_number": "TRK-DEL-1"}],
    )
    await service.start_receiving(active_order.id)
    await service.scan_label(active_order.id, "TRK-DEL-1")

    with pytest.raises(HTTPException) as exc:
        await service.delete_inbound_order(active_order.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_void_inbound_order_preserves_unconfirmed_history_but_blocks_confirmed_receipts(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-void-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-void-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-VOID-1",
            name="Void Test",
        )
    )
    db.add(
        Location(
            id="staging-void-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-void-1",
            barcode="STAGE-VOID-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    voidable = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-VOID-OPEN",
        lines=[
            {"sku_id": "sku-void-1", "quantity": 2, "external_tracking_number": "TRK-VOID-OPEN"}
        ],
    )
    await service.start_receiving(voidable.id)
    await service.scan_label(voidable.id, "TRK-VOID-OPEN")
    voided = await service.void_inbound_order(voidable.id, user_id)
    assert voided.status == InboundStatus.CANCELLED.value
    assert (voided.extra_data or {}).get("voided") is True

    confirmed = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-VOID-BLOCK",
        lines=[
            {"sku_id": "sku-void-1", "quantity": 2, "external_tracking_number": "TRK-VOID-BLOCK"}
        ],
    )
    await service.start_receiving(confirmed.id)
    await service.receive_label(
        order_id=confirmed.id,
        label_code="TRK-VOID-BLOCK",
        quantity_received=2,
        quantity_damaged=0,
        staging_location_id="staging-void-1",
        user_id=user_id,
    )
    with pytest.raises(HTTPException) as exc:
        await service.void_inbound_order(confirmed.id, user_id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_archived_inbound_orders_are_hidden_from_default_list(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        SKU(
            id="sku-archive-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-ARC-1",
            name="Archive Test",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-ARCHIVE-1",
        lines=[{"sku_id": "sku-archive-1", "quantity": 1}],
    )
    await service.set_inbound_order_archived(order.id, True, user_id)

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    default_list = await list_inbound_orders(
        response=Response(),
        warehouse_id=None,
        status=None,
        include_archived=False,
        current_user=current_user,
        db=db,
    )
    archived_list = await list_inbound_orders(
        response=Response(),
        warehouse_id=None,
        status=None,
        include_archived=True,
        current_user=current_user,
        db=db,
    )

    assert all(item.id != order.id for item in default_list)
    archived_item = next(item for item in archived_list if item.id == order.id)
    assert archived_item.archived is True
    assert archived_item.can_archive is True


@pytest.mark.asyncio
async def test_inbound_order_list_exposes_package_operational_summary(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-summary-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-summary-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-SUM-1",
            name="Summary Test",
        )
    )
    db.add(
        Location(
            id="staging-summary-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-summary-1",
            barcode="STAGE-SUM-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-SUMMARY-1",
        lines=[{"line_number": 4, "sku_id": "sku-summary-1", "quantity": 5}],
    )
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    assert line is not None

    prebooked_package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=3,
        package_type="carton",
        external_tracking_number="SUM-TRACK-UP-002",
    )
    assert prebooked_package is not None

    await service.start_receiving(order.id)

    await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=2,
        package_type="crate",
        external_carton_mark="SUM-CARTON-003",
    )

    await service.receive_package(
        order_id=order.id,
        package_id=prebooked_package.id,
        quantity_received=3,
        quantity_damaged=0,
        staging_location_id="staging-summary-1",
        user_id=user_id,
    )

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    listing = await list_inbound_orders(
        response=Response(),
        warehouse_id=None,
        status=None,
        include_archived=False,
        current_user=current_user,
        db=db,
    )
    listed = next(item for item in listing if item.id == order.id)

    assert listed.total_packages == 2
    assert listed.packages_open == 2
    assert listed.packages_putaway_pending == 0
    assert listed.packages_stored == 0
    assert listed.packages_needing_action == 2
    assert listed.packages_prebooked == 1
    assert listed.packages_dock_created == 1
    assert listed.supervisor_review_needed is True
    assert listed.internal_labels_total == 1
    assert listed.internal_labels_print_pending == 1


@pytest.mark.asyncio
async def test_inbound_order_list_batches_operational_summary_queries(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id, name="Batch Summary Tenant", code="BST", contact_email="ops@example.com"
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        SKU(
            id="sku-batch-summary-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-BATCH-1",
            name="Batch Summary Test",
        )
    )
    for index in range(12):
        order_id = f"order-batch-summary-{index}"
        line_id = f"line-batch-summary-{index}"
        db.add(
            InboundOrder(
                id=order_id,
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number=f"ASN-BATCH-SUMMARY-{index:03d}",
                reference_number=f"REF-BATCH-{index:03d}",
                status=InboundStatus.RECEIVING.value,
            )
        )
        db.add(
            InboundOrderLine(
                id=line_id,
                tenant_id=tenant_id,
                order_id=order_id,
                sku_id="sku-batch-summary-1",
                line_number=1,
                quantity_expected=2,
            )
        )
        db.add(
            InboundPackage(
                id=f"pkg-batch-summary-{index}",
                tenant_id=tenant_id,
                order_id=order_id,
                order_line_id=line_id,
                package_number=1,
                package_type="carton",
                status="expected",
                expected_qty=2,
            )
        )
        db.add(
            ReceivingLabel(
                id=f"label-batch-summary-{index}",
                tenant_id=tenant_id,
                order_id=order_id,
                order_line_id=line_id,
                sku_id="sku-batch-summary-1",
                label_code=f"RCV-BATCH-{index:03d}",
                expected_qty=2,
                status="received",
            )
        )
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    sync_bind = db.sync_session.get_bind()
    event.listen(sync_bind, "before_cursor_execute", count_selects)
    try:
        listing = await list_inbound_orders(
            response=Response(),
            warehouse_id=None,
            status=None,
            include_archived=False,
            current_user=current_user,
            db=db,
        )
    finally:
        event.remove(sync_bind, "before_cursor_execute", count_selects)

    listed_orders = [item for item in listing if item.order_number.startswith("ASN-BATCH-SUMMARY")]
    assert len(listed_orders) == 12
    assert all(item.packages_open == 1 for item in listed_orders)
    assert all(item.internal_labels_print_pending == 1 for item in listed_orders)
    assert len(statements) <= 10


@pytest.mark.asyncio
async def test_order_lists_expose_limit_plus_one_pagination_headers(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Order Pagination Tenant",
            code="OPT",
            contact_email="ops@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Page Client", code="PAGE"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Page Warehouse", code="PGW"))
    for index in range(3):
        db.add(
            InboundOrder(
                id=f"inbound-page-{index}",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number=f"INB-PAGE-{index}",
                status=InboundStatus.EXPECTED.value,
            )
        )
        db.add(
            OutboundOrder(
                id=f"outbound-page-{index}",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number=f"OUT-PAGE-{index}",
                status=OutboundStatus.PENDING.value,
            )
        )
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    inbound_response = Response()
    inbound_page = await list_inbound_orders(
        response=inbound_response,
        warehouse_id=None,
        status=None,
        include_archived=False,
        offset=0,
        limit=2,
        current_user=current_user,
        db=db,
    )
    outbound_response = Response()
    outbound_page = await list_outbound_orders(
        response=outbound_response,
        warehouse_id=None,
        status=None,
        offset=0,
        limit=2,
        current_user=current_user,
        db=db,
    )

    assert len(inbound_page) == 2
    assert inbound_response.headers["X-Offset"] == "0"
    assert inbound_response.headers["X-Limit"] == "2"
    assert inbound_response.headers["X-Returned-Count"] == "2"
    assert inbound_response.headers["X-Has-More"] == "true"
    assert len(outbound_page) == 2
    assert outbound_response.headers["X-Offset"] == "0"
    assert outbound_response.headers["X-Limit"] == "2"
    assert outbound_response.headers["X-Returned-Count"] == "2"
    assert outbound_response.headers["X-Has-More"] == "true"


@pytest.mark.asyncio
async def test_inbound_order_list_filters_lifecycle_operation_and_sorts_server_side(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Inbound Filter Tenant",
            code="IFT",
            contact_email="ops@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Inbound Client", code="INB"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Inbound Warehouse", code="IWH"))
    db.add(
        SKU(
            id="sku-inbound-filter",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="INB-FILTER",
            name="Inbound Filter SKU",
        )
    )
    rows = [
        ("inbound-filter-expected", "INB-FILTER-003", InboundStatus.EXPECTED.value, {}),
        ("inbound-filter-receiving", "INB-FILTER-002", InboundStatus.RECEIVING.value, {}),
        ("inbound-filter-completed", "INB-FILTER-004", InboundStatus.COMPLETED.value, {}),
        ("inbound-filter-archived", "INB-FILTER-001", InboundStatus.EXPECTED.value, {"archived": True}),
        ("inbound-filter-putaway", "INB-FILTER-005", InboundStatus.PUTAWAY.value, {}),
    ]
    for order_id, order_number, order_status, extra_data in rows:
        db.add(
            InboundOrder(
                id=order_id,
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number=order_number,
                status=order_status,
                extra_data=extra_data,
            )
        )
        db.add(
            InboundOrderLine(
                id=f"{order_id}-line",
                tenant_id=tenant_id,
                order_id=order_id,
                sku_id="sku-inbound-filter",
                line_number=1,
                quantity_expected=2,
            )
        )
    db.add(
        InboundPackage(
            id="inbound-filter-receiving-package",
            tenant_id=tenant_id,
            order_id="inbound-filter-receiving",
            order_line_id="inbound-filter-receiving-line",
            package_number=1,
            package_type="carton",
            status=InboundPackageStatus.EXPECTED.value,
            expected_qty=2,
        )
    )
    db.add(
        InboundPackage(
            id="inbound-filter-putaway-package",
            tenant_id=tenant_id,
            order_id="inbound-filter-putaway",
            order_line_id="inbound-filter-putaway-line",
            package_number=1,
            package_type="carton",
            status=InboundPackageStatus.PUTAWAY_PENDING.value,
            expected_qty=2,
        )
    )
    db.add(
        ReceivingLabel(
            id="inbound-filter-print-label",
            tenant_id=tenant_id,
            order_id="inbound-filter-receiving",
            order_line_id="inbound-filter-receiving-line",
            sku_id="sku-inbound-filter",
            label_code="RCV-INB-FILTER-001",
            expected_qty=2,
            status="received",
            extra_data={"print_count": 0},
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    active_response = Response()
    active_rows = await list_inbound_orders(
        response=active_response,
        warehouse_id=None,
        status=None,
        statuses=None,
        lifecycle="active",
        operation=None,
        include_archived=False,
        sort_by="order_number",
        sort_direction="asc",
        recent_hours=12,
        offset=0,
        limit=10,
        current_user=current_user,
        db=db,
    )
    assert [row.order_number for row in active_rows] == ["INB-FILTER-002", "INB-FILTER-003"]

    print_response = Response()
    print_rows = await list_inbound_orders(
        response=print_response,
        warehouse_id=None,
        status=None,
        statuses=None,
        lifecycle=None,
        operation="print_pending",
        include_archived=False,
        sort_by="order_number",
        sort_direction="asc",
        recent_hours=12,
        offset=0,
        limit=10,
        current_user=current_user,
        db=db,
    )
    assert [row.order_number for row in print_rows] == ["INB-FILTER-002"]
    assert print_rows[0].internal_labels_print_pending == 1

    putaway_response = Response()
    putaway_rows = await list_inbound_orders(
        response=putaway_response,
        warehouse_id=None,
        status=None,
        statuses=None,
        lifecycle=None,
        operation="putaway_pending",
        include_archived=False,
        sort_by="order_number",
        sort_direction="asc",
        recent_hours=12,
        offset=0,
        limit=10,
        current_user=current_user,
        db=db,
    )
    assert [row.order_number for row in putaway_rows] == ["INB-FILTER-005"]
    assert putaway_rows[0].packages_putaway_pending == 1
    assert active_response.headers["X-Returned-Count"] == "2"


@pytest.mark.asyncio
async def test_outbound_order_list_filters_statuses_and_sorts_server_side(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Outbound Filter Tenant",
            code="OFT",
            contact_email="ops@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Outbound Client", code="OUT"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Outbound Warehouse", code="OWH"))
    for order_id, order_number, order_status in [
        ("out-sort-pending", "OUT-SORT-003", OutboundStatus.PENDING.value),
        ("out-sort-picked", "OUT-SORT-002", OutboundStatus.PICKED.value),
        ("out-sort-packed", "OUT-SORT-001", OutboundStatus.PACKED.value),
        ("out-sort-shipped", "OUT-SORT-004", OutboundStatus.SHIPPED.value),
    ]:
        db.add(
            OutboundOrder(
                id=order_id,
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number=order_number,
                status=order_status,
            )
        )
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    response = Response()
    rows = await list_outbound_orders(
        response=response,
        warehouse_id=None,
        status=None,
        statuses="picked,packed",
        sort_by="order_number",
        sort_direction="asc",
        offset=0,
        limit=10,
        current_user=current_user,
        db=db,
    )

    assert [row.order_number for row in rows] == ["OUT-SORT-001", "OUT-SORT-002"]
    assert {row.status for row in rows} == {OutboundStatus.PICKED.value, OutboundStatus.PACKED.value}
    assert response.headers["X-Has-More"] == "false"
    assert response.headers["X-Returned-Count"] == "2"


@pytest.mark.asyncio
async def test_outbound_order_list_sorts_pick_and_shipping_readiness_server_side(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Outbound Readiness Tenant",
            code="ORT",
            contact_email="ops@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Readiness Client", code="RDY"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Readiness Warehouse", code="RWH"))
    db.add(
        Zone(
            id="zone-outbound-readiness",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Storage",
            code="STOR",
        )
    )
    db.add(
        Location(
            id="loc-outbound-readiness",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-outbound-readiness",
            barcode="RDY-STOR-01",
            aisle="A",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        SKU(
            id="sku-outbound-readiness",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="RDY-SKU",
            name="Readiness SKU",
        )
    )
    db.add(
        Inventory(
            id="inv-outbound-readiness",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-outbound-readiness",
            sku_id="sku-outbound-readiness",
            quantity_on_hand=10,
            quantity_allocated=0,
            quantity_damaged=0,
        )
    )
    for order_id, order_number, order_status, qty, carrier, tracking in [
        ("out-pick-short", "OUT-READY-003", OutboundStatus.PENDING.value, 50, None, None),
        ("out-pick-ready", "OUT-READY-002", OutboundStatus.PENDING.value, 2, None, None),
        ("out-pick-allocated", "OUT-READY-001", OutboundStatus.ALLOCATED.value, 2, None, None),
        ("out-ship-picked", "OUT-SHIP-003", OutboundStatus.PICKED.value, 2, None, None),
        ("out-ship-packed", "OUT-SHIP-002", OutboundStatus.PACKED.value, 2, None, None),
        ("out-ship-ready", "OUT-SHIP-001", OutboundStatus.PACKED.value, 2, "UPS", "1ZRDY"),
    ]:
        db.add(
            OutboundOrder(
                id=order_id,
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number=order_number,
                status=order_status,
                carrier=carrier,
                tracking_number=tracking,
            )
        )
        db.add(
            OutboundOrderLine(
                id=f"{order_id}-line",
                tenant_id=tenant_id,
                order_id=order_id,
                sku_id="sku-outbound-readiness",
                quantity_ordered=qty,
                quantity_allocated=0,
                quantity_picked=0,
            )
        )
    await db.flush()
    readiness_orders = await db.execute(
        select(OutboundOrder).where(
            OutboundOrder.tenant_id == tenant_id,
            OutboundOrder.id.in_(
                [
                    "out-pick-short",
                    "out-pick-ready",
                    "out-pick-allocated",
                    "out-ship-picked",
                    "out-ship-packed",
                    "out-ship-ready",
                ]
            ),
        )
    )
    for order in readiness_orders.scalars().all():
        await refresh_outbound_readiness_projection(db, tenant_id, order)
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    pick_response = Response()
    pick_rows = await list_outbound_orders(
        response=pick_response,
        warehouse_id=None,
        status=None,
        statuses="pending,allocated",
        sort_by="pick_readiness",
        sort_direction="asc",
        offset=0,
        limit=10,
        current_user=current_user,
        db=db,
    )

    assert [row.order_number for row in pick_rows] == [
        "OUT-READY-003",
        "OUT-READY-002",
        "OUT-READY-001",
    ]
    assert [row.pick_readiness for row in pick_rows] == [
        "short_stock",
        "ready_to_allocate",
        "ready_to_release",
    ]

    shipping_response = Response()
    shipping_rows = await list_outbound_orders(
        response=shipping_response,
        warehouse_id=None,
        status=None,
        statuses="picked,packed",
        sort_by="shipping_readiness",
        sort_direction="asc",
        offset=0,
        limit=10,
        current_user=current_user,
        db=db,
    )

    assert [row.order_number for row in shipping_rows] == [
        "OUT-SHIP-001",
        "OUT-SHIP-002",
        "OUT-SHIP-003",
    ]


@pytest.mark.asyncio
async def test_inbound_detail_exposes_lifecycle_and_receiving_artifacts(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-detail-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-detail-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-DETAIL-1",
            name="Detail Test",
        )
    )
    db.add(
        Location(
            id="staging-detail-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-detail-1",
            barcode="STAGE-DETAIL-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    archived = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-DETAIL-ARCHIVED",
        lines=[{"sku_id": "sku-detail-1", "quantity": 1}],
    )
    await service.set_inbound_order_archived(archived.id, True, user_id)

    active = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-DETAIL-ACTIVE",
        lines=[
            {"sku_id": "sku-detail-1", "quantity": 3, "external_tracking_number": "TRK-DETAIL-1"}
        ],
    )
    await service.start_receiving(active.id)
    scan = await service.scan_label(active.id, "TRK-DETAIL-1")
    await service.add_observed_code(
        order_id=active.id,
        label_code=scan["label_code"],
        code_value="BOX-DETAIL-1",
        code_type="carton_mark",
        source="manual",
        is_primary=False,
    )
    await service.receive_label(
        order_id=active.id,
        label_code="TRK-DETAIL-1",
        quantity_received=3,
        quantity_damaged=0,
        staging_location_id="staging-detail-1",
        user_id=user_id,
    )
    await service.mark_labels_printed(active.id)
    await service.complete_receiving(active.id, user_id)
    voidable = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-DETAIL-VOIDED",
        lines=[
            {"sku_id": "sku-detail-1", "quantity": 1, "external_tracking_number": "TRK-DETAIL-VOID"}
        ],
    )
    await service.start_receiving(voidable.id)
    await service.scan_label(voidable.id, "TRK-DETAIL-VOID")
    await service.void_inbound_order(voidable.id, user_id)

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    archived_detail = await get_inbound_detail(archived.id, current_user=current_user, db=db)
    active_detail = await get_inbound_detail(active.id, current_user=current_user, db=db)
    voided_detail = await get_inbound_detail(voidable.id, current_user=current_user, db=db)

    assert archived_detail["archived"] is True
    assert archived_detail["voided"] is False
    assert active_detail["total_observed_codes"] == 2
    assert active_detail["total_internal_labels"] == 1
    assert active_detail["printed_internal_labels"] == 1
    assert active_detail["package_summary"]["total_packages"] == 1
    assert active_detail["package_summary"]["packages_open"] == 0
    assert active_detail["package_summary"]["packages_putaway_pending"] == 1
    assert active_detail["package_summary"]["packages_stored"] == 0
    assert active_detail["package_summary"]["packages_needing_action"] == 1
    assert active_detail["package_summary"]["supervisor_review_needed"] is False
    assert active_detail["package_summary"]["internal_labels_print_pending"] == 0
    assert active_detail["lines"][0]["observed_codes"][0]["code_value"] == "TRK-DETAIL-1"
    assert active_detail["lines"][0]["receiving_labels"][0]["print_count"] == 1
    assert active_detail["downstream_summary"]["putaway_tasks_total"] == 1
    assert active_detail["downstream_summary"]["handling_units_putaway_pending"] == 1
    assert active_detail["lines"][0]["downstream_tasks"][0]["task_type"] == TaskType.PUTAWAY.value
    assert active_detail["lines"][0]["handling_units"][0]["status"] == "putaway_pending"
    timeline_event_types = [event["event_type"] for event in active_detail["timeline"]]
    assert "receiving_started" in timeline_event_types
    assert "external_code_captured" in timeline_event_types
    assert "internal_label_issued" in timeline_event_types
    assert "receiving_completed" in timeline_event_types
    assert "putaway_task_created" in timeline_event_types
    assert timeline_event_types.index("external_code_captured") < timeline_event_types.index(
        "receiving_completed"
    )
    assert voided_detail["voided"] is True
    assert voided_detail["total_observed_codes"] == 1
    assert voided_detail["total_internal_labels"] == 0


@pytest.mark.asyncio
async def test_package_origin_distinguishes_prebooked_and_dock_created(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id, name="Package Origin Tenant", code="PKG", contact_email="ops@example.com"
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-origin-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-origin-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-PKG-1",
            name="Package Origin Test",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-PKG-ORIGIN",
        lines=[
            {
                "line_number": 7,
                "sku_id": "sku-origin-1",
                "quantity": 3,
                "packages": [
                    {
                        "package_number": 2,
                        "expected_qty": 3,
                        "package_type": "carton",
                        "external_tracking_number": "TRK-ORIGIN-UP",
                    }
                ],
            }
        ],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(
        select(InboundOrderLine).where(
            InboundOrderLine.tenant_id == tenant_id,
            InboundOrderLine.order_id == order.id,
        )
    )
    assert line is not None

    dock_package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=5,
        package_type="crate",
        external_tracking_number="TRK-ORIGIN-DOCK",
    )

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    packages = await list_inbound_packages(order.id, current_user=current_user, db=db)
    detail = await get_inbound_detail(order.id, current_user=current_user, db=db)

    packages_by_number = {pkg["package_number"]: pkg for pkg in packages}
    detail_packages_by_number = {
        pkg["package_number"]: pkg for pkg in detail["lines"][0]["packages"]
    }

    assert packages_by_number[2]["package_origin"] == "prebooked"
    assert packages_by_number[dock_package.package_number]["package_origin"] == "dock_created"
    assert detail_packages_by_number[2]["package_origin"] == "prebooked"
    assert (
        detail_packages_by_number[dock_package.package_number]["package_origin"] == "dock_created"
    )
    assert detail["package_summary"]["supervisor_review_needed"] is True
