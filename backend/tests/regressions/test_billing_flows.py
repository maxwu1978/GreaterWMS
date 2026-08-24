"""Regression tests: billing (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.billing import (
    InvoiceGenerateRequest,
    InvoiceStatusUpdateRequest,
    RateCardCreate,
    create_rate_card,
    list_invoices,
    list_rate_cards,
    update_invoice_status,
)
from app.api.v1.endpoints.billing import generate_invoice as generate_invoice_endpoint
from app.api.v1.endpoints.skus import list_skus
from app.core.pagination import PaginationParams
from app.core.security import TokenPayload, UserRole
from app.models.billing import BillingLineItem, BillingPeriod, Invoice, RateCard
from app.models.client import Client
from app.models.inventory import SKU
from app.models.tenant import Tenant


@pytest.mark.asyncio
async def test_list_rate_cards_is_scoped_to_current_tenant(
    db: AsyncSession,
    tenant_id: str,
):
    client = Client(id="client-1", tenant_id=tenant_id, name="Acme", code="ACME")
    other_tenant = Tenant(
        id="tenant-2", name="Other Tenant", code="OTH", contact_email="other@example.com"
    )
    other_client = Client(id="client-2", tenant_id="tenant-2", name="Other Client", code="OTHC")
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Billing Tenant",
                code="BILL",
                contact_email="billing@example.com",
            ),
            client,
            other_tenant,
            other_client,
            RateCard(
                id="rc-1",
                tenant_id=tenant_id,
                client_id=client.id,
                name="Tenant Rate Card",
                effective_from=datetime.now(UTC).date(),
                rules={"pick_per_line": 1.0},
                is_active=True,
            ),
            RateCard(
                id="rc-2",
                tenant_id="tenant-2",
                client_id=other_client.id,
                name="Other Rate Card",
                effective_from=datetime.now(UTC).date(),
                rules={"pick_per_line": 99.0},
                is_active=True,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await list_rate_cards(current_user=current_user, db=db)

    assert len(response) == 1
    assert response[0].id == "rc-1"


@pytest.mark.asyncio
async def test_list_rate_cards_returns_newest_effective_version_first(
    db: AsyncSession,
    tenant_id: str,
):
    client = Client(id="client-rate-order", tenant_id=tenant_id, name="Acme", code="ACME")
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Billing Tenant",
                code="BILL",
                contact_email="billing@example.com",
            ),
            client,
            RateCard(
                id="rc-old",
                tenant_id=tenant_id,
                client_id=client.id,
                name="Old Rate Card",
                effective_from=datetime(2026, 4, 1, tzinfo=UTC).date(),
                rules={"pick_per_line": 1.0},
                is_active=True,
            ),
            RateCard(
                id="rc-new",
                tenant_id=tenant_id,
                client_id=client.id,
                name="New Rate Card",
                effective_from=datetime(2026, 5, 1, tzinfo=UTC).date(),
                rules={"pick_per_line": 2.0},
                is_active=True,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await list_rate_cards(client_id=client.id, current_user=current_user, db=db)

    assert [card.id for card in response] == ["rc-new", "rc-old"]


@pytest.mark.asyncio
async def test_create_rate_card_closes_previous_active_version(
    db: AsyncSession,
    tenant_id: str,
):
    client = Client(id="client-rate-version", tenant_id=tenant_id, name="Acme", code="ACME")
    old_rate_card = RateCard(
        id="rc-version-old",
        tenant_id=tenant_id,
        client_id=client.id,
        name="Old Rate Card",
        effective_from=datetime(2026, 4, 1, tzinfo=UTC).date(),
        rules={"minimum_monthly": 200},
        is_active=True,
    )
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Billing Tenant",
                code="BILL",
                contact_email="billing@example.com",
            ),
            client,
            old_rate_card,
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await create_rate_card(
        RateCardCreate(
            client_id=client.id,
            name="May Rate Card",
            effective_from=datetime(2026, 5, 1, tzinfo=UTC).date(),
            rules={"minimum_monthly": 230},
        ),
        current_user=current_user,
        db=db,
    )

    await db.refresh(old_rate_card)

    assert response.effective_from == datetime(2026, 5, 1, tzinfo=UTC).date()
    assert old_rate_card.effective_to == datetime(2026, 4, 30, tzinfo=UTC).date()


@pytest.mark.asyncio
async def test_list_skus_is_scoped_to_current_tenant(
    db: AsyncSession,
    tenant_id: str,
):
    other_tenant_id = "tenant-sku-other"
    current_client_id = "client-sku-current"
    other_client_id = "client-sku-other"

    db.add_all(
        [
            Tenant(
                id=tenant_id, name="Current Tenant", code="CUR", contact_email="current@example.com"
            ),
            Tenant(
                id=other_tenant_id,
                name="Other Tenant",
                code="OTH",
                contact_email="other@example.com",
            ),
            Client(id=current_client_id, tenant_id=tenant_id, name="Current Client", code="CURC"),
            Client(id=other_client_id, tenant_id=other_tenant_id, name="Other Client", code="OTHC"),
            SKU(
                id="sku-current-1",
                tenant_id=tenant_id,
                client_id=current_client_id,
                sku_code="SKU-CURRENT-1",
                name="Current Tenant SKU",
            ),
            SKU(
                id="sku-other-1",
                tenant_id=other_tenant_id,
                client_id=other_client_id,
                sku_code="SKU-OTHER-1",
                name="Other Tenant SKU",
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-current",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await list_skus(
        client_id=None,
        page=PaginationParams(offset=0, limit=100),
        current_user=current_user,
        db=db,
    )

    assert [item.sku_code for item in response["items"]] == ["SKU-CURRENT-1"]


@pytest.mark.asyncio
async def test_list_invoices_is_scoped_to_current_tenant(
    db: AsyncSession,
    tenant_id: str,
):
    client = Client(id="client-1", tenant_id=tenant_id, name="Acme", code="ACME")
    other_tenant = Tenant(
        id="tenant-2", name="Other Tenant", code="OTH", contact_email="other@example.com"
    )
    other_client = Client(id="client-2", tenant_id="tenant-2", name="Other Client", code="OTHC")
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Billing Tenant",
                code="BILL",
                contact_email="billing@example.com",
            ),
            client,
            other_tenant,
            other_client,
            Invoice(
                id="inv-1",
                tenant_id=tenant_id,
                client_id=client.id,
                billing_period_id="period-1",
                invoice_number="INV-001",
                status="draft",
                subtotal=10,
                tax_amount=0,
                total_amount=10,
            ),
            Invoice(
                id="inv-2",
                tenant_id="tenant-2",
                client_id=other_client.id,
                billing_period_id="period-2",
                invoice_number="INV-OTHER",
                status="draft",
                subtotal=99,
                tax_amount=0,
                total_amount=99,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await list_invoices(current_user=current_user, db=db)

    assert len(response) == 1
    assert response[0].id == "inv-1"


@pytest.mark.asyncio
async def test_update_invoice_status_sets_paid_date(
    db: AsyncSession,
    tenant_id: str,
):
    client = Client(id="client-1", tenant_id=tenant_id, name="Acme", code="ACME")
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Billing Tenant",
                code="BILL",
                contact_email="billing@example.com",
            ),
            client,
            Invoice(
                id="inv-1",
                tenant_id=tenant_id,
                client_id=client.id,
                billing_period_id="period-1",
                invoice_number="INV-001",
                status="draft",
                subtotal=10,
                tax_amount=0,
                total_amount=10,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await update_invoice_status(
        "inv-1",
        InvoiceStatusUpdateRequest(status="paid"),
        current_user=current_user,
        db=db,
    )
    refreshed = (await db.execute(select(Invoice).where(Invoice.id == "inv-1"))).scalar_one()

    assert response.status == "paid"
    assert response.paid_date is not None
    assert refreshed.paid_date is not None


@pytest.mark.asyncio
async def test_generate_invoice_rejects_missing_formal_invoice_profile(
    db: AsyncSession,
    tenant_id: str,
):
    client = Client(id="client-formal-1", tenant_id=tenant_id, name="Acme", code="ACME")
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Billing Tenant",
                code="BILL",
                contact_email="billing@example.com",
                settings={"business_mode": "3pl", "billing_profile": {"currency": "EUR"}},
            ),
            client,
            BillingPeriod(
                id="period-formal-1",
                tenant_id=tenant_id,
                client_id=client.id,
                period_start=datetime.now(UTC).date(),
                period_end=datetime.now(UTC).date(),
                status="open",
            ),
            BillingLineItem(
                id="line-formal-1",
                tenant_id=tenant_id,
                billing_period_id="period-formal-1",
                charge_type="storage",
                description="Storage",
                quantity=1,
                unit_price=10,
                total_amount=10,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    with pytest.raises(HTTPException) as exc:
        await generate_invoice_endpoint(
            InvoiceGenerateRequest(
                client_id=client.id,
                period_id="period-formal-1",
                invoice_number="INV-MISSING-1",
            ),
            current_user=current_user,
            db=db,
        )

    assert exc.value.status_code == 400
    assert "Formal invoice data is incomplete" in exc.value.detail


@pytest.mark.asyncio
async def test_generate_invoice_allows_us_formal_profile_without_vat_or_tax_id(
    db: AsyncSession,
    tenant_id: str,
):
    client = Client(
        id="client-formal-us-1",
        tenant_id=tenant_id,
        name="Acme US",
        code="ACMEUS",
        settings={"billing_profile": {"legal_name": "Acme US Retail LLC", "tax_region": "us"}},
    )
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Billing Tenant",
                code="BILL",
                contact_email="billing@example.com",
                settings={
                    "business_mode": "3pl",
                    "billing_profile": {
                        "legal_name": "US Warehouse Services LLC",
                        "tax_region": "us",
                        "currency": "USD",
                        "tax_rate_pct": 8.25,
                    },
                },
            ),
            client,
            BillingPeriod(
                id="period-formal-us-1",
                tenant_id=tenant_id,
                client_id=client.id,
                period_start=datetime.now(UTC).date(),
                period_end=datetime.now(UTC).date(),
                status="open",
            ),
            BillingLineItem(
                id="line-formal-us-1",
                tenant_id=tenant_id,
                billing_period_id="period-formal-us-1",
                charge_type="storage",
                description="Storage",
                quantity=1,
                unit_price=10,
                total_amount=10,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin-1",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    response = await generate_invoice_endpoint(
        InvoiceGenerateRequest(
            client_id=client.id,
            period_id="period-formal-us-1",
            invoice_number="INV-US-ALLOW-1",
        ),
        current_user=current_user,
        db=db,
    )

    assert response["status"] == "draft"
    assert response["tax"] > 0
