"""Billing API — rate cards, billing periods, invoice generation."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.billing import BillingLineItem, BillingPeriod, Invoice, InvoiceStatus, RateCard
from app.models.client import Client
from app.models.tenant import Tenant
from app.services.billing_service import BillingService

router = APIRouter()


# --- Rate Cards ---


class RateCardCreate(BaseModel):
    client_id: str
    name: str
    effective_from: date
    effective_to: date | None = None
    rules: dict


class RateCardResponse(BaseModel):
    id: str
    client_id: str
    name: str
    effective_from: date
    effective_to: date | None
    rules: dict
    is_active: bool


@router.get("/rate-cards", response_model=list[RateCardResponse])
async def list_rate_cards(
    client_id: str | None = None,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(RateCard).where(
        RateCard.tenant_id == current_user.tenant_id,
        RateCard.is_active == True,  # noqa: E712
    )
    if client_id:
        query = query.where(RateCard.client_id == client_id)
    result = await db.execute(
        query.order_by(RateCard.effective_from.desc(), RateCard.created_at.desc()).limit(500)
    )
    return [
        RateCardResponse(
            id=rc.id,
            client_id=rc.client_id,
            name=rc.name,
            effective_from=rc.effective_from,
            effective_to=rc.effective_to,
            rules=rc.rules,
            is_active=rc.is_active,
        )
        for rc in result.scalars()
    ]


@router.post("/rate-cards", response_model=RateCardResponse, status_code=201)
async def create_rate_card(
    body: RateCardCreate,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    same_day_result = await db.execute(
        select(RateCard).where(
            RateCard.tenant_id == current_user.tenant_id,
            RateCard.client_id == body.client_id,
            RateCard.is_active == True,  # noqa: E712
            RateCard.effective_from == body.effective_from,
        )
    )
    for same_day_card in same_day_result.scalars():
        same_day_card.is_active = False

    next_result = await db.execute(
        select(RateCard)
        .where(
            RateCard.tenant_id == current_user.tenant_id,
            RateCard.client_id == body.client_id,
            RateCard.is_active == True,  # noqa: E712
            RateCard.effective_from > body.effective_from,
        )
        .order_by(RateCard.effective_from.asc())
        .limit(1)
    )
    next_rate_card = next_result.scalar_one_or_none()
    effective_to = body.effective_to
    if effective_to is None and next_rate_card:
        effective_to = next_rate_card.effective_from - timedelta(days=1)

    previous_result = await db.execute(
        select(RateCard).where(
            RateCard.tenant_id == current_user.tenant_id,
            RateCard.client_id == body.client_id,
            RateCard.is_active == True,  # noqa: E712
            RateCard.effective_from < body.effective_from,
            or_(RateCard.effective_to.is_(None), RateCard.effective_to >= body.effective_from),
        )
    )
    for previous_rate_card in previous_result.scalars():
        previous_rate_card.effective_to = body.effective_from - timedelta(days=1)

    rc = RateCard(
        tenant_id=current_user.tenant_id,
        client_id=body.client_id,
        name=body.name,
        effective_from=body.effective_from,
        effective_to=effective_to,
        rules=body.rules,
    )
    db.add(rc)
    await db.flush()
    return RateCardResponse(
        id=rc.id,
        client_id=rc.client_id,
        name=rc.name,
        effective_from=rc.effective_from,
        effective_to=rc.effective_to,
        rules=rc.rules,
        is_active=rc.is_active,
    )


# --- Billing Periods & Calculation ---


class BillingCalcRequest(BaseModel):
    client_id: str
    period_start: date
    period_end: date


class InvoiceGenerateRequest(BaseModel):
    client_id: str
    period_id: str
    invoice_number: str


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    client_id: str
    client_name: str | None = None
    status: str
    subtotal: float
    tax_amount: float
    total_amount: float
    currency: str
    issued_date: date | None
    due_date: date | None
    paid_date: date | None
    billing_period_id: str


class InvoiceStatusUpdateRequest(BaseModel):
    status: str


@router.post("/calculate")
async def calculate_billing(
    body: BillingCalcRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Calculate charges for a client in a date range. Creates billing period + line items."""
    svc = BillingService(db, current_user.tenant_id)

    period = await svc.create_billing_period(
        client_id=body.client_id,
        period_start=body.period_start,
        period_end=body.period_end,
    )

    charges = await svc.calculate_charges(
        client_id=body.client_id,
        period_id=period.id,
        period_start=body.period_start,
        period_end=body.period_end,
    )

    total = sum(c.get("total_amount", 0) for c in charges if "error" not in c)

    return {
        "period_id": period.id,
        "client_id": body.client_id,
        "period": f"{body.period_start} to {body.period_end}",
        "charges": charges,
        "total": total,
    }


