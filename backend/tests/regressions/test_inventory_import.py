"""Regression tests: inventory and data import (split from tests/test_regressions.py)."""

from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.data_import import (
    ManualInventoryImportRequest,
    import_inventory_csv,
    import_single_inventory_row,
)
from app.api.v1.endpoints.inventory import list_inventory
from app.api.v1.endpoints.orders import (
    _create_outbound_order,
    import_outbound_orders_csv,
    preview_outbound_orders_csv,
)
from app.api.v1.endpoints.receiving import import_inbound_orders_csv, preview_inbound_orders_csv
from app.core.pagination import PaginationParams
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction, TransactionType
from app.models.order import (
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
)
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.inventory_service import InventoryService
from app.services.outbound_readiness import refresh_outbound_readiness_projection
from tests.regressions.helpers import setup_pick_fixture


@pytest.mark.asyncio
async def test_inventory_service_can_backfill_missing_lot(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    """Lot backfill should update the inventory row and append an audit transaction."""
    fixtures = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    svc = InventoryService(db, tenant_id)

    result = await svc.update_inventory_lot(
        inventory_id=fixtures["inventory_id"],
        lot_number="LOT-2026-APR-01",
        user_id=user_id,
        reason="Backfilled after receiving review",
    )

    inv = (
        await db.execute(select(Inventory).where(Inventory.id == fixtures["inventory_id"]))
    ).scalar_one()

    assert result["success"] is True
    assert inv.lot_number == "LOT-2026-APR-01"

    from app.models.inventory import InventoryTransaction

    txn = (
        await db.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.location_id == inv.location_id,
                InventoryTransaction.sku_id == inv.sku_id,
                InventoryTransaction.performed_by == user_id,
            )
        )
    ).scalar_one()
    assert txn.quantity_change == 0
    assert txn.lot_number == "LOT-2026-APR-01"
    assert "Lot update" in (txn.notes or "")


