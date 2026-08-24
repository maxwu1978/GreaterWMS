"""Shared helpers for the regression test suite (split from tests/test_regressions.py)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.inventory import SKU, Inventory
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services import email_service


async def setup_pick_fixture(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
) -> dict:
    """Create a minimal warehouse state with a single pick task."""
    db.add(Tenant(id=tenant_id, name="Test 3PL", code="TST", contact_email="test@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Acme", code="ACME"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Main", code="MAIN"))
    db.add(
        Zone(id="zone-1", tenant_id=tenant_id, warehouse_id=warehouse_id, name="Zone 1", code="Z1")
    )
    db.add(
        Location(
            id="loc-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-1",
            barcode="A-01-01-01-01",
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
            id="sku-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-1",
            name="Widget",
        )
    )
    db.add(
        Inventory(
            id="inv-1",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-1",
            sku_id="sku-1",
            quantity_on_hand=10,
            quantity_allocated=5,
        )
    )
    db.add(
        OutboundOrder(
            id="order-1",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="SO-1",
            status=OutboundStatus.ALLOCATED.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="line-1",
            tenant_id=tenant_id,
            order_id="order-1",
            sku_id="sku-1",
            quantity_ordered=5,
            quantity_allocated=5,
        )
    )
    db.add(
        Task(
            id="task-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PICK.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-1",
            quantity=5,
            source_location_id="loc-1",
            reference_type="outbound_order",
            reference_id="order-1",
            assigned_type=AssignedType.UNASSIGNED.value,
        )
    )
    await db.flush()
    return {"task_id": "task-1", "inventory_id": "inv-1"}


def _disable_email_provider_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "auto")
    monkeypatch.setattr(email_service.settings, "EMAIL_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(email_service.settings, "RESEND_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(email_service.settings, "BREVO_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "SMTP2GO_API_KEY", "")
    monkeypatch.setattr(email_service.settings, "SMTP2GO_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "MAILERSEND_API_KEY", "")
    monkeypatch.setattr(email_service.settings, "MAILERSEND_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "POSTMARK_SERVER_TOKEN", "")
    monkeypatch.setattr(email_service.settings, "POSTMARK_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "SENDGRID_API_KEY", "")
    monkeypatch.setattr(email_service.settings, "SENDGRID_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "MAILGUN_API_KEY", "")
    monkeypatch.setattr(email_service.settings, "MAILGUN_DOMAIN", "")
    monkeypatch.setattr(email_service.settings, "MAILGUN_FROM_EMAIL", "")
    monkeypatch.setattr(email_service.settings, "SMTP_USER", "")
    monkeypatch.setattr(email_service.settings, "SMTP_PASSWORD", "")
