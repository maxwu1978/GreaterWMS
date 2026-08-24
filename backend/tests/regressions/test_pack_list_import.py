"""Regression tests for governed Pack List import semantics."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.agent import (
    PackListImportAgentRequest,
    PackListImportPreviewRequest,
    confirm_pack_list_for_agent,
    preview_pack_list_for_agent,
)
from app.core.security import TokenPayload, UserPermission, UserRole
from app.models.client import Client
from app.models.inventory import SKU
from app.models.order import InboundOrder, InboundPackage
from app.models.pack_list import PackListDocument, PackListLine
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.pack_list_service import PackListService


def _source() -> str:
    return """InboundOrder,Client,Warehouse,Container/Tracking,Package Type,SKU,Item Qty,S-SKU,Item Name
IB-001,CLIENT-1,WH-1,CONT-1,PKG-001,SKU-702,1,CUST-702,Cooling System
IB-001,CLIENT-1,WH-1,CONT-1,PKG-002,SKU-702,1,CUST-702,Cooling System
"""


@pytest.mark.asyncio
async def test_pack_list_import_creates_pre_arrival_order_without_inventory(
    db: AsyncSession, tenant_id: str
):
    db.add(Tenant(id=tenant_id, name="Pack List Tenant", code="PLT", contact_email="pl@example.com"))
    db.add(Client(id="client-1", tenant_id=tenant_id, name="Customer One", code="CLIENT-1"))
    db.add(Warehouse(id="warehouse-1", tenant_id=tenant_id, name="Warehouse One", code="WH-1"))
    db.add(
        SKU(
            id="sku-702",
            tenant_id=tenant_id,
            client_id="client-1",
            sku_code="SKU-702",
            name="Cooling System",
        )
    )
    await db.flush()

    args = {
        "source_text": _source(),
        "file_name": "pack-list.csv",
        "create_inbound_if_missing": True,
    }
    preview = await PackListService(db, tenant_id).preview(args)

    assert preview["ok"] is True
    assert preview["document"]["eta"] is None
    assert preview["document"]["arrival_status"] == "pre_arrival"
    assert preview["summary"] == {
        "rows": 2,
        "valid_rows": 2,
        "error": 0,
        "warning": 1,
        "packages": 2,
        "quantity": 2,
        "serial_numbers": 0,
    }

    result = await PackListService(db, tenant_id).import_after_preview(args, "operator-1")

    assert result["ok"] is True
    assert result["inventory_changed"] is False
    order = await db.scalar(select(InboundOrder).where(InboundOrder.order_number == "IB-001"))
    assert order is not None
    assert order.status == "expected"
    assert order.expected_date is None
    document = await db.scalar(select(PackListDocument))
    assert document is not None
    assert document.status == "pending"
    assert document.package_count == 2
    assert document.serial_count == 0
    packages = list((await db.execute(select(InboundPackage))).scalars())
    assert {package.external_carton_mark for package in packages} == {"PKG-001", "PKG-002"}
    lines = list((await db.execute(select(PackListLine))).scalars())
    assert {line.package_code for line in lines} == {"PKG-001", "PKG-002"}
    assert all(line.serial_number is None for line in lines)


@pytest.mark.asyncio
async def test_pack_list_import_blocks_duplicate_source(
    db: AsyncSession, tenant_id: str
):
    db.add(Tenant(id=tenant_id, name="Duplicate Tenant", code="DUP", contact_email="dup@example.com"))
    db.add(Client(id="client-1", tenant_id=tenant_id, name="Customer One", code="CLIENT-1"))
    db.add(Warehouse(id="warehouse-1", tenant_id=tenant_id, name="Warehouse One", code="WH-1"))
    db.add(
        SKU(
            id="sku-702",
            tenant_id=tenant_id,
            client_id="client-1",
            sku_code="SKU-702",
            name="Cooling System",
        )
    )
    await db.flush()
    args = {
        "source_text": _source(),
        "file_name": "pack-list.csv",
        "create_inbound_if_missing": True,
    }
    service = PackListService(db, tenant_id)
    assert (await service.import_after_preview(args, "operator-1"))["ok"] is True

    duplicate = await service.preview(args)
    assert duplicate["ok"] is False
    assert any(error.get("code") == "duplicate_pack_list_source" for error in duplicate["errors"])


@pytest.mark.asyncio
async def test_cli_and_graphical_pack_list_operations_have_the_same_preview_and_state(
    db: AsyncSession, tenant_id: str
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Parity Tenant",
            code="PARITY",
            contact_email="parity@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "allowed_tools": ["receiving.inbound.preview_pack_list"],
                }
            },
        )
    )
    db.add(Client(id="client-1", tenant_id=tenant_id, name="Customer One", code="CLIENT-1"))
    db.add(Warehouse(id="warehouse-1", tenant_id=tenant_id, name="Warehouse One", code="WH-1"))
    db.add(
        SKU(
            id="sku-702",
            tenant_id=tenant_id,
            client_id="client-1",
            sku_code="SKU-702",
            name="Cooling System",
        )
    )
    await db.flush()

    cli_args = {
        "source_text": _source(),
        "file_name": "pack-list.csv",
        "order_number": "IB-001",
        "client_code": "CLIENT-1",
        "warehouse_code": "WH-1",
        "source_type": "customer_pack_list",
        "create_inbound_if_missing": True,
    }
    cli_preview = await PackListService(db, tenant_id).preview(cli_args)
    current_user = TokenPayload(
        sub="parity-user",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=[UserPermission.INBOUND_ORDERS_IMPORT.value],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    graphical_payload = PackListImportPreviewRequest(**cli_args)
    graphical_preview = await preview_pack_list_for_agent(
        graphical_payload,
        current_user=current_user,
        db=db,
    )

    assert graphical_preview["ok"] is True
    assert graphical_preview["source_checksum"] == cli_preview["source_checksum"]
    assert graphical_preview["summary"] == cli_preview["summary"]
    assert graphical_preview["document"] == cli_preview["document"]
    assert graphical_preview["rows"] == cli_preview["rows"]
    assert graphical_preview["summary"]["packages"] == 2
    assert graphical_preview["summary"]["serial_numbers"] == 0
    assert graphical_preview["document"]["eta"] is None
    assert graphical_preview["document"]["arrival_status"] == "pre_arrival"

    confirmed = await confirm_pack_list_for_agent(
        PackListImportAgentRequest(
            **cli_args,
            confirmation_token=graphical_preview["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="pack-list-parity-confirm-1",
        current_user=current_user,
        db=db,
    )
    order = await db.scalar(select(InboundOrder).where(InboundOrder.order_number == "IB-001"))
    documents = list((await db.execute(select(PackListDocument))).scalars())
    packages = list((await db.execute(select(InboundPackage))).scalars())

    assert confirmed["ok"] is True
    assert confirmed["state_after"]["inventory_changed"] is False
    assert confirmed["state_after"]["receiving_started"] is False
    assert order is not None and order.status == "expected" and order.expected_date is None
    assert len(documents) == 1 and documents[0].serial_count == 0
    assert {package.external_carton_mark for package in packages} == {"PKG-001", "PKG-002"}