@pytest.mark.asyncio
async def test_create_outbound_order_creates_pending_order_and_lines(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    """Single-order outbound intake should create a pending order with one line."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)

    order = await _create_outbound_order(
        db=db,
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="SO-IMPORT-001",
        reference_number="SHOP-REF-1",
        carrier="DHL",
        lines=[{"sku_id": "sku-1", "quantity": 7}],
    )

    saved_order = (
        await db.execute(select(OutboundOrder).where(OutboundOrder.id == order.id))
    ).scalar_one()
    saved_lines = (
        (await db.execute(select(OutboundOrderLine).where(OutboundOrderLine.order_id == order.id)))
        .scalars()
        .all()
    )

    assert saved_order.status == OutboundStatus.PENDING.value
    assert saved_order.reference_number == "SHOP-REF-1"
    assert saved_order.carrier == "DHL"
    assert len(saved_lines) == 1
    assert saved_lines[0].quantity_ordered == 7


@pytest.mark.asyncio
async def test_manual_inventory_import_upserts_inventory_row(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    """Single-row inventory intake should create or update inventory without a CSV file."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)

    user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    response = await import_single_inventory_row(
        body=ManualInventoryImportRequest(
            warehouse_id=warehouse_id,
            location_barcode="A-01-01-01-01",
            sku_code="SKU-1",
            quantity=22,
            lot_number="LOT-MANUAL-22",
        ),
        current_user=user,
        db=db,
    )

    inv = (
        await db.execute(
            select(Inventory).where(
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == "sku-1",
                Inventory.lot_number == "LOT-MANUAL-22",
            )
        )
    ).scalar_one()

    assert response["sku_code"] == "SKU-1"
    assert response["quantity"] == 22
    assert inv.quantity_on_hand == 22
    assert inv.lot_number == "LOT-MANUAL-22"


@pytest.mark.asyncio
async def test_manual_inventory_import_refreshes_pending_outbound_readiness(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    """Restocking a SKU should update affected pending outbound readiness projections."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    order = OutboundOrder(
        id="order-short-import",
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="SO-SHORT-IMPORT",
        status=OutboundStatus.PENDING.value,
    )
    db.add(order)
    db.add(
        OutboundOrderLine(
            id="line-short-import",
            tenant_id=tenant_id,
            order_id=order.id,
            sku_id="sku-1",
            quantity_ordered=20,
            quantity_allocated=0,
        )
    )
    await db.flush()
    readiness, _total_items, shortage_units = await refresh_outbound_readiness_projection(
        db,
        tenant_id,
        order,
    )
    assert readiness == "short_stock"
    assert shortage_units == 15
    assert order.pick_readiness_rank == 10

    user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    response = await import_single_inventory_row(
        body=ManualInventoryImportRequest(
            warehouse_id=warehouse_id,
            location_barcode="A-01-01-01-01",
            sku_code="SKU-1",
            quantity=25,
        ),
        current_user=user,
        db=db,
    )
    await db.refresh(order)

    assert response["readiness_refresh"]["scanned_orders"] == 1
    assert response["readiness_refresh"]["updated_orders"] == 1
    assert order.pick_readiness_rank == 20


@pytest.mark.asyncio
async def test_inventory_adjustment_refreshes_pending_outbound_readiness(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    """Manual quantity adjustments should keep pending pick readiness current."""
    fixtures = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    order = OutboundOrder(
        id="order-short-adjust",
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="SO-SHORT-ADJUST",
        status=OutboundStatus.PENDING.value,
    )
    db.add(order)
    db.add(
        OutboundOrderLine(
            id="line-short-adjust",
            tenant_id=tenant_id,
            order_id=order.id,
            sku_id="sku-1",
            quantity_ordered=20,
            quantity_allocated=0,
        )
    )
    await db.flush()
    await refresh_outbound_readiness_projection(db, tenant_id, order)
    assert order.pick_readiness_rank == 10

    svc = InventoryService(db, tenant_id)
    result = await svc.adjust_inventory(
        inventory_id=fixtures["inventory_id"],
        new_quantity=25,
        user_id=user_id,
        reason="Restocked after count",
    )
    await db.refresh(order)

    assert result["readiness_refresh"]["scanned_orders"] == 1
    assert result["readiness_refresh"]["updated_orders"] == 1
    assert order.pick_readiness_rank == 20
    inv = await db.get(Inventory, fixtures["inventory_id"])
    assert inv.quantity_on_hand == 25
    assert inv.quantity_on_hand - inv.quantity_allocated == 20
    transaction = (
        await db.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.transaction_type == TransactionType.ADJUST.value,
                InventoryTransaction.sku_id == "sku-1",
                InventoryTransaction.location_id == "loc-1",
            )
        )
    ).scalar_one()
    assert transaction.quantity_change == 15
    assert transaction.performed_by == user_id
    assert "Reason: Restocked after count" in (transaction.notes or "")


@pytest.mark.asyncio
async def test_inventory_adjustment_requires_reason_before_mutating_stock(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    """Manual adjustments must have an operator reason before stock changes."""
    fixtures = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)

    svc = InventoryService(db, tenant_id)
    result = await svc.adjust_inventory(
        inventory_id=fixtures["inventory_id"],
        new_quantity=25,
        user_id=user_id,
        reason="   ",
    )
    inv = await db.get(Inventory, fixtures["inventory_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.transaction_type == TransactionType.ADJUST.value,
        )
    )

    assert result == {"success": False, "error": "Adjustment reason is required"}
    assert inv.quantity_on_hand == 10
    assert txn_count == 0


@pytest.mark.asyncio
async def test_cycle_count_transaction_records_variance_for_audit(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    """Cycle counts should update stock and write readable variance evidence."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)

    svc = InventoryService(db, tenant_id)
    result = await svc.cycle_count(
        location_id="loc-1",
        counts=[{"sku_id": "sku-1", "counted_quantity": 12}],
        user_id=user_id,
    )
    inv = await db.get(Inventory, "inv-1")
    transaction = (
        await db.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.transaction_type == TransactionType.CYCLE_COUNT.value,
                InventoryTransaction.sku_id == "sku-1",
                InventoryTransaction.location_id == "loc-1",
            )
        )
    ).scalar_one()

    assert result == [
        {"sku_id": "sku-1", "system": 10, "counted": 12, "discrepancy": 2, "status": "variance"}
    ]
    assert inv.quantity_on_hand == 12
    assert transaction.quantity_change == 2
    assert transaction.performed_by == user_id
    assert transaction.notes == "Cycle count: system=10 counted=12 variance=2"