@router.post("/invoice")
async def generate_invoice(
    body: InvoiceGenerateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Generate an invoice from a billing period."""
    await _validate_formal_invoice_profile(
        db=db,
        tenant_id=current_user.tenant_id,
        client_id=body.client_id,
    )
    svc = BillingService(db, current_user.tenant_id)
    try:
        invoice = await svc.generate_invoice(
            client_id=body.client_id,
            period_id=body.period_id,
            invoice_number=body.invoice_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "subtotal": float(invoice.subtotal),
        "tax": float(invoice.tax_amount),
        "total": float(invoice.total_amount),
    }


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    client_id: str | None = None,
    status_filter: str | None = None,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    query = (
        select(Invoice, Client.name)
        .join(Client, Client.id == Invoice.client_id)
        .where(Invoice.tenant_id == current_user.tenant_id)
        .order_by(Invoice.created_at.desc())
    )
    if client_id:
        query = query.where(Invoice.client_id == client_id)
    if status_filter:
        query = query.where(Invoice.status == status_filter)

    result = await db.execute(query.limit(200))
    rows = result.all()
    return [
        InvoiceResponse(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            client_id=invoice.client_id,
            client_name=client_name,
            status=invoice.status,
            subtotal=float(invoice.subtotal),
            tax_amount=float(invoice.tax_amount),
            total_amount=float(invoice.total_amount),
            currency=invoice.currency,
            issued_date=invoice.issued_date,
            due_date=invoice.due_date,
            paid_date=invoice.paid_date,
            billing_period_id=invoice.billing_period_id,
        )
        for invoice, client_name in rows
    ]


@router.patch("/invoice/{invoice_id}/status", response_model=InvoiceResponse)
async def update_invoice_status(
    invoice_id: str,
    body: InvoiceStatusUpdateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    if body.status not in {
        InvoiceStatus.DRAFT.value,
        InvoiceStatus.SENT.value,
        InvoiceStatus.PAID.value,
        InvoiceStatus.OVERDUE.value,
        InvoiceStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=400, detail="Unsupported invoice status")

    result = await db.execute(
        select(Invoice, Client.name)
        .join(Client, Client.id == Invoice.client_id)
        .where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice, client_name = row
    invoice.status = body.status
    if body.status == InvoiceStatus.SENT.value and not invoice.issued_date:
        invoice.issued_date = date.today()
    if body.status == InvoiceStatus.PAID.value:
        invoice.paid_date = date.today()
    if body.status != InvoiceStatus.PAID.value:
        invoice.paid_date = None
    if body.status == InvoiceStatus.DRAFT.value and invoice.issued_date is None:
        invoice.issued_date = date.today()

    await db.flush()

    return InvoiceResponse(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        client_id=invoice.client_id,
        client_name=client_name,
        status=invoice.status,
        subtotal=float(invoice.subtotal),
        tax_amount=float(invoice.tax_amount),
        total_amount=float(invoice.total_amount),
        currency=invoice.currency,
        issued_date=invoice.issued_date,
        due_date=invoice.due_date,
        paid_date=invoice.paid_date,
        billing_period_id=invoice.billing_period_id,
    )


@router.get("/invoice/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: str,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.CLIENT_VIEWER)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Generate and return invoice PDF."""
    inv_result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = inv_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if current_user.role == UserRole.CLIENT_VIEWER and invoice.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Load related data
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one()
    tenant_billing_profile = dict((tenant.settings or {}).get("billing_profile") or {})

    client_result = await db.execute(select(Client).where(Client.id == invoice.client_id))
    client = client_result.scalar_one()
    client_billing_profile = dict((client.settings or {}).get("billing_profile") or {})

    period_result = await db.execute(
        select(BillingPeriod).where(BillingPeriod.id == invoice.billing_period_id)
    )
    period = period_result.scalar_one_or_none()

    items_result = await db.execute(
        select(BillingLineItem).where(
            BillingLineItem.billing_period_id == invoice.billing_period_id
        )
    )
    items = [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "total_amount": float(item.total_amount),
        }
        for item in items_result.scalars()
    ]

    try:
        from app.services.invoice_pdf_service import generate_invoice_pdf
    except ImportError as exc:
        raise HTTPException(
            status_code=501, detail="PDF generation not available (weasyprint not installed)"
        ) from exc

    pdf_bytes = generate_invoice_pdf(
        invoice_number=invoice.invoice_number,
        tenant_name=tenant_billing_profile.get("legal_name") or tenant.name,
        tenant_address=tenant.address,
        tenant_tax_id=tenant_billing_profile.get("tax_id"),
        tenant_vat_id=tenant_billing_profile.get("vat_id"),
        tenant_billing_email=tenant_billing_profile.get("billing_email") or tenant.contact_email,
        tenant_bank_name=tenant_billing_profile.get("bank_name"),
        tenant_bank_account=tenant_billing_profile.get("bank_account"),
        tenant_iban=tenant_billing_profile.get("iban"),
        tenant_swift=tenant_billing_profile.get("swift"),
        client_name=client_billing_profile.get("legal_name") or client.name,
        client_address=client.address,
        client_tax_id=client_billing_profile.get("tax_id"),
        client_vat_id=client_billing_profile.get("vat_id"),
        client_billing_email=client_billing_profile.get("billing_email") or client.contact_email,
        issued_date=invoice.issued_date or date.today(),
        due_date=invoice.due_date,
        service_period=f"{period.period_start} → {period.period_end}" if period else None,
        payment_terms_label=client_billing_profile.get("payment_terms_label")
        or tenant_billing_profile.get("payment_terms_label"),
        tax_region=client_billing_profile.get("tax_region")
        or tenant_billing_profile.get("tax_region")
        or "eu",
        tax_label=client_billing_profile.get("tax_label")
        or tenant_billing_profile.get("tax_label")
        or (
            "Sales Tax"
            if (
                client_billing_profile.get("tax_region") or tenant_billing_profile.get("tax_region")
            )
            == "us"
            else "VAT"
        ),
        tax_rate_pct=float(
            client_billing_profile.get("tax_rate_pct")
            or tenant_billing_profile.get("tax_rate_pct")
            or 0
        ),
        tax_legal_note=client_billing_profile.get("reverse_charge_note")
        or client_billing_profile.get("tax_exemption_note")
        or tenant_billing_profile.get("reverse_charge_note")
        or tenant_billing_profile.get("tax_exemption_note"),
        footer_legal_note=tenant_billing_profile.get("invoice_footer_legal"),
        line_items=items,
        subtotal=float(invoice.subtotal),
        tax_amount=float(invoice.tax_amount),
        total_amount=float(invoice.total_amount),
        currency=invoice.currency,
        notes=invoice.notes
        or client_billing_profile.get("invoice_notes")
        or tenant_billing_profile.get("invoice_notes"),
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice-{invoice.invoice_number}.pdf"'
        },
    )


async def _validate_formal_invoice_profile(
    db: AsyncSession, tenant_id: str | None, client_id: str
) -> None:
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if (tenant.settings or {}).get("business_mode") == "self_use":
        return

    client_result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.tenant_id == tenant_id,
        )
    )
    client = client_result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    tenant_billing_profile = dict((tenant.settings or {}).get("billing_profile") or {})
    client_billing_profile = dict((client.settings or {}).get("billing_profile") or {})
    tax_region = (
        client_billing_profile.get("tax_region") or tenant_billing_profile.get("tax_region") or "eu"
    )

    missing: list[str] = []
    if not (tenant_billing_profile.get("legal_name") or tenant.name):
        missing.append("issuer legal name")
    if tax_region == "eu" and not (
        tenant_billing_profile.get("tax_id") or tenant_billing_profile.get("vat_id")
    ):
        missing.append("issuer tax or VAT registration")
    if not (client_billing_profile.get("legal_name") or client.name):
        missing.append("bill-to legal name")

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Formal invoice data is incomplete: {', '.join(missing)}",
        )