@pytest.mark.asyncio
async def test_import_center_accepts_real_csv_files_and_manual_inventory_entry(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    tmp_path,
):
    """CSV uploads and single-row intake should both work with real files."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)

    db.add(
        Location(
            id="loc-stage-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-1",
            barcode="STAGE-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="sku-2",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-2",
            name="Second Widget",
        )
    )
    await db.flush()

    inbound_path = tmp_path / "inbound-orders.csv"
    inbound_path.write_text(
        "\n".join(
            [
                "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,supplier_name",
                "INB-CSV-001,ACME,MAIN,SKU-1,12,PO-REF-001,Vendor A",
            ]
        ),
        encoding="utf-8",
    )
    outbound_path = tmp_path / "outbound-orders.csv"
    outbound_path.write_text(
        "\n".join(
            [
                "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,carrier",
                "OUT-CSV-001,ACME,MAIN,SKU-1,5,SO-REF-001,DHL",
            ]
        ),
        encoding="utf-8",
    )
    inventory_path = tmp_path / "inventory.csv"
    inventory_path.write_text(
        "\n".join(
            [
                "sku_code,location_barcode,client_id,quantity,lot_number",
                f"SKU-2,A-01-01-01-01,{client_id},18,LOT-CSV-001",
            ]
        ),
        encoding="utf-8",
    )

    tenant_admin = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    inbound_preview = await preview_inbound_orders_csv(
        file=UploadFile(
            filename=inbound_path.name,
            file=BytesIO(inbound_path.read_bytes()),
        ),
        current_user=tenant_admin,
    )
    assert inbound_preview["total_rows"] == 1
    assert inbound_preview["missing_required"] == []

    inbound_import = await import_inbound_orders_csv(
        file=UploadFile(
            filename=inbound_path.name,
            file=BytesIO(inbound_path.read_bytes()),
        ),
        mapping=None,
        current_user=tenant_admin,
        db=db,
    )
    assert inbound_import["imported"] == 1
    inbound_order = await db.scalar(
        select(InboundOrder).where(
            InboundOrder.tenant_id == tenant_id,
            InboundOrder.order_number == "INB-CSV-001",
        )
    )
    assert inbound_order is not None
    assert inbound_order.reference_number == "PO-REF-001"

    outbound_preview = await preview_outbound_orders_csv(
        file=UploadFile(
            filename=outbound_path.name,
            file=BytesIO(outbound_path.read_bytes()),
        ),
        current_user=tenant_admin,
    )
    assert outbound_preview["total_rows"] == 1
    assert outbound_preview["missing_required"] == []

    outbound_import = await import_outbound_orders_csv(
        file=UploadFile(
            filename=outbound_path.name,
            file=BytesIO(outbound_path.read_bytes()),
        ),
        mapping=None,
        current_user=tenant_admin,
        db=db,
    )
    assert outbound_import["imported"] == 1
    outbound_order = await db.scalar(
        select(OutboundOrder).where(
            OutboundOrder.tenant_id == tenant_id,
            OutboundOrder.order_number == "OUT-CSV-001",
        )
    )
    assert outbound_order is not None
    assert outbound_order.reference_number == "SO-REF-001"
    assert outbound_order.carrier == "DHL"

    inventory_import = await import_inventory_csv(
        file=UploadFile(
            filename=inventory_path.name,
            file=BytesIO(inventory_path.read_bytes()),
        ),
        warehouse_id=warehouse_id,
        current_user=tenant_admin,
        db=db,
    )
    assert inventory_import["imported"] == 1
    imported_inventory = await db.scalar(
        select(Inventory)
        .join(SKU, SKU.id == Inventory.sku_id)
        .join(Location, Location.id == Inventory.location_id)
        .where(
            Inventory.tenant_id == tenant_id,
            SKU.sku_code == "SKU-2",
            Location.barcode == "A-01-01-01-01",
            Inventory.lot_number == "LOT-CSV-001",
        )
    )
    assert imported_inventory is not None
    assert imported_inventory.quantity_on_hand == 18

    manual_inventory = await import_single_inventory_row(
        body=ManualInventoryImportRequest(
            warehouse_id=warehouse_id,
            location_barcode="STAGE-01",
            sku_code="SKU-1",
            quantity=9,
            lot_number="LOT-MANUAL-CSV",
        ),
        current_user=tenant_admin,
        db=db,
    )
    assert manual_inventory["location_barcode"] == "STAGE-01"


@pytest.mark.asyncio
async def test_import_inbound_orders_csv_groups_package_rows_under_one_line(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    tmp_path,
):
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    inbound_path = tmp_path / "inbound-package-orders.csv"
    inbound_path.write_text(
        "\n".join(
            [
                "order_number,client_code,warehouse_code,sku_code,quantity,reference_number,supplier_name,line_number,package_number,package_type,package_tracking_number",
                "INB-CSV-PKG-001,ACME,MAIN,SKU-1,3,PO-REF-PKG,Vendor A,10,1,carton,PKG-TRACK-1",
                "INB-CSV-PKG-001,ACME,MAIN,SKU-1,5,PO-REF-PKG,Vendor A,10,2,crate,PKG-TRACK-2",
            ]
        ),
        encoding="utf-8",
    )

    tenant_admin = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    imported = await import_inbound_orders_csv(
        file=UploadFile(
            filename=inbound_path.name,
            file=BytesIO(inbound_path.read_bytes()),
        ),
        mapping=None,
        current_user=tenant_admin,
        db=db,
    )

    order = await db.scalar(
        select(InboundOrder).where(
            InboundOrder.tenant_id == tenant_id,
            InboundOrder.order_number == "INB-CSV-PKG-001",
        )
    )
    assert imported["imported"] == 1
    assert imported["errors"] == []
    assert order is not None

    lines = (
        (
            await db.execute(
                select(InboundOrderLine)
                .where(InboundOrderLine.order_id == order.id)
                .order_by(InboundOrderLine.line_number.asc())
            )
        )
        .scalars()
        .all()
    )
    packages = (
        (
            await db.execute(
                select(InboundPackage)
                .where(InboundPackage.order_id == order.id)
                .order_by(InboundPackage.package_number.asc())
            )
        )
        .scalars()
        .all()
    )

    assert len(lines) == 1
    assert lines[0].line_number == 10
    assert lines[0].quantity_expected == 8
    assert len(packages) == 2
    assert [package.package_number for package in packages] == [1, 2]
    assert [package.expected_qty for package in packages] == [3, 5]
    assert [package.package_type for package in packages] == ["carton", "crate"]
    assert [package.external_tracking_number for package in packages] == [
        "PKG-TRACK-1",
        "PKG-TRACK-2",
    ]


@pytest.mark.asyncio
async def test_inventory_list_is_scoped_to_current_tenant(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    """Inventory listing must never include rows from a different tenant."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)

    other_tenant_id = "other-tenant-001"
    other_client_id = "other-client-001"
    other_warehouse_id = "other-warehouse-001"
    db.add(
        Tenant(id=other_tenant_id, name="Other 3PL", code="OTH", contact_email="other@example.com")
    )
    db.add(Client(id=other_client_id, tenant_id=other_tenant_id, name="Other Client", code="OTHR"))
    db.add(
        Warehouse(id=other_warehouse_id, tenant_id=other_tenant_id, name="Other Main", code="OMAIN")
    )
    db.add(
        Zone(
            id="other-zone-1",
            tenant_id=other_tenant_id,
            warehouse_id=other_warehouse_id,
            name="Other Zone",
            code="OZ1",
        )
    )
    db.add(
        Location(
            id="other-loc-1",
            tenant_id=other_tenant_id,
            warehouse_id=other_warehouse_id,
            zone_id="other-zone-1",
            barcode="B-01-01-01-01",
            aisle="B",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        SKU(
            id="other-sku-1",
            tenant_id=other_tenant_id,
            client_id=other_client_id,
            sku_code="OTHER-SKU-1",
            name="Other Widget",
        )
    )
    db.add(
        Inventory(
            id="other-inv-1",
            tenant_id=other_tenant_id,
            client_id=other_client_id,
            warehouse_id=other_warehouse_id,
            location_id="other-loc-1",
            sku_id="other-sku-1",
            quantity_on_hand=99,
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    result = await list_inventory(
        warehouse_id=None,
        client_id=None,
        sku_id=None,
        search=None,
        focus=None,
        location_type=None,
        issue=None,
        sort_by="warehouse",
        sort_direction="asc",
        page=PaginationParams(offset=0, limit=100),
        current_user=current_user,
        db=db,
    )

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0].warehouse_id == warehouse_id
    assert result["items"][0].client_id == client_id


@pytest.mark.asyncio
async def test_inventory_list_filters_search_before_pagination(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    """Inventory search/filtering should happen in SQL, not only on the current UI page."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    db.add(
        Location(
            id="loc-search-2",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-1",
            barcode="A-99-SEARCH-01",
            aisle="A",
            rack="99",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        SKU(
            id="sku-search-2",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SEARCH-SKU-2",
            name="Searchable Widget",
        )
    )
    db.add(
        Inventory(
            id="inv-search-2",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-search-2",
            sku_id="sku-search-2",
            quantity_on_hand=7,
            quantity_allocated=0,
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    result = await list_inventory(
        warehouse_id=None,
        client_id=None,
        sku_id=None,
        search="SEARCH-SKU",
        focus=None,
        location_type=None,
        issue=None,
        sort_by="sku",
        sort_direction="asc",
        page=PaginationParams(offset=0, limit=1),
        current_user=current_user,
        db=db,
    )

    assert result["total"] == 1
    assert result["has_more"] is False
    assert len(result["items"]) == 1
    assert result["items"][0].sku_id == "sku-search-2"


@pytest.mark.asyncio
async def test_inventory_staging_focus_uses_open_putaway_source_locations(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    """The staging inventory focus should match the putaway work queue source locations."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    db.add(
        Task(
            id="task-putaway-inventory-focus",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-1",
            quantity=3,
            source_location_id="loc-1",
            reference_type="inbound_order",
            reference_id="inbound-focus-1",
            assigned_type=AssignedType.UNASSIGNED.value,
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    result = await list_inventory(
        warehouse_id=None,
        client_id=None,
        sku_id=None,
        search=None,
        focus="staging",
        location_type=None,
        issue=None,
        sort_by="warehouse",
        sort_direction="asc",
        page=PaginationParams(offset=0, limit=10),
        current_user=current_user,
        db=db,
    )

    assert result["total"] == 1
    assert result["items"][0].id == "inv-1"


@pytest.mark.asyncio
async def test_inventory_csv_import_uses_location_warehouse_when_warehouse_not_provided(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    """CSV inventory import should inherit the location warehouse instead of a placeholder default."""
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)

    tenant_admin = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    csv_file = UploadFile(
        filename="inventory.csv",
        file=BytesIO(
            "\n".join(
                [
                    "sku_code,location_barcode,client_id,quantity,lot_number",
                    f"SKU-1,A-01-01-01-01,{client_id},14,LOT-WH-AUTO",
                ]
            ).encode("utf-8")
        ),
    )

    result = await import_inventory_csv(
        file=csv_file,
        warehouse_id=None,
        current_user=tenant_admin,
        db=db,
    )

    imported_inventory = await db.scalar(
        select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.location_id == "loc-1",
            Inventory.sku_id == "sku-1",
            Inventory.lot_number == "LOT-WH-AUTO",
        )
    )

    assert result["imported"] == 1
    assert imported_inventory is not None
    assert imported_inventory.warehouse_id == warehouse_id
    assert imported_inventory.quantity_on_hand == 14
